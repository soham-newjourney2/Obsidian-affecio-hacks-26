// UI primitives: string binding, toasts, modals, button states. Text is set with textContent only.
import { t } from "./strings.js";

export function applyStrings(root = document) {
  for (const el of root.querySelectorAll("[data-s]")) {
    el.textContent = t(el.dataset.s);
  }
  for (const el of root.querySelectorAll("[data-s-label]")) {
    el.setAttribute("aria-label", t(el.dataset.sLabel));
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

export function toast(message, { kind = "info", timeout = 5000 } = {}) {
  const node = el("div", `toast toast--${kind}`, message);
  getToastRegion().append(node);
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
