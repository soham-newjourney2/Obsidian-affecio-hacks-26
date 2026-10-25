// Table page: start a table or join with a code, a live waiting room with chat, then the case itself.
import { ApiError, api, signOut } from "../core/api.js";
import { getToken, redirectToLogin, requireSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { applyTempStrings, tt } from "../core/strings-temp.js";
import { mountAppHeader, openModal, setBusy, setFieldError, setPageState, toast } from "../core/ui.js";
import { connectRoom, newId } from "../core/ws.js";
import { createGame } from "./room-game.js";

const ROOM_KEY = "echo.room"; // { id, code } per tab; the code is known only to the creating tab
const MAX_CHAT = 1000;

const $ = (selector) => document.querySelector(selector);
const statePanel = $("#page-state");
const gate = $("#gate");
const table = $("#table");

let current = null; // { id, code }
let socket = null;
let view = null; // latest room view (personal)
let you = null; // my member id
let online = new Set();
const pending = new Map(); // client_message_id -> body, until the server echoes it
const sentFrames = new Map(); // frame id -> client_message_id, to retry rate-limited sends
const RETRY_MS = 1200;

const game = createGame({
  onVote: (choiceId) => {
    const g = game.current();
    sendGame("game.vote", { turn: g.turn, state_version: g.version, choice_id: choiceId });
  },
  onShare: (clueId) => sendGame("game.clue.share", { clue_id: clueId }),
  onHint: () => sendGame("game.hint.request", {}),
  onTheory: (text) => sendGame("game.theory.submit", { text }),
});

// Identity comes from the socket on the server; the client only says what it wants to do.
function sendGame(type, payload) {
  if (!socket?.send(type, { ...payload, client_action_id: newId() })) toast(tt("room.status.reconnecting"));
}

function setMode(hasGame) {
  table.dataset.mode = hasGame ? "game" : "waiting";
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

const KNOWN_ERRORS = new Set([
  "RATE_LIMITED",
  "ROOM_CLOSED",
  "FRAME_TOO_LARGE",
  "VALIDATION_ERROR",
  "NOT_A_MEMBER",
  "ROOM_NOT_WAITING",
]);
const GAME_ERRORS = new Set(["STALE_STATE", "ALREADY_SHARED", "NO_MORE_HINTS", "GAME_OVER"]);

function errorText(code) {
  if (GAME_ERRORS.has(code)) return tt(`game.errors.${code}`);
  return tt(`room.errors.${KNOWN_ERRORS.has(code) ? code : "generic"}`);
}

function remember(room) {
  current = room;
  try {
    if (room) sessionStorage.setItem(ROOM_KEY, JSON.stringify(room));
    else sessionStorage.removeItem(ROOM_KEY);
  } catch {
    // storage blocked: remembered only while this page is open
  }
}

function saved() {
  const fromUrl = new URLSearchParams(location.search).get("id");
  try {
    const stored = JSON.parse(sessionStorage.getItem(ROOM_KEY));
    if (fromUrl) return { id: fromUrl, code: stored?.id === fromUrl ? stored.code : null };
    return stored;
  } catch {
    return fromUrl ? { id: fromUrl, code: null } : null;
  }
}

// ---- connection status -----------------------------------------------------------------

function showStatus(status) {
  const pill = $("#conn-status");
  pill.dataset.state = status;
  const key = { connecting: "connecting", connected: "connected", reconnecting: "reconnecting", offline: "offline" }[status] ?? "closed";
  $("#conn-text").textContent = tt(`room.status.${key}`);
  $("#chat-send").disabled = status !== "connected";
  // In the story, a dropped connection gets a clear overlay; your seat is kept.
  $("#reconnect").hidden = !(table.dataset.mode === "game" && (status === "reconnecting" || status === "offline"));
  if (status === "connected") resendPending();
  if (status === "unauthorized") redirectToLogin();
  if (status === "forbidden") leaveLocally(tt("room.gone"));
}

// ---- rendering -------------------------------------------------------------------------

function memberRow(member) {
  const row = el("li", "room-member");
  const ready = member.status === "ready" || member.status === "playing";
  if (ready) row.classList.add("is-ready");
  const here = online.has(member.member_id);
  row.classList.toggle("is-away", !here);
  row.append(el("span", "room-member__name", member.display_name));
  if (member.is_you) row.append(el("span", "room-badge", tt("room.members.you")));
  if (member.is_host) row.append(el("span", "room-badge room-badge--host", tt("room.members.host")));
  if (member.is_companion) row.append(el("span", "room-badge", `🤖 ${tt("room.members.companion")}`));
  if (!member.is_you && !member.is_companion) {
    const report = el("button", "btn btn--ghost btn--sm room-member__report", tt("results.connect.report"));
    report.type = "button";
    report.addEventListener("click", () => reportFromRoom(member.display_name));
    row.append(report);
  }
  // Icon + word for every state, never colour alone.
  row.append(el("span", "room-member__presence", `${here ? "●" : "○"} ${tt(here ? "room.members.online" : "room.members.away")}`));
  if (member.status !== "playing") {
    row.append(el("span", "room-member__state", `${ready ? "✓" : "…"} ${tt(ready ? "room.members.ready" : "room.members.notReady")}`));
  }
  return row;
}

function hintFor(room) {
  if (room.status !== "waiting") return "";
  if (room.members.length < room.story.min_players) return tt("room.hints.needPlayers", { min: room.story.min_players });
  if (room.members.some((m) => m.status !== "ready")) return tt("room.hints.needReady");
  if (!room.you_are_host) {
    const host = room.members.find((m) => m.is_host);
    return tt("room.hints.waitingHost", { name: host?.display_name ?? "" });
  }
  return tt("room.hints.canStart");
}

function renderRoom() {
  if (!view) return;
  const waiting = view.status === "waiting";
  $("#table-title").textContent = view.story.title;
  $("#invite").hidden = !waiting;
  $("#invite-known").hidden = !current?.code;
  $("#invite-unknown").hidden = Boolean(current?.code);
  if (current?.code) $("#invite-code").textContent = `${current.code.slice(0, 4)}-${current.code.slice(4)}`;

  $("#members-title").textContent = tt("room.members.title", { count: view.members.length, max: view.story.max_players });
  $("#members").replaceChildren(...view.members.map(memberRow));
  $("#table-hint").textContent = hintFor(view);

  $("#table-actions").hidden = !waiting;
  const me = view.members.find((m) => m.is_you);
  const ready = me?.status === "ready";
  const toggle = $("#ready-toggle");
  toggle.setAttribute("aria-pressed", String(ready));
  toggle.textContent = tt(ready ? "room.actions.notReady" : "room.actions.ready");
  toggle.className = `btn ${ready ? "btn--ghost" : "btn--primary"}`;
  const start = $("#start");
  $("#add-companions").hidden = !view.companions_allowed;
  start.hidden = !view.you_are_host;
  start.disabled = !view.can_start;
  game.setNames(view.members);
  if (view.session_id) $("#results-link").href = `/results.html?session=${encodeURIComponent(view.session_id)}`;
}

function messageItem(message, { isPending = false } = {}) {
  const item = el("li", `room-msg${message.member_id === you ? " room-msg--mine" : ""}${isPending ? " is-pending" : ""}`);
  item.dataset.cid = message.client_message_id ?? "";
  const meta = el("p", "room-msg__meta");
  meta.append(el("span", "room-msg__who", message.display_name ?? tt("common.brand")));
  if (isPending) meta.append(el("span", "room-msg__time", tt("room.chat.sending")));
  else meta.append(el("time", "room-msg__time", new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })));
  item.append(meta, el("p", "room-msg__body", message.body)); // textContent only
  return item;
}

