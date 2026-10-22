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
}

// Browser constraint validation, shown with our own messages. Returns true when valid.
function validate(form) {
  clearFormErrors(form);
  let firstInvalid = null;
  for (const input of form.querySelectorAll("input")) {
    if (input.type !== "checkbox") input.value = input.type === "password" ? input.value : input.value.trim();
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
