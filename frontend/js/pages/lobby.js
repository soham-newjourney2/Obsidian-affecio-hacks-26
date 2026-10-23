import { ApiError, api, signOut } from "../core/api.js";
import { requireSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { t } from "../core/strings.js";
import {
  applyStrings,
  mountAppHeader,
  openModal,
  setBusy,
  setFieldError,
  setPageState,
  toast,
} from "../core/ui.js";

const POLL_MS = 3000; // until live updates arrive over WebSocket (P07)
const ROOM_KEY = "echo.room"; // { id, code }: per tab, like the session

const statePanel = document.querySelector("#page-state");
const content = document.querySelector("#lobby-content");
const home = document.querySelector("#home");
const grid = document.querySelector("#catalogue");
const dialog = document.querySelector("#story-dialog");
const roomPanel = document.querySelector("#room");
const joinForm = document.querySelector("#join-form");

let openStorySlug = null;
let currentRoom = null;
let pollTimer = null;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function showError(error) {
  toast(error instanceof ApiError ? error.message : t("errors.generic"), { kind: "error" });
}

// ---- catalogue -------------------------------------------------------------------------

function inspiredBy(story) {
  const { title, author, year } = story.inspiration;
  return t("lobby.inspiredBy", { title, author, year });
}

async function openStory(story, number, trigger) {
  trigger.setAttribute("aria-busy", "true");
  let detail;
  try {
    detail = await api(`/stories/${encodeURIComponent(story.slug)}`, { auth: false });
  } catch (error) {
    trigger.removeAttribute("aria-busy");
    showError(error);
    return;
  }
  trigger.removeAttribute("aria-busy");
  openStorySlug = detail.slug;
  dialog.querySelector("#story-number").textContent = t("lobby.caseNumber", { n: number });
  dialog.querySelector("#story-title").textContent = detail.title;
  dialog.querySelector("#story-inspiration").textContent = inspiredBy(detail);
  dialog.querySelector("#story-premise").textContent = detail.premise ?? detail.description;
  dialog.querySelector("#story-roles").replaceChildren(
    ...detail.roles.map((role) => {
      const item = el("li", "story-modal__role");
      item.append(el("strong", null, role.name), el("span", null, role.focus));
      return item;
    }),
  );
  const source = dialog.querySelector("#story-source");
  source.href = detail.inspiration.source_url;
  source.textContent = t("lobby.detail.original", { language: detail.inspiration.language });
  dialog.showModal();
}

function storyCard(story, number, genreLabels) {
  const item = el("li", `story-card case-card${story.playable ? " story-card--open" : " story-card--soon"}`);
  item.dataset.slug = story.slug;
  // Coming-soon cards say so with a visual stamp; the label carries it for screen readers.
  const labelClass = story.playable ? "case-card__label" : "case-card__label visually-hidden";
  item.append(el("span", labelClass, story.playable ? t("lobby.caseNumber", { n: number }) : t("lobby.comingSoon")));
  item.append(el("h3", "case-card__title", story.title));
  item.append(el("p", "case-card__body", story.description));

  const tags = el("ul", "story-card__tags");
  for (const genre of story.genres) tags.append(el("li", "story-card__tag", genreLabels.get(genre) ?? genre));
  tags.append(el("li", "story-card__tag", t("lobby.players", { min: story.min_players, max: story.max_players })));
  if (story.est_minutes) tags.append(el("li", "story-card__tag", t("lobby.minutes", { n: story.est_minutes })));
  item.append(tags);
  item.append(el("p", "story-card__inspiration", inspiredBy(story)));

  if (story.playable) {
    const open = el("button", "btn btn--seal story-card__open", t("lobby.openCase"));
    open.type = "button";
    open.addEventListener("click", () => openStory(story, number, open));
    item.append(open);
  } else {
    const stamp = el("span", "story-card__stamp", t("lobby.comingSoon"));
    stamp.setAttribute("aria-hidden", "true");
    item.append(stamp);
  }
  return item;
}

function renderCatalogue(stories, meta) {
  const genreLabels = new Map(meta.genres.map((g) => [g.id, g.label]));
  if (stories.length === 0) {
    grid.replaceChildren(el("li", "catalogue__empty", t("lobby.catalogueEmpty")));
    return;
  }
  let caseNumber = 0;
  grid.replaceChildren(...stories.map((story) => storyCard(story, story.playable ? ++caseNumber : null, genreLabels)));
}

// ---- room ------------------------------------------------------------------------------

function rememberRoom(room) {
  currentRoom = room;
  try {
    if (room) sessionStorage.setItem(ROOM_KEY, JSON.stringify(room));
    else sessionStorage.removeItem(ROOM_KEY);
  } catch {
    // storage blocked: the room is remembered only while this page stays open
  }
}

function savedRoom() {
  try {
    return JSON.parse(sessionStorage.getItem(ROOM_KEY));
  } catch {
    return null;
  }
}

function formatCode(code) {
  return `${code.slice(0, 4)}-${code.slice(4)}`;
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

function showHome() {
  stopPolling();
  roomPanel.hidden = true;
  home.hidden = false;
}

function memberRow(member) {
  const row = el("li", `room__member${member.status === "ready" || member.status === "playing" ? " is-ready" : ""}`);
  const name = el("span", "room__member-name", member.display_name);
  row.append(name);
  if (member.is_you) row.append(el("span", "room__badge", t("lobby.room.you")));
  if (member.is_host) row.append(el("span", "room__badge room__badge--host", t("lobby.room.host")));
  if (member.status !== "playing") {
    const ready = member.status === "ready";
    // Icon + word, never colour alone.
    row.append(el("span", "room__state", `${ready ? "✓" : "…"} ${t(ready ? "lobby.room.ready" : "lobby.room.notReady")}`));
  }
  return row;
}

function statusLine(view) {
  if (view.status !== "waiting") return "";
  const count = view.members.length;
  if (count < view.story.min_players) return t("lobby.room.needPlayers", { min: view.story.min_players });
  if (view.members.some((m) => m.status !== "ready")) return t("lobby.room.needReady");
  if (!view.you_are_host) {
    const host = view.members.find((m) => m.is_host);
    return t("lobby.room.waitingHost", { name: host?.display_name ?? "" });
  }
  return "";
}

function renderRoom(view) {
  const waiting = view.status === "waiting";
  roomPanel.querySelector("#room-title").textContent = t("lobby.room.title", { title: view.story.title });

  roomPanel.querySelector("#invite").hidden = !waiting;
  const code = currentRoom?.code;
  roomPanel.querySelector("#invite-known").hidden = !code;
  roomPanel.querySelector("#invite-unknown").hidden = Boolean(code);
  if (code) roomPanel.querySelector("#invite-code").textContent = formatCode(code);

  roomPanel.querySelector("#members-title").textContent = t("lobby.room.members", {
    count: view.members.length,
    max: view.story.max_players,
  });
  roomPanel.querySelector("#members").replaceChildren(...view.members.map(memberRow));
  roomPanel.querySelector("#room-status").textContent = statusLine(view);

  roomPanel.querySelector("#room-actions").hidden = !waiting;
  const me = view.members.find((m) => m.is_you);
  const toggle = roomPanel.querySelector("#ready-toggle");
  const ready = me?.status === "ready";
  toggle.setAttribute("aria-pressed", String(ready));
  toggle.textContent = t(ready ? "lobby.room.markNotReady" : "lobby.room.markReady");
  toggle.className = `btn ${ready ? "btn--ghost" : "btn--primary"}`;
  const start = roomPanel.querySelector("#start");
  start.hidden = !view.you_are_host;
  start.disabled = !view.can_start;

  const started = roomPanel.querySelector("#room-started");
  started.hidden = waiting;
  if (!waiting) {
    const names = view.members.map((m) => m.display_name).join(", ");
    roomPanel.querySelector("#started-body").textContent = t("lobby.room.startedBody", { names });
  }
}

function showRoom(view) {
  renderRoom(view);
  home.hidden = true;
  roomPanel.hidden = false;
  if (view.status === "waiting" && !pollTimer) {
    pollTimer = setInterval(() => {
      if (!document.hidden) refreshRoom();
    }, POLL_MS);
  } else if (view.status !== "waiting") {
    stopPolling();
  }
}

function leftRoom() {
  rememberRoom(null);
  showHome();
}

async function refreshRoom() {
  if (!currentRoom) return;
  try {
    showRoom(await api(`/rooms/${encodeURIComponent(currentRoom.id)}`));
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
      leftRoom();
      toast(t("lobby.room.gone"));
    }
    // Network blips: keep the last view and try again on the next tick.
  }
}

async function roomAction(button, action, body) {
  setBusy(button, true);
  try {
    const view = await api(`/rooms/${encodeURIComponent(currentRoom.id)}/${action}`, { method: "POST", body });
    setBusy(button, false);
    showRoom(view);
  } catch (error) {
    setBusy(button, false);
    showError(error);
    refreshRoom();
  }
}

async function createRoom(button) {
  setBusy(button, true);
  try {
    const view = await api("/rooms", { method: "POST", body: { story_slug: openStorySlug } });
    rememberRoom({ id: view.id, code: view.invite_code });
    dialog.close();
    showRoom(view);
    roomPanel.scrollIntoView({ block: "start" });
  } catch (error) {
    showError(error);
  } finally {
    setBusy(button, false);
  }
}

function wireRoom() {
  dialog.querySelector("#story-create").addEventListener("click", (event) => createRoom(event.currentTarget));

  roomPanel.querySelector("#copy-code").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(currentRoom.code);
      toast(t("lobby.room.copied"), { kind: "success" });
    } catch {
      toast(t("lobby.room.copyFailed"), { kind: "error" });
    }
  });

  roomPanel.querySelector("#ready-toggle").addEventListener("click", (event) => {
    const ready = event.currentTarget.getAttribute("aria-pressed") !== "true";
    roomAction(event.currentTarget, "ready", { ready });
  });
  roomPanel.querySelector("#start").addEventListener("click", (event) => roomAction(event.currentTarget, "start"));

  roomPanel.querySelector("#leave").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const confirmed = await openModal({
      title: t("lobby.room.leaveTitle"),
      body: t("lobby.room.leaveBody"),
      actions: [
        { label: t("lobby.room.stay"), value: false, kind: "ghost" },
        { label: t("lobby.room.leaveConfirm"), value: true, kind: "seal" },
      ],
    });
    if (!confirmed) return;
    setBusy(button, true);
    try {
      await api(`/rooms/${encodeURIComponent(currentRoom.id)}/leave`, { method: "POST" });
    } catch (error) {
      if (!(error instanceof ApiError && (error.status === 403 || error.status === 404))) {
        setBusy(button, false);
        showError(error);
        return;
      }
    }
    setBusy(button, false);
    leftRoom();
  });

  roomPanel.querySelector("#back-to-catalogue").addEventListener("click", leftRoom);

  joinForm.querySelector('[type="submit"]').disabled = false;
  joinForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = joinForm.querySelector("#join-code");
    const code = input.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (code.length !== 8) {
      setFieldError(input, t("lobby.join.invalid"));
      input.focus();
      return;
    }
    setFieldError(input, "");
    const button = joinForm.querySelector('[type="submit"]');
    setBusy(button, true);
    try {
      const view = await api("/rooms/join", { method: "POST", body: { code } });
      // Keep the code if this tab already knew it (e.g. the host re-joining).
      rememberRoom({ id: view.id, code: currentRoom?.id === view.id ? currentRoom.code : null });
      input.value = "";
      showRoom(view);
    } catch (error) {
      setFieldError(input, error instanceof ApiError ? error.message : t("errors.generic"));
    } finally {
      setBusy(button, false);
    }
  });
}

