// UI primitives: string binding, toasts, modals, button states. Text is set with textContent only.
import { t } from "./strings.js";

export function applyStrings(root = document) {
  for (const el of root.querySelectorAll("[data-s]")) {
    el.textContent = t(el.dataset.s);
  }
  for (const el of root.querySelectorAll("[data-s-label]")) {
    el.setAttribute("aria-label", t(el.dataset.sLabel));
  }
  for (const el of root.querySelectorAll("[data-s-placeholder]")) {
    el.setAttribute("placeholder", t(el.dataset.sPlaceholder));
  }
  for (const el of root.querySelectorAll("[data-s-title]")) {
    el.setAttribute("title", t(el.dataset.sTitle));
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

let toastRegion;

function getToastRegion() {
  if (!toastRegion || !toastRegion.isConnected) {
    toastRegion = el("div", "toast-region");
    toastRegion.setAttribute("role", "status");
    toastRegion.setAttribute("aria-live", "polite");
    document.body.append(toastRegion);
  }
  return toastRegion;
}

const MAX_TOASTS = 3;

export function toast(message, { kind = "info", timeout = 5000 } = {}) {
  const node = el("div", `toast toast--${kind}`, message);
  const region = getToastRegion();
  region.append(node);
  // Bursts (e.g. several companions pinning at once) keep only the newest few.
  while (region.children.length > MAX_TOASTS) region.firstElementChild.remove();
  if (timeout > 0) setTimeout(() => node.remove(), timeout);
  return node;
}

// Resolves with the clicked action's value, or null when dismissed.
export function openModal({ title, body, actions = [{ label: t("common.ok"), value: true, kind: "primary" }] }) {
  const dialog = el("dialog", "modal");
  const inner = el("div", "modal__inner");
  const heading = el("h2", "modal__title", title);
  heading.id = `modal-title-${Date.now()}`;
  dialog.setAttribute("aria-labelledby", heading.id);
  inner.append(heading);
  if (body) inner.append(el("p", "modal__body", body));

  const row = el("div", "modal__actions");
  for (const action of actions) {
    const button = el("button", `btn btn--${action.kind || "ghost"}`, action.label);
    button.type = "button";
    button.addEventListener("click", () => dialog.close(String(actions.indexOf(action))));
    row.append(button);
  }
  inner.append(row);
  dialog.append(inner);
  document.body.append(dialog);

  return new Promise((resolve) => {
    dialog.addEventListener(
      "close",
      () => {
        const index = Number.parseInt(dialog.returnValue, 10);
        resolve(Number.isInteger(index) ? actions[index].value : null);
        dialog.remove();
      },
      { once: true },
    );
    dialog.showModal();
  });
}

export function setBusy(button, busy) {
  button.disabled = busy;
  if (busy) button.setAttribute("aria-busy", "true");
  else button.removeAttribute("aria-busy");
}

// Forms: field errors live in an element whose id is in the input's aria-describedby.
function errorSlot(input) {
  return document.getElementById(`${input.id}-error`);
}

export function setFieldError(input, message) {
  const slot = errorSlot(input);
  input.setAttribute("aria-invalid", message ? "true" : "false");
  if (slot) {
    slot.textContent = message || "";
    slot.hidden = !message;
  }
}

export function clearFormErrors(form) {
  for (const input of form.querySelectorAll("[aria-invalid]")) setFieldError(input, "");
  setFormError(form, "");
}

export function setFormError(form, message) {
  const slot = form.querySelector(".form-error");
  if (!slot) return;
  slot.textContent = message || "";
  slot.hidden = !message;
}

// Page state panel: "loading" | "error" | null (hidden).
export function setPageState(panel, state, { message = "", onRetry } = {}) {
  panel.replaceChildren();
  panel.hidden = state === null;
  if (state === "loading") {
    const spinner = el("div", "spinner");
    spinner.setAttribute("aria-hidden", "true");
    panel.append(spinner, el("p", null, message || t("common.loading")));
  } else if (state === "error") {
    panel.append(el("p", null, message || t("errors.generic")));
    if (onRetry) {
      const retry = el("button", "btn btn--ghost", t("common.retry"));
      retry.type = "button";
      retry.addEventListener("click", onRetry);
      panel.append(retry);
    }
  }
}

export function mountAppHeader(user, onSignOut) {
  const name = document.querySelector("#user-name");
  if (name) name.textContent = user.display_name;
  for (const avatar of document.querySelectorAll("[data-user-initial]")) {
    avatar.textContent = [...user.display_name.trim()][0]?.toUpperCase() ?? "";
  }
  document.querySelector("#sign-out")?.addEventListener("click", (event) => {
    setBusy(event.currentTarget, true);
    onSignOut();
  });
}
