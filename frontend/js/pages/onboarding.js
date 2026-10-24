import { ApiError, api, signOut } from "../core/api.js";
import { requireSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { t } from "../core/strings.js";
import {
  applyStrings,
  mountAppHeader,
  setBusy,
  setFieldError,
  setFormError,
  setPageState,
} from "../core/ui.js";

// Section order and wizard step; option lists and limits come from /meta/interests.
// Step 1 is the welcome screen and step 5 reviews everything before saving.
const SECTIONS = [
  { field: "interests", kind: "chips", options: "interests", step: 2 },
  { field: "genres", kind: "chips", options: "genres", step: 2 },
  { field: "activities", kind: "chips", options: "activities", step: 2 },
  { field: "interaction_style", kind: "choices", options: "interaction_styles", step: 3 },
  { field: "preferred_roles", kind: "cards", options: "roles", step: 3 },
  { field: "availability", kind: "chips", options: "availability", step: 3 },
  { field: "shareable_summary", kind: "text", step: 4 },
  { field: "visibility", kind: "choices", options: "visibility", step: 4 },
];
const TOTAL_STEPS = 5;

const form = document.querySelector("#profile-form");
const statePanel = document.querySelector("#page-state");
const progress = document.querySelector("#progress");
const stepButtons = [...document.querySelectorAll("[data-goto]")];

const wizard = { current: 1, furthest: 1, editing: false, meta: null };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function optionInput(type, field, option, className) {
  const label = el("label", className);
  const input = el("input");
  input.type = type;
  input.name = field;
  input.value = option.id;
  const [title, detail] = option.label.split(" — ");
  const text = el("span");
  if (detail) text.append(el("strong", null, title), document.createElement("br"), detail);
  else text.textContent = title;
  label.append(input, text);
  return label;
}

function updateCounter(section, max, min) {
  const boxes = [...section.querySelectorAll('input[type="checkbox"]')];
  const count = boxes.filter((box) => box.checked).length;
  for (const box of boxes) box.disabled = !box.checked && count >= max;
  const counter = section.querySelector(".counter");
  counter.textContent = min === 0 && count === 0 ? t("onboarding.optional") : t("onboarding.counter", { count, max });
}

function buildSection({ field, kind, options }, meta) {
  const section = el("fieldset", "field-group");
  section.id = `field-${field}`;
  section.setAttribute("aria-describedby", `field-${field}-error`);
  const legend = el("legend", "field-group__legend");
  legend.append(el("span", "field-group__title", t(`onboarding.sections.${field}.title`)));
  const counter = el("span", "counter");
  counter.setAttribute("aria-live", "polite");
  legend.append(counter);
  section.append(legend, el("p", "hint", t(`onboarding.sections.${field}.hint`)));

  if (kind === "chips" || kind === "cards") {
    const [min, max] = meta.limits[field];
    const group = el("div", kind === "chips" ? "chips" : "choices");
    const itemClass = kind === "chips" ? "chip" : "choice";
    for (const option of meta[options]) group.append(optionInput("checkbox", field, option, itemClass));
    section.addEventListener("change", () => updateCounter(section, max, min));
    section.append(group);
    section.dataset.min = String(min);
    section.dataset.max = String(max);
  } else if (kind === "choices") {
    counter.remove();
    const choices = el("div", "choices");
    for (const option of meta[options]) choices.append(optionInput("radio", field, option, "choice"));
    section.append(choices);
  } else {
    const textarea = el("textarea", "input");
    textarea.name = field;
    textarea.id = "summary";
    textarea.maxLength = meta.summary_max;
    textarea.rows = 3;
    textarea.setAttribute("aria-label", t(`onboarding.sections.${field}.title`));
    const update = () => {
      counter.textContent = t("onboarding.summaryCounter", { count: textarea.value.length, max: meta.summary_max });
    };
    textarea.addEventListener("input", update);
    section.append(textarea);
    update();
  }

  const error = el("p", "field-error");
  error.id = `field-${field}-error`;
  error.hidden = true;
  section.append(error);
  return section;
}

function fill(profile) {
  for (const { field, kind } of SECTIONS) {
    const value = profile[field];
    if (kind === "text") {
      form.elements[field].value = value ?? "";
      form.elements[field].dispatchEvent(new Event("input"));
      continue;
    }
    const wanted = new Set(Array.isArray(value) ? value : [value]);
    for (const input of form.querySelectorAll(`input[name="${field}"]`)) input.checked = wanted.has(input.value);
    form.querySelector(`#field-${field}`).dispatchEvent(new Event("change"));
  }
}

function readForm() {
  const body = {};
  for (const { field, kind } of SECTIONS) {
    if (kind === "text") body[field] = form.elements[field].value;
    else if (kind === "choices") body[field] = form.querySelector(`input[name="${field}"]:checked`)?.value ?? null;
    else body[field] = [...form.querySelectorAll(`input[name="${field}"]:checked`)].map((input) => input.value);
  }
  return body;
}

// Validates the given sections (all by default). On failure, opens the step holding
// the first invalid section and focuses it. Returns true when everything passes.
function validate(body, sections = SECTIONS) {
  let firstInvalid = null;
  for (const { field, kind, step } of sections) {
    const section = form.querySelector(`#field-${field}`);
    let message = "";
    if (Array.isArray(body[field]) && body[field].length < Number(section.dataset.min)) {
      message = t("onboarding.minimum", { min: section.dataset.min });
    } else if (kind === "choices" && body[field] === null) {
      message = t("onboarding.chooseOne");
    }
    setFieldError(section, message);
    if (message && !firstInvalid) firstInvalid = { section, step };
  }
  if (!firstInvalid) return true;
  if (firstInvalid.step !== wizard.current) showStep(firstInvalid.step);
  firstInvalid.section.scrollIntoView({ block: "center", behavior: "smooth" });
  firstInvalid.section.querySelector("input:not(:disabled), textarea")?.focus({ preventScroll: true });
  return false;
}

// Step 5: a read-only summary of every section, each linking back to its step.
function renderReview() {
  const review = form.querySelector("#review");
  const body = readForm();
  const rows = [];
  for (const { field, kind, options, step } of SECTIONS) {
    if (field === "shareable_summary" && !body[field]) continue;
    const row = el("div", "review__row");
    const term = el("dt", "review__term");
    const edit = el("button", "review__edit", t(`onboarding.sections.${field}.title`));
    edit.type = "button";
    edit.addEventListener("click", () => showStep(step, { focus: true }));
    term.append(edit);
    const detail = el("dd", "review__detail");
    if (kind === "text") {
      detail.append(el("p", "review__quote", body[field]));
    } else {
      const ids = new Set([body[field]].flat().filter(Boolean));
      const labels = wizard.meta[options].filter((o) => ids.has(o.id)).map((o) => o.label.split(" — ")[0]);
      if (labels.length === 0) detail.append(el("span", "review__empty", t("onboarding.nothingChosen")));
      for (const label of labels) detail.append(el("span", "review__chip", label));
    }
    row.append(term, detail);
    rows.push(row);
  }
  review.replaceChildren(...rows);
}

function showStep(step, { focus = false } = {}) {
  wizard.current = step;
  wizard.furthest = Math.max(wizard.furthest, step);
  for (const section of form.querySelectorAll("[data-step]")) {
    section.hidden = Number(section.dataset.step) !== step;
  }
  for (const button of stepButtons) {
    const target = Number(button.dataset.goto);
    button.classList.toggle("is-done", target < step || (target <= wizard.furthest && target !== step && wizard.editing));
    button.disabled = !wizard.editing && target > wizard.furthest;
    if (target === step) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  }

  document.querySelector("#progress-label").textContent = t("onboarding.stepOf", { step, total: TOTAL_STEPS });
  document.querySelector("#progress-fill").style.width = `${(step / TOTAL_STEPS) * 100}%`;
  progress.querySelector('[role="progressbar"]').setAttribute("aria-valuenow", String(step));

  form.querySelector("#back").hidden = step === 1;
  form.querySelector("#next").hidden = step === TOTAL_STEPS;
  form.querySelector("#next-label").textContent = t(step === 1 ? "onboarding.start" : "onboarding.next");
  form.querySelector("#save").hidden = !(wizard.editing || step === TOTAL_STEPS);
  form.querySelector("#quote").hidden = step !== 1;
  form.dataset.step = String(step);

  if (step === TOTAL_STEPS) renderReview();
  if (focus) {
    window.scrollTo({ top: 0, behavior: "smooth" });
    form.querySelector(`#step-${step}-title`)?.focus({ preventScroll: true });
  }
}

function goNext() {
  setFormError(form, "");
  const here = SECTIONS.filter((section) => section.step === wizard.current);
  if (here.length && !validate(readForm(), here)) return;
  showStep(Math.min(wizard.current + 1, TOTAL_STEPS), { focus: true });
}

async function save(event) {
  event.preventDefault();
  // Enter inside a field moves forward while there are steps left (new case files only).
  if (!wizard.editing && wizard.current < TOTAL_STEPS) {
    goNext();
    return;
  }
  setFormError(form, "");
  const body = readForm();
  if (!validate(body)) return;
  const button = form.querySelector("#save");
  setBusy(button, true);
  try {
    await api("/users/me/profile", { method: "PUT", body });
    location.assign("/lobby.html");
  } catch (error) {
    setFormError(form, error instanceof ApiError ? error.message : t("errors.generic"));
    setBusy(button, false);
  }
}

function wireWizard() {
  form.querySelector("#next").addEventListener("click", goNext);
  form.querySelector("#back").addEventListener("click", () => showStep(Math.max(1, wizard.current - 1), { focus: true }));
  for (const button of stepButtons) {
    button.addEventListener("click", () => showStep(Number(button.dataset.goto), { focus: true }));
  }
}

async function load() {
  setPageState(statePanel, "loading", { message: t("onboarding.loading") });
  form.hidden = true;
  progress.hidden = true;
  try {
    const [meta, profile] = await Promise.all([
      api("/meta/interests", { auth: false }),
      api("/users/me/profile").catch((error) => {
        if (error instanceof ApiError && error.code === "PROFILE_NOT_FOUND") return null;
        throw error;
      }),
    ]);
    wizard.meta = meta;
    wizard.editing = profile !== null;
    for (const container of form.querySelectorAll("[data-sections]")) {
      const step = Number(container.dataset.sections);
      container.replaceChildren(...SECTIONS.filter((s) => s.step === step).map((s) => buildSection(s, meta)));
    }
    fill(profile ?? { visibility: "private" });
    form.querySelector("#save").textContent = t(wizard.editing ? "onboarding.submitEdit" : "onboarding.submitNew");
    form.querySelector("#done-lede").textContent = t(wizard.editing ? "onboarding.done.editLede" : "onboarding.done.lede");
    // Editing an existing case file skips the welcome and lets every step be visited.
    wizard.furthest = wizard.editing ? TOTAL_STEPS : 1;
    setPageState(statePanel, null);
    form.hidden = false;
    progress.hidden = false;
    showStep(wizard.editing ? 2 : 1);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return; // redirecting to sign-in
    setPageState(statePanel, "error", { message: t("onboarding.loadError"), onRetry: load });
  }
}

applyStrings();
initAtmosphere();

const user = requireSession();
if (user) {
  mountAppHeader(user, signOut);
  wireWizard();
  form.addEventListener("submit", save);
  load();
}
