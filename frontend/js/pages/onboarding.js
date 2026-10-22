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

// Section order on the page; option lists and limits come from /meta/interests.
const SECTIONS = [
  { field: "interests", kind: "chips", options: "interests" },
  { field: "interaction_style", kind: "choices", options: "interaction_styles" },
  { field: "genres", kind: "chips", options: "genres" },
  { field: "preferred_roles", kind: "cards", options: "roles" },
  { field: "availability", kind: "chips", options: "availability" },
  { field: "activities", kind: "chips", options: "activities" },
  { field: "visibility", kind: "choices", options: "visibility" },
  { field: "shareable_summary", kind: "text" },
];

const form = document.querySelector("#profile-form");
const statePanel = document.querySelector("#page-state");

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

function validate(body) {
  let firstInvalid = null;
  for (const { field, kind } of SECTIONS) {
    const section = form.querySelector(`#field-${field}`);
    let message = "";
    if (Array.isArray(body[field]) && body[field].length < Number(section.dataset.min)) {
      message = t("onboarding.minimum", { min: section.dataset.min });
    } else if (kind === "choices" && body[field] === null) {
      message = t("onboarding.chooseOne");
    }
    setFieldError(section, message);
    if (message && !firstInvalid) firstInvalid = section;
  }
  firstInvalid?.querySelector("input:not(:disabled)")?.focus();
  return firstInvalid === null;
}

async function save(event) {
  event.preventDefault();
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

async function load() {
  setPageState(statePanel, "loading", { message: t("onboarding.loading") });
  form.hidden = true;
  try {
    const [meta, profile] = await Promise.all([
      api("/meta/interests", { auth: false }),
      api("/users/me/profile").catch((error) => {
        if (error instanceof ApiError && error.code === "PROFILE_NOT_FOUND") return null;
        throw error;
      }),
    ]);
    const sections = form.querySelector("#sections");
    sections.replaceChildren(...SECTIONS.map((section) => buildSection(section, meta)));
    fill(profile ?? { visibility: "private" });
    form.querySelector("#save").textContent = t(profile ? "onboarding.submitEdit" : "onboarding.submitNew");
    setPageState(statePanel, null);
    form.hidden = false;
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
  form.addEventListener("submit", save);
  load();
}
