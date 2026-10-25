// Results: the ending, what really happened, what the table did together (from recorded events),
// a private reflection with badges (never ranked), and the 2-question pulse.
import { ApiError, api, signOut } from "../core/api.js";
import { requireSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { applyTempStrings, tt } from "../core/strings-temp.js";
import {
  mountAppHeader,
  openModal,
  setBusy,
  setFieldError,
  setFormError,
  setPageState,
  toast,
} from "../core/ui.js";

const $ = (s) => document.querySelector(s);
const statePanel = $("#page-state");
const sessionId = new URLSearchParams(location.search).get("session");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function renderEnding(data) {
  $("#results-story").textContent = data.story.title;
  const kind = data.ending?.kind ?? "abandoned";
  const stamp = $("#results-stamp");
  stamp.textContent = tt(`game.ending.${kind}`);
  stamp.dataset.kind = kind;
  $("#ending-title").textContent = data.ending?.title ?? tt("game.ending.abandoned");
  $("#ending-text").textContent = data.ending?.text ?? "";
  $("#solution").textContent = data.solution;
}

function renderTeam(data) {
  const { team } = data;
  $("#recap").textContent = data.recap;
  const stats = [
    ["chapters", team.chapters],
    ["decisions", team.decisions],
    ["pinned", team.clues_pinned],
    ["hints", team.hints_used],
  ];
  $("#team-stats").replaceChildren(
    ...stats.flatMap(([key, value]) => {
      const wrap = el("div", "results-stat");
      wrap.append(el("dt", null, tt(`results.team.${key}`)), el("dd", null, String(value)));
      return [wrap];
    }),
  );
  $("#chapters").replaceChildren(
    ...data.chapters.map((c) => {
      const item = el("li", "results-chapter");
      item.append(el("p", "results-chapter__title", c.title), el("p", "results-chapter__prompt", c.prompt));
      item.append(el("p", "results-chapter__choice", tt("results.team.chose", { choice: c.choice, votes: c.votes })));
      return item;
    }),
  );
  $("#players").replaceChildren(
    ...team.players.map((p) => {
      const item = el("li", "results-player");
      item.append(el("span", "results-player__name", p.display_name), el("span", "results-player__role", p.roles.join(", ")));
      return item;
    }),
  );
}

function renderYou(you) {
  $("#you-facts").replaceChildren(
    el("li", null, tt("results.you.pinned", { count: you.clues_pinned })),
    el("li", null, tt("results.you.matched", { count: you.votes_matched, total: you.decisions_voted })),
    el("li", null, tt("results.you.hints", { count: you.hints_asked })),
  );
  $("#badges").replaceChildren(
    ...you.badges.map((badge) => {
      const item = el("li", "results-badge");
      item.dataset.badge = badge.id;
      item.append(
        el("p", "results-badge__name", tt(`results.badges.${badge.id}.name`)),
        el("p", "results-badge__why", tt(`results.badges.${badge.id}.why`, { count: badge.count })),
      );
      return item;
    }),
  );
  $("#badges-empty").hidden = you.badges.length > 0;
}

const CATEGORIES = ["harassment", "hate", "spam", "safety", "other"];

async function reportPerson(name, body) {
  const category = await openModal({
    title: tt("results.connect.reportTitle", { name }),
    body: tt("results.connect.reportBody"),
    actions: [
      ...CATEGORIES.map((c) => ({ label: tt(`safety.categories.${c}`), value: c, kind: "ghost" })),
      { label: tt("safety.cancel"), value: null, kind: "primary" },
    ],
  });
  if (!category) return;
  try {
    await api("/reports", { method: "POST", body: { ...body, category } });
    toast(tt("results.connect.reported"), { kind: "success" });
  } catch {
    toast(tt("results.connect.unavailable"), { kind: "error" });
  }
}

function renderConnect(data) {
  const others = data.team.players.filter((p) => p.user_id !== data.you_user_id);
  $("#connect-list").replaceChildren(
    ...others.map((p) => {
      const item = el("li", "results-connect__row");
      item.append(el("span", "results-player__name", p.display_name));
      const ask = el("button", "btn btn--primary btn--sm", tt("results.connect.ask"));
      ask.type = "button";
      ask.addEventListener("click", async () => {
        setBusy(ask, true);
        try {
          const res = await api(`/sessions/${encodeURIComponent(sessionId)}/connections`, { method: "POST", body: { user_id: p.user_id } });
          ask.textContent = tt(res.state === "connected" ? "results.connect.connected" : "results.connect.requested");
          ask.disabled = true;
          ask.removeAttribute("aria-busy");
        } catch {
          setBusy(ask, false);
          toast(tt("results.connect.unavailable"), { kind: "error" });
        }
      });
      const block = el("button", "btn btn--ghost btn--sm", tt("results.connect.block"));
      block.type = "button";
      block.addEventListener("click", async () => {
        const ok = await openModal({
          title: tt("results.connect.blockTitle", { name: p.display_name }),
          body: tt("results.connect.blockBody"),
          actions: [
            { label: tt("safety.cancel"), value: false, kind: "ghost" },
            { label: tt("results.connect.block"), value: true, kind: "seal" },
          ],
        });
        if (!ok) return;
        await api(`/users/${encodeURIComponent(p.user_id)}/block`, { method: "POST" });
        item.replaceChildren(el("span", "results-player__name", p.display_name), el("span", "hint", tt("results.connect.blocked")));
      });
      const report = el("button", "btn btn--ghost btn--sm", tt("results.connect.report"));
      report.type = "button";
      report.addEventListener("click", () => reportPerson(p.display_name, { reported_user: p.user_id }));
      item.append(ask, block, report);
      return item;
    }),
  );
}

function option(type, name, value, label) {
  const wrap = el("label", type === "scale" ? "results-scale__step" : "choice");
  const input = el("input");
  input.type = "radio";
  input.name = name;
  input.value = value;
  input.required = true;
  wrap.append(input, el("span", null, label));
  return wrap;
}

function setupPulse(submitted) {
  const form = $("#pulse-form");
  const thanks = $("#pulse-thanks");
  if (submitted) {
    form.hidden = true;
    thanks.hidden = false;
    return;
  }
  $("#play-again").replaceChildren(
    ...["yes", "maybe", "no"].map((v) => option("choice", "play_again", v, tt(`results.pulse.${v}`))),
  );
  $("#ease").replaceChildren(...[1, 2, 3, 4, 5].map((n) => option("scale", "ease_of_talking", String(n), String(n))));
  const submit = form.querySelector("[type=submit]");
  submit.disabled = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFormError(form, "");
    const play = form.querySelector("input[name=play_again]:checked")?.value;
    const ease = form.querySelector("input[name=ease_of_talking]:checked")?.value;
    setFieldError($("#q-play"), play ? "" : tt("results.pulse.pick"));
    setFieldError($("#q-ease"), ease ? "" : tt("results.pulse.pick"));
    if (!play || !ease) {
      setFormError(form, tt("results.pulse.pickBoth"));
      return;
    }
    setBusy(submit, true);
    try {
      await api(`/sessions/${encodeURIComponent(sessionId)}/pulse`, {
        method: "POST",
        body: { play_again: play, ease_of_talking: Number(ease) },
      });
    } catch (error) {
      if (!(error instanceof ApiError && error.code === "PULSE_ALREADY_SENT")) {
        setFormError(form, error instanceof ApiError ? error.message : tt("room.errors.generic"));
        setBusy(submit, false);
        return;
      }
    }
    form.hidden = true;
    thanks.hidden = false;
    thanks.focus?.();
  });
}

async function load() {
  setPageState(statePanel, "loading", { message: tt("results.loading") });
  if (!sessionId) {
    setPageState(statePanel, "error", { message: tt("results.missing") });
    return;
  }
  let data;
  try {
    data = await api(`/sessions/${encodeURIComponent(sessionId)}/summary`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return; // redirecting to sign-in
    if (error instanceof ApiError && error.code === "SESSION_ACTIVE") {
      setPageState(statePanel, null);
      $("#still-playing").hidden = false;
      return;
    }
    setPageState(statePanel, "error", { message: tt("results.loadError"), onRetry: load });
    return;
  }
  renderEnding(data);
  renderTeam(data);
  renderYou(data.you);
  renderConnect(data);
  setupPulse(data.pulse_submitted);
  setPageState(statePanel, null);
  $("#results").hidden = false;
}

applyTempStrings();
initAtmosphere();

const user = requireSession();
if (user) {
  mountAppHeader(user, signOut);
  $("#user-initial").textContent = [...user.display_name][0]?.toUpperCase() ?? "";
  load();
}
