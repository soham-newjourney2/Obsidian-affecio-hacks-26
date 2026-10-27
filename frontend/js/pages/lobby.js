import { ApiError, api, signOut } from "../core/api.js";
import { requireSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { STRINGS, t } from "../core/strings.js";
import { applyStrings, mountAppHeader, setPageState, toast } from "../core/ui.js";

const statePanel = document.querySelector("#page-state");
const content = document.querySelector("#lobby-content");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function renderCatalogue(stories) {
  const grid = document.querySelector(".game-grid");
  const heading = document.querySelector("#recommended-title");
  const pill = document.querySelector(".lobby-section__head .sample-pill");
  if (pill) pill.remove();
  grid.replaceChildren();

  if (!stories.length) {
    const empty = el("li", "game-empty", "No stories are available right now. Please try again later.");
    empty.setAttribute("role", "status");
    grid.append(empty);
    return;
  }

  stories.forEach((story, index) => {
    const card = el("li", `game-card ${["game-card--manor", "game-card--expedition", "game-card--archive"][index % 3]}`);
    card.dataset.gameCard = "";
    card.append(el("h3", "game-card__title", story.title));
    card.append(el("p", "game-card__description", story.description));
    const tags = el("p", "game-card__tags");
    (story.genres || []).slice(0, 2).forEach((genre) => tags.append(el("span", "tag", genre)));
    tags.append(el("span", "tag", `${story.min_players}–${story.max_players} players`));
    if (story.est_minutes) tags.append(el("span", "tag", `${story.est_minutes} min`));
    card.append(tags);

    if (story.playable) {
      card.classList.add("game-card--playable");
      card.tabIndex = 0;
      card.setAttribute("role", "link");
      card.setAttribute("aria-label", `Play ${story.title}`);
      const status = el("span", "game-status game-status--playable", "Playable now");
      card.append(status);
      const openStory = () => { location.href = `/room.html?story=${encodeURIComponent(story.slug)}#find-panel`; };
      card.addEventListener("click", openStory);
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openStory(); }
      });
    } else {
      card.classList.add("game-card--coming-soon");
      card.append(el("span", "game-status", "Coming soon"));
      card.setAttribute("aria-label", `${story.title}, coming soon`);
    }
    grid.append(card);
  });
}

function wireLobbyActions() {
  const searchForm = document.querySelector("#search");
  const searchInput = searchForm.querySelector("input[type=search]");
  const filterSearch = () => {
    const query = searchInput.value.trim().toLocaleLowerCase();
    const cards = [...document.querySelectorAll("[data-game-card]")];
    cards.forEach((card) => { card.hidden = Boolean(query) && !card.textContent.toLocaleLowerCase().includes(query); });
    const visible = cards.some((card) => !card.hidden);
    let empty = document.querySelector("#search-empty");
    if (!empty) {
      empty = el("p", "game-empty", "No matching stories. Try another title or genre.");
      empty.id = "search-empty";
      empty.hidden = true;
      document.querySelector(".game-grid").insertAdjacentElement("afterend", empty);
    }
    empty.hidden = !query || visible;
  };
  searchForm.addEventListener("submit", (event) => { event.preventDefault(); filterSearch(); });
  searchInput.addEventListener("input", filterSearch);
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
  try {
    const stories = await api("/stories", { auth: false });
    renderCatalogue(Array.isArray(stories) ? stories : []);
  } catch (error) {
    const grid = document.querySelector(".game-grid");
    grid.replaceChildren(el("li", "game-empty", "We couldn't load the story catalogue. Refresh to try again."));
    console.error("Story catalogue failed to load", error);
  }
  setPageState(statePanel, null);
  content.hidden = false;
}

applyStrings();
initAtmosphere();
wireLobbyActions();

const user = requireSession();
if (user) {
  mountAppHeader(user, signOut);
  load(user);
}
