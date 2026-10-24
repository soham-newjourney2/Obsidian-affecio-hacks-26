// Story room: renders one member's game projection (`view` from the server) and plays the
// small moments (typewriter, clue unlocked, pins, decisions, the ending stamp).
// Everything is rebuilt from the latest view, so a reconnect or refresh simply re-renders.
import { motionReduced } from "../core/fx.js";
import { tt } from "../core/strings-temp.js";
import { toast } from "../core/ui.js";

const TYPE_MS = 18;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function svg(tag, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

export function createGame({ onVote, onShare, onHint }) {
  const $ = (s) => document.querySelector(s);
  let view = null;
  let names = new Map(); // member_id -> display name
  let lastScene = null;
  let typing = null;
  let countdown = null;

  // ---- narration ----------------------------------------------------------------------

  function stopTyping() {
    clearInterval(typing);
    typing = null;
    $("#narration-skip").hidden = true;
  }

  function narrate(text, animate) {
    stopTyping();
    const visual = $("#narration");
    $("#narration-sr").textContent = text; // screen readers get it whole, once
    if (!animate || motionReduced()) {
      visual.textContent = text;
      return;
    }
    visual.textContent = "";
    let i = 0;
    $("#narration-skip").hidden = false;
    typing = setInterval(() => {
      i += 2;
      visual.textContent = text.slice(0, i);
      if (i >= text.length) stopTyping();
    }, TYPE_MS);
  }

  // ---- pieces ---------------------------------------------------------------------------

  function renderProgress(chapter) {
    $("#chapter-label").textContent = tt("game.story.chapter", { index: chapter.index, total: chapter.total });
    $("#chapter-dots").replaceChildren(
      ...Array.from({ length: chapter.total }, (_, i) => {
        const dot = el("li", "game-progress__dot");
        if (i + 1 < chapter.index) dot.classList.add("is-done");
        if (i + 1 === chapter.index) dot.classList.add("is-current");
        return dot;
      }),
    );
    $("#chapter-title").textContent = chapter.title;
    $("#objective").textContent = chapter.objective;
  }

  function renderRole(you) {
    const box = $("#game-role");
    box.replaceChildren();
    for (const role of you.roles) {
      box.append(el("p", "game-role__name", tt("game.clues.role", { role: role.name })));
      box.append(el("p", "game-role__focus", role.focus));
    }
  }

  function renderPrivate(clues, highlight) {
    const list = $("#private-clues");
    list.replaceChildren(
      ...clues.map((clue) => {
        const item = el("li", `game-clue${clue.shared ? " is-shared" : ""}`);
        item.dataset.clue = clue.id;
        if (highlight?.has(clue.id)) item.classList.add("is-new");
        // Private vs shared: icon + word, never colour alone.
        const tag = el("p", "game-clue__tag", `${clue.shared ? "📌" : "🔒"} ${tt(clue.shared ? "game.clues.shared" : "game.clues.private")}`);
        item.append(tag, el("p", "game-clue__text", clue.text));
        if (!clue.shared && view.status === "active") {
          const share = el("button", "btn btn--ghost btn--sm", tt("game.clues.share"));
          share.type = "button";
          share.addEventListener("click", () => onShare(clue.id));
          item.append(share);
        }
        return item;
      }),
    );
    $("#private-empty").hidden = clues.length > 0;
  }

  function renderBoard(pins, highlight) {
    const list = $("#board");
    list.replaceChildren(
      ...pins.map((pin, i) => {
        const item = el("li", "game-pin");
        item.dataset.clue = pin.id;
        item.style.setProperty("--tilt", `${[-1.6, 1.2, -0.6, 1.8, -1.1][i % 5]}deg`);
        if (highlight?.has(pin.id)) item.classList.add("is-new");
        const by = pin.by ? tt("game.board.sharedBy", { name: names.get(pin.by) ?? "?" }) : tt("game.board.public");
        item.append(el("p", "game-pin__by", `📌 ${by}`), el("p", "game-pin__text", pin.text));
        return item;
      }),
    );
    $("#board-empty").hidden = pins.length > 0;
    requestAnimationFrame(drawStrings);
  }

  // Red string between consecutive pins.
  function drawStrings() {
    const surface = $("#board-surface");
    const strings = $("#board-strings");
    const box = surface.getBoundingClientRect();
    strings.setAttribute("viewBox", `0 0 ${Math.max(1, box.width)} ${Math.max(1, box.height)}`);
    const pins = [...surface.querySelectorAll(".game-pin")].map((pin) => {
      const r = pin.getBoundingClientRect();
      return [r.left - box.left + r.width / 2, r.top - box.top + 14];
    });
    strings.replaceChildren(
      ...pins.slice(1).map(([x, y], i) => {
        const [px, py] = pins[i];
        const sag = Math.min(40, Math.hypot(x - px, y - py) / 6);
        return svg("path", { d: `M${px},${py} Q${(px + x) / 2},${(py + y) / 2 + sag} ${x},${y}`, class: "game-string" });
      }),
    );
  }

  function choiceLabel(decision, choice) {
    return decision.id === "continue" ? tt("game.decision.continueLabel") : choice.label;
  }

  function renderDecision(decision) {
    const box = $("#decision");
    clearInterval(countdown);
    if (!decision) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    $("#decision-prompt").textContent = decision.id === "continue" ? tt("game.decision.continuePrompt") : decision.prompt;
    const status = () => {
      const parts = [tt("game.decision.status", { voted: decision.voted.length, seats: decision.seats })];
      if (decision.deadline) {
        const seconds = Math.max(0, Math.ceil(decision.deadline - Date.now() / 1000));
        parts.push(tt("game.decision.deadline", { seconds }));
      }
      $("#decision-status").textContent = parts.join(" · ");
    };
    status();
    if (decision.deadline) countdown = setInterval(status, 1000);

    $("#choices").replaceChildren(
      ...decision.choices.map((choice) => {
        const mine = decision.your_vote === choice.id;
        const count = decision.tally[choice.id] ?? 0;
        const item = el("li", "game-choice");
        const button = el("button", `game-seal${mine ? " is-mine" : ""}`);
        button.type = "button";
        button.dataset.choice = choice.id;
        button.setAttribute("aria-pressed", String(mine));
        button.append(el("span", "game-seal__label", choiceLabel(decision, choice)));
        const meta = el("span", "game-seal__meta", tt("game.decision.votes", { count }));
        if (mine) meta.textContent += ` · ${tt("game.decision.yourVote")}`;
        button.append(meta);
        button.addEventListener("click", () => {
          if (!mine) onVote(choice.id);
        });
        item.append(button);
        return item;
      }),
    );
  }

  function renderHints() {
    const left = view.hints_left;
    const button = $("#hint-request");
    button.textContent = left > 0 ? tt("game.hints.request", { left }) : tt("game.hints.none");
    button.disabled = left === 0 || view.status !== "active";
    $("#hints").replaceChildren(
      ...view.hints.map((hint) => {
        const item = el("li", "game-hint");
        item.append(el("strong", null, tt("game.hints.level", { level: hint.level })), el("span", null, ` ${hint.text}`));
        return item;
      }),
    );
  }

  function renderEnding(ending) {
    const box = $("#ending");
    box.hidden = !ending;
    if (!ending) return;
    $("#ending-stamp").textContent = tt(`game.ending.${ending.kind}`);
    $("#ending-stamp").dataset.kind = ending.kind;
    $("#ending-title").textContent = ending.title;
    $("#ending-text").textContent = ending.text;
    $("#ending-solution").textContent = ending.solution;
  }

  // ---- public ---------------------------------------------------------------------------

  function render(next, { event = null, payload = {} } = {}) {
    const previous = view;
    view = next;
    const sceneChanged = lastScene !== view.chapter.scene_id;
    lastScene = view.chapter.scene_id;

    const newClues = new Set(
      previous ? view.private_clues.map((c) => c.id).filter((id) => !previous.private_clues.some((p) => p.id === id)) : [],
    );
    const newPins = new Set(
      previous ? view.board.map((p) => p.id).filter((id) => !previous.board.some((q) => q.id === id)) : [],
    );

    renderProgress(view.chapter);
    if (sceneChanged) {
      const story = $("#game-story");
      story.classList.remove("is-entering");
      void story.offsetWidth; // restart the transition
      story.classList.add("is-entering");
      narrate(view.chapter.narration, Boolean(previous) || event === "game.scene");
    }
    renderRole(view.you);
    renderPrivate(view.private_clues, newClues);
    renderBoard(view.board, newPins);
    renderDecision(view.status === "active" ? view.decision : null);
    renderHints();
    renderEnding(view.ending);

    if (event === "game.clue.private" && newClues.size) toast(tt("game.clues.unlocked"), { kind: "success" });
    if (event === "game.board.updated" && payload.by && payload.by !== view.you.member_id && newPins.size) {
      toast(tt("game.board.pinned", { name: names.get(payload.by) ?? "?" }));
    }
    if (event === "game.decision.resolved" && previous?.decision) {
      const choice = previous.decision.choices.find((c) => c.id === payload.choice_id);
      if (choice) toast(tt("game.decision.resolved", { label: choiceLabel(previous.decision, choice) }));
    }
    if (event === "game.vote.tally" && payload.tie) toast(tt("game.decision.tie"));
  }

  function setNames(members) {
    names = new Map(members.map((m) => [m.member_id, m.display_name]));
  }

  function current() {
    return view;
  }

  $("#narration-skip").addEventListener("click", () => {
    stopTyping();
    $("#narration").textContent = view?.chapter.narration ?? "";
  });
  $("#hint-request").addEventListener("click", () => onHint());
  window.addEventListener("resize", () => requestAnimationFrame(drawStrings));

  // Mobile tabs.
  const tabs = [...document.querySelectorAll(".game-tabs__tab")];
  function selectTab(tab, focus = false) {
    for (const other of tabs) {
      const on = other === tab;
      other.setAttribute("aria-selected", String(on));
      other.tabIndex = on ? 0 : -1;
      document.getElementById(other.getAttribute("aria-controls")).classList.toggle("is-tab-active", on);
    }
    if (focus) tab.focus();
    requestAnimationFrame(drawStrings);
  }
  for (const tab of tabs) {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      selectTab(tabs[(tabs.indexOf(tab) + step + tabs.length) % tabs.length], true);
    });
  }
  selectTab(tabs[0]);

  return { render, setNames, current };
}