// ---- page ------------------------------------------------------------------------------

async function load(user) {
  setPageState(statePanel, "loading");
  content.hidden = true;
  try {
    await api("/users/me/profile");
  } catch (error) {
    if (error instanceof ApiError && error.code === "PROFILE_NOT_FOUND") {
      location.replace("/onboarding.html");
      return;
    }
    if (error instanceof ApiError && error.status === 401) return; // redirecting to sign-in
    setPageState(statePanel, "error", { message: error.message, onRetry: () => load(user) });
    return;
  }
  try {
    const [stories, meta] = await Promise.all([
      api("/stories", { auth: false }),
      api("/meta/interests", { auth: false }),
    ]);
    renderCatalogue(stories, meta);
  } catch {
    setPageState(statePanel, "error", { message: t("lobby.catalogueError"), onRetry: () => load(user) });
    return;
  }
  document.querySelector("#welcome").textContent = t("lobby.welcome", { name: user.display_name });
  setPageState(statePanel, null);
  content.hidden = false;

  const saved = savedRoom();
  if (saved?.id) {
    currentRoom = saved;
    await refreshRoom();
  }
}

applyStrings();
initAtmosphere();
dialog.querySelector("#story-close").addEventListener("click", () => dialog.close());

const user = requireSession();
if (user) {
  mountAppHeader(user, signOut);
  wireRoom();
  load(user);
}