function addMessage(message) {
  const log = $("#chat-log");
  const existing = message.client_message_id
    ? log.querySelector(`[data-cid="${CSS.escape(message.client_message_id)}"]`)
    : null;
  if (existing && !existing.classList.contains("is-pending")) return; // already shown
  const item = messageItem(message);
  if (existing) existing.replaceWith(item);
  else log.append(item);
  pending.delete(message.client_message_id);
  $("#chat-empty").hidden = true;
  log.scrollTop = log.scrollHeight;
}

function renderHistory(messages) {
  const log = $("#chat-log");
  log.replaceChildren(...messages.map((m) => messageItem(m)));
  for (const [cid, body] of pending) {
    if (!messages.some((m) => m.client_message_id === cid)) {
      log.append(messageItem({ client_message_id: cid, body, member_id: you, display_name: user.display_name }, { isPending: true }));
    } else {
      pending.delete(cid);
    }
  }
  $("#chat-empty").hidden = log.children.length > 0;
  log.scrollTop = log.scrollHeight;
}

async function reportFromRoom(name) {
  const categories = ["harassment", "hate", "spam", "safety", "other"];
  const category = await openModal({
    title: tt("results.connect.reportTitle", { name }),
    body: tt("results.connect.reportBody"),
    actions: [
      ...categories.map((c) => ({ label: tt(`safety.categories.${c}`), value: c, kind: "ghost" })),
      { label: tt("safety.cancel"), value: null, kind: "primary" },
    ],
  });
  if (!category) return;
  try {
    await api("/reports", { method: "POST", body: { room_id: current.id, category, description: name } });
  } catch {
    toast(tt("results.connect.unavailable"), { kind: "error" });
  }
}

