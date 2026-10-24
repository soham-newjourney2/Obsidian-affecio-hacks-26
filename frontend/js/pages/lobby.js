import { ApiError, api, signOut } from "../core/api.js";
import { requireSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { STRINGS, t } from "../core/strings.js";
import { applyStrings, mountAppHeader, setPageState, toast } from "../core/ui.js";

const statePanel = document.querySelector("#page-state");
const content = document.querySelector("#lobby-content");

// Warm avatar gradients, cycled by position.
const AVATAR_TONES = [
  ["#c0803f", "#6e3a1c"],
  ["#3f6b52", "#163225"],
  ["#a8393d", "#5c1619"],
  ["#8a6a3c", "#3d2a14"],
];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function avatar(name, index) {
  const node = el("span", "avatar", [...name][0]?.toUpperCase() ?? "");
  const [a, b] = AVATAR_TONES[index % AVATAR_TONES.length];
  node.style.setProperty("--avatar-a", a);
  node.style.setProperty("--avatar-b", b);
  node.setAttribute("aria-hidden", "true");
  return node;
}

// Sample people until matching ships; the section header carries a "Sample" pill.
function renderSamples() {
  const people = STRINGS.lobby.samplePeople.map((person, i) => {
    const item = el("li", "person");
    item.append(avatar(person.name, i), el("span", "person__name", person.name), el("span", "person__note", person.note));
    return item;
  });
  document.querySelector("#people").replaceChildren(...people);

  const active = STRINGS.lobby.sampleActive.map((person, i) => {
    const item = el("li", "active-list__item");
    const who = el("span", "active-list__who");
    who.append(el("span", "active-list__name", person.name), el("span", "active-list__note", person.note));
    item.append(avatar(person.name, i + 1), who, el("span", "active-list__dot"));
    return item;
  });
  document.querySelector("#active").replaceChildren(...active);
}

function wireComingSoon() {
  for (const button of document.querySelectorAll("[data-soon]")) {
    button.addEventListener("click", () => toast(t("lobby.soonToast")));
  }
  document.querySelector("#search").addEventListener("submit", (event) => {
    event.preventDefault();
    toast(t("lobby.soonToast"));
  });
  document.querySelector("#notifications").addEventListener("click", () => toast(t("lobby.noNotifications")));
}

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
  document.querySelector("#welcome").textContent = t("lobby.welcome", { name: user.display_name });
  setPageState(statePanel, null);
  content.hidden = false;
}

applyStrings();
initAtmosphere();
renderSamples();
wireComingSoon();

const user = requireSession();
if (user) {
  mountAppHeader(user, signOut);
  load(user);
}
