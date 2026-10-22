import { ApiError, api, signOut } from "../core/api.js";
import { requireSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { t } from "../core/strings.js";
import { applyStrings, mountAppHeader, setPageState } from "../core/ui.js";

const statePanel = document.querySelector("#page-state");
const content = document.querySelector("#lobby-content");

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

const user = requireSession();
if (user) {
  mountAppHeader(user, signOut);
  load(user);
}
