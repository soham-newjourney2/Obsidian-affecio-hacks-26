import { ApiError, api, signOut } from "../core/api.js";
import { requireSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { t } from "../core/strings.js";
import { applyStrings, mountAppHeader, setPageState, toast } from "../core/ui.js";

const statePanel = document.querySelector("#page-state");
const content = document.querySelector("#lobby-content");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

const ART = ["game-card--manor", "game-card--expedition", "game-card--archive"];

function link(href, className, text) {
  const node = el("a", className, text);
  node.href = href;
  return node;
}

function sourceLink(inspiration, className) {
  const node = link(inspiration.source_url, className, t("lobby.original", { language: inspiration.language }));
  node.target = "_blank";
  node.rel = "noopener noreferrer";
  return node;
}

const tableHref = (slug) => `/room.html?story=${encodeURIComponent(slug)}#find-panel`;

async function openCaseFile(story, opener) {
  let detail;
  try {
    detail = await api(`/stories/${encodeURIComponent(story.slug)}`, { auth: false });
  } catch (error) {
    toast(error.message, { kind: "error" });
    return;
  }
  const dialog = el("dialog", "modal story-modal");
  dialog.id = "story-dialog";
  dialog.setAttribute("aria-labelledby", "story-title");
  const inner = el("div", "modal__inner");
  const title = el("h2", "modal__title", detail.title);
  title.id = "story-title";
  const premise = el("p", "modal__body", detail.premise ?? detail.description);
  premise.id = "story-premise";
  inner.append(title, premise);
  if (detail.roles.length) {
    const roles = el("ul", "story-modal__roles");
    for (const role of detail.roles) {
      const item = el("li", "story-modal__role");
      item.append(el("strong", null, role.name), el("span", null, role.focus));
      roles.append(item);
    }
    inner.append(el("h3", "story-modal__subtitle", t("lobby.detail.roles")), roles);
  }
  const { inspiration } = detail;
  const credit = el("p", "story-modal__credit", t("lobby.inspiredBy", inspiration));
  const source = sourceLink(inspiration, "story-modal__source");
  source.id = "story-source";
  inner.append(credit, source);

  const actions = el("div", "modal__actions");
  const close = el("button", "btn btn--ghost", t("lobby.detail.close"));
  close.type = "button";
  close.addEventListener("click", () => dialog.close());
  actions.append(close, link(tableHref(detail.slug), "btn btn--primary", t("lobby.play")));
  inner.append(actions);
  dialog.append(inner);
  dialog.addEventListener("close", () => { dialog.remove(); opener.focus(); }, { once: true });
  document.body.append(dialog);
  dialog.showModal();
}

function storyCard(story, index, caseNumber) {
  const card = el("li", `game-card ${ART[index % ART.length]}`);
  card.dataset.gameCard = "";
  card.dataset.slug = story.slug;
  card.append(
    el("span", `game-status${story.playable ? " game-status--playable" : ""}`,
      story.playable ? t("lobby.caseNumber", { n: caseNumber }) : t("lobby.comingSoon")),
    el("h3", "game-card__title", story.title),
    el("p", "game-card__description", story.description),
  );
  const tags = el("p", "game-card__tags");
  for (const genre of story.genres.slice(0, 2)) tags.append(el("span", "tag", genre));
  tags.append(el("span", "tag", t("lobby.players", { min: story.min_players, max: story.max_players })));
  if (story.est_minutes) tags.append(el("span", "tag", t("lobby.minutes", { n: story.est_minutes })));
  card.append(tags, el("p", "game-card__credit", t("lobby.inspiredBy", story.inspiration)));

  const actions = el("div", "game-card__actions");
  if (story.playable) {
    card.classList.add("game-card--playable");
    const open = el("button", "btn btn--glass btn--sm", t("lobby.openCase"));
    open.type = "button";
    open.addEventListener("click", () => openCaseFile(story, open));
    actions.append(link(tableHref(story.slug), "btn btn--primary btn--sm", t("lobby.play")), open);
  } else {
    card.classList.add("game-card--coming-soon");
    actions.append(sourceLink(story.inspiration, "game-card__source"));
  }
  card.append(actions);
  return card;
}

function renderCatalogue(stories) {
  const grid = document.querySelector("#catalogue");
  if (!stories.length) {
    const empty = el("li", "game-empty", t("lobby.catalogueEmpty"));
    empty.setAttribute("role", "status");
    grid.replaceChildren(empty);
    return;
  }
  // The API lists playable cases first; those are numbered, the rest are "Coming soon".
  let caseNumber = 0;
  grid.replaceChildren(...stories.map((story, i) => storyCard(story, i, story.playable ? ++caseNumber : 0)));
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
      empty = el("p", "game-empty", t("lobby.searchEmpty"));
      empty.id = "search-empty";
      empty.hidden = true;
      document.querySelector("#catalogue").after(empty);
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
  } catch {
    document.querySelector("#catalogue").replaceChildren(el("li", "game-empty", t("lobby.catalogueError")));
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