// ---- socket frames ---------------------------------------------------------------------

function onFrame(frame) {
  const { type, payload } = frame;
  if (type === "room.snapshot") {
    view = payload.room;
    you = payload.you;
    online = new Set(payload.online);
    renderHistory(payload.messages);
    renderRoom();
    setMode(Boolean(payload.game));
    if (payload.game) game.render(payload.game);
  } else if (type === "room.member") {
    online = new Set(payload.online);
    if (payload.room) view = payload.room;
    renderRoom();
  } else if (type === "chat.message") {
    addMessage(payload);
  } else if (type === "moderation.notice") {
    toast(tt("results.connect.reported"), { kind: "success" });
  } else if (type.startsWith("game.")) {
    setMode(true);
    game.render(payload.view, { event: type, payload });
  } else if (type === "error") {
    const cid = sentFrames.get(payload.ref_id);
    sentFrames.delete(payload.ref_id);
    if (payload.code === "RATE_LIMITED" && cid && pending.has(cid)) {
      setTimeout(() => sendChat(cid), RETRY_MS); // same client id: the server dedupes retries
      return;
    }
    toast(errorText(payload.code), { kind: payload.code === "STALE_STATE" ? "info" : "error" });
  }
}

function sendChat(cid) {
  const body = pending.get(cid);
  if (body === undefined) return;
  const frameId = socket?.send("chat.send", { client_message_id: cid, body });
  if (frameId) sentFrames.set(frameId, cid); // if offline, resent on reconnect
}

function resendPending() {
  for (const cid of pending.keys()) sendChat(cid);
}

// ---- table lifecycle -------------------------------------------------------------------

function enterTable(room) {
  remember(room);
  history.replaceState(null, "", `/room.html?id=${encodeURIComponent(room.id)}`);
  setPageState(statePanel, null);
  gate.hidden = true;
  table.hidden = false;
  $("#conn-status").hidden = false;
  socket?.close();
  socket = connectRoom(room.id, { getToken, onFrame, onStatus: showStatus });
}

function leaveLocally(message) {
  socket?.close();
  socket = null;
  view = null;
  pending.clear();
  remember(null);
  history.replaceState(null, "", "/room.html");
  table.hidden = true;
  setMode(false);
  $("#reconnect").hidden = true;
  showGate();
  if (message) toast(message);
}

async function showGate() {
  setPageState(statePanel, null);
  gate.hidden = false;
  $("#conn-status").hidden = true;
  const select = $("#story-select");
  try {
    const stories = (await api("/stories", { auth: false })).filter((s) => s.playable);
    select.replaceChildren(...stories.map((s) => {
      const option = el("option", null, s.title);
      option.value = s.slug;
      return option;
    }));
    const create = $("#create-form [type=submit]");
    create.disabled = stories.length === 0;
    if (!stories.length) setFieldError(select, tt("room.gate.noStories"));
  } catch (error) {
    setFieldError(select, error instanceof ApiError ? error.message : tt("room.errors.generic"));
  }
}

function wireGate() {
  $("#create-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("[type=submit]");
    setBusy(button, true);
    try {
      const room = await api("/rooms", { method: "POST", body: { story_slug: $("#story-select").value } });
      enterTable({ id: room.id, code: room.invite_code });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : tt("room.errors.generic"), { kind: "error" });
    } finally {
      setBusy(button, false);
    }
  });

  const join = $("#join-form");
  join.querySelector("[type=submit]").disabled = false;
  join.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("#join-code");
    const code = input.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (code.length !== 8) {
      setFieldError(input, tt("room.gate.codeInvalid"));
      input.focus();
      return;
    }
    setFieldError(input, "");
    const button = join.querySelector("[type=submit]");
    setBusy(button, true);
    try {
      const room = await api("/rooms/join", { method: "POST", body: { code } });
      input.value = "";
      enterTable({ id: room.id, code: current?.id === room.id ? current.code : null });
    } catch (error) {
      setFieldError(input, error instanceof ApiError ? error.message : tt("room.errors.generic"));
    } finally {
      setBusy(button, false);
    }
  });
}

let findTimer = null;

function stopFinding() {
  clearInterval(findTimer);
  findTimer = null;
  $("#find-waiting").hidden = true;
  $("#find-cancel").hidden = true;
  $("#find-start").hidden = false;
}

