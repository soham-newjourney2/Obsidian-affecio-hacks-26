import { ApiError, api } from "../core/api.js";
import { getUser, safeNext, saveSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { t } from "../core/strings.js";
import { applyStrings, clearFormErrors, setBusy, setFieldError, setFormError } from "../core/ui.js";

const next = safeNext(new URLSearchParams(location.search).get("next"));
const tabs = [...document.querySelectorAll('[role="tab"]')];

function selectTab(tab, { focus = false, remember = true } = {}) {
  for (const other of tabs) {
    const selected = other === tab;
    other.setAttribute("aria-selected", String(selected));
    other.tabIndex = selected ? 0 : -1;
    document.getElementById(other.getAttribute("aria-controls")).hidden = !selected;
  }
  if (focus) tab.focus();
  if (remember) {
    history.replaceState(null, "", `${location.pathname}${location.search}#${tab.id.replace("tab-", "")}`);
  }
}

function wireTabs() {
  for (const tab of tabs) {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      selectTab(tabs[(tabs.indexOf(tab) + step + tabs.length) % tabs.length], { focus: true });
    });
  }
  const initial = location.hash === "#register" ? "tab-register" : "tab-login";
  selectTab(document.getElementById(initial), { remember: false });

  // "Already have an account? Sign in" style links under each form.
  for (const link of document.querySelectorAll("[data-switch]")) {
    link.addEventListener("click", () => selectTab(document.getElementById(link.dataset.switch), { focus: true }));
  }
}

// Eye button next to password fields: toggles between hidden and visible text.
function wirePasswordToggles() {
  for (const toggle of document.querySelectorAll(".pw-toggle")) {
    const input = document.getElementById(toggle.getAttribute("aria-controls"));
    toggle.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      toggle.setAttribute("aria-pressed", String(show));
      input.focus();
    });
  }
}

// Browser constraint validation, shown with our own messages. Returns true when valid.
function validate(form) {
  clearFormErrors(form);
  let firstInvalid = null;
  for (const input of form.querySelectorAll("input")) {
    // Passwords are never trimmed, even while shown as text by the eye toggle.
    if (input.type !== "checkbox" && input.name !== "password") input.value = input.value.trim();
    if (input.checkValidity()) continue;
    setFieldError(input, t(input.dataset.invalid));
    firstInvalid ??= input;
  }
  firstInvalid?.focus();
  return firstInvalid === null;
}

// Signed in: onboarding if the case file is missing, else where the user was heading.
async function continueSignedIn() {
  try {
    await api("/users/me/profile");
    location.assign(next);
  } catch (error) {
    if (error instanceof ApiError && error.code === "PROFILE_NOT_FOUND") {
      location.assign("/onboarding.html");
    } else {
      throw error;
    }
  }
}

function showServerError(form, error) {
  if (error.code === "EMAIL_TAKEN") {
    setFieldError(form.querySelector('[name="email"]'), error.message);
    form.querySelector('[name="email"]').focus();
  } else {
    setFormError(form, error instanceof ApiError ? error.message : t("errors.generic"));
  }
}

// Submit buttons ship disabled so nothing can be posted natively before this runs.
function wireForm(form, submit) {
  form.querySelector('[type="submit"]').disabled = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validate(form)) return;
    const button = form.querySelector('[type="submit"]');
    setBusy(button, true);
    try {
      saveSession(await submit(form));
      await continueSignedIn();
    } catch (error) {
      showServerError(form, error);
      setBusy(button, false);
    }
  });
}

function wireForms() {
  wireTabs();
  wirePasswordToggles();
  wireForm(document.querySelector("#panel-login"), (form) =>
    api("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: form.email.value, password: form.password.value },
    }),
  );
  wireForm(document.querySelector("#panel-register"), (form) =>
    api("/auth/register", {
      method: "POST",
      auth: false,
      body: {
        display_name: form.display_name.value,
        email: form.email.value,
        password: form.password.value,
        age_confirmed: form.age_confirmed.checked,
      },
    }),
  );
}

applyStrings();
initAtmosphere();

if (getUser()) {
  // Already signed in in this tab: skip the forms (fall back to them if that fails).
  continueSignedIn().catch(wireForms);
} else {
  wireForms();
}