function showFindStatus(status) {
  if (status.state === "matched") {
    stopFinding();
    toast(tt("room.find.matched", { why: status.explanations.join(" · ") }), { kind: "success" });
    enterTable({ id: status.room_id, code: null });
    return;
  }
  if (status.state !== "waiting") return stopFinding();
  $("#find-text").textContent = tt("room.find.waiting", { seconds: status.waited_s });
  $("#find-alternatives").hidden = !status.suggest_alternatives;
}

function wireFind() {
  $("#find-start").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setBusy(button, true);
    try {
      const status = await api("/matchmaking/queue", { method: "POST" });
      button.hidden = true;
      $("#find-waiting").hidden = false;
      $("#find-cancel").hidden = false;
      showFindStatus(status);
      findTimer = setInterval(async () => {
        try {
          showFindStatus(await api("/matchmaking/status"));
        } catch {
          // keep waiting; the next poll retries
        }
      }, 3000);
    } catch (error) {
      const message = error instanceof ApiError && error.code === "PROFILE_REQUIRED" ? tt("room.find.noProfile") : tt("room.errors.generic");
      toast(message, { kind: "error" });
    } finally {
      setBusy(button, false);
    }
  });
  $("#find-cancel").addEventListener("click", async () => {
    stopFinding();
    try {
      await api("/matchmaking/queue", { method: "DELETE" });
    } catch {
      // nothing to undo
    }
  });
}

function wireTable() {
  $("#copy-code").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(current.code);
      toast(tt("room.invite.copied"), { kind: "success" });
    } catch {
      toast(tt("room.invite.copyFailed"), { kind: "error" });
    }
  });

  $("#ready-toggle").addEventListener("click", (event) => {
    const ready = event.currentTarget.getAttribute("aria-pressed") !== "true";
    if (!socket?.send("player.ready", { ready })) toast(tt("room.status.reconnecting"));
  });

  $("#add-companions").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setBusy(button, true);
    try {
      const count = Math.min(3, view.story.max_players - view.members.length);
      await api(`/rooms/${encodeURIComponent(current.id)}/companions`, { method: "POST", body: { count } });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : tt("room.errors.generic"), { kind: "error" });
    } finally {
      setBusy(button, false);
    }
  });

  $("#start").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setBusy(button, true);
    try {
      await api(`/rooms/${encodeURIComponent(current.id)}/start`, { method: "POST" });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : tt("room.errors.generic"), { kind: "error" });
    } finally {
      setBusy(button, false);
      renderRoom(); // the WS "started" event brings the new state
    }
  });

  $("#leave").addEventListener("click", async () => {
    const confirmed = await openModal({
      title: tt("room.actions.leaveTitle"),
      body: tt("room.actions.leaveBody"),
      actions: [
        { label: tt("room.actions.stay"), value: false, kind: "ghost" },
        { label: tt("room.actions.leaveConfirm"), value: true, kind: "seal" },
      ],
    });
    if (!confirmed) return;
    try {
      await api(`/rooms/${encodeURIComponent(current.id)}/leave`, { method: "POST" });
    } catch (error) {
      if (!(error instanceof ApiError && (error.status === 403 || error.status === 404))) {
        toast(error.message, { kind: "error" });
        return;
      }
    }
    leaveLocally();
  });

  const form = $("#chat-form");
  const input = $("#chat-input");
  const counter = $("#chat-counter");
  const updateCounter = () => {
    counter.textContent = tt("room.chat.counter", { count: input.value.length, max: MAX_CHAT });
  };
  input.addEventListener("input", updateCounter);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const body = input.value.trim();
    if (!body) return;
    if (body.length > MAX_CHAT) {
      setFieldError(input, tt("room.chat.tooLong", { max: MAX_CHAT }));
      return;
    }
    setFieldError(input, "");
    const cid = newId();
    pending.set(cid, body);
    $("#chat-log").append(messageItem({ client_message_id: cid, body, member_id: you, display_name: user.display_name }, { isPending: true }));
    $("#chat-empty").hidden = true;
    sendChat(cid);
    input.value = "";
    updateCounter();
  });
  updateCounter();
}

// ---- page ------------------------------------------------------------------------------

async function load() {
  setPageState(statePanel, "loading", { message: tt("room.loading") });
  wireGate();
  wireFind();
  wireTable();
  const room = saved();
  if (!room?.id) {
    await showGate();
    return;
  }
  try {
    await api(`/rooms/${encodeURIComponent(room.id)}`); // membership check before connecting
    enterTable(room);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return; // redirecting to sign-in
    remember(null);
    await showGate();
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) toast(tt("room.gone"));
  }
}

applyTempStrings();
initAtmosphere();

const user = requireSession();
if (user) {
  mountAppHeader(user, signOut);
  $("#user-initial").textContent = [...user.display_name][0]?.toUpperCase() ?? "";
  load();
}
