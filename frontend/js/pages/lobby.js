import { ApiError, api, signOut } from "../core/api.js";
import { requireSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { t } from "../core/strings.js";
import { applyStrings, mountAppHeader, setPageState, toast } from "../core/ui.js";

const statePanel = document.querySelector("#page-state");
const content = document.querySelector("#lobby-content");
const grid = document.querySelector("#catalogue");
const dialog = document.querySelector("#story-dialog");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function inspiredBy(story) {
  const { title, author, year } = story.inspiration;
  return t("lobby.inspiredBy", { title, author, year });
}

async function openStory(story, number, trigger) {
  trigger.setAttribute("aria-busy", "true");
  let detail;
  try {
    detail = await api(`/stories/${encodeURIComponent(story.slug)}`, { auth: false });
  } catch (error) {
    trigger.removeAttribute("aria-busy");
    toast(error instanceof ApiError ? error.message : t("errors.generic"), { kind: "error" });
    return;
  }
  trigger.removeAttribute("aria-busy");
  dialog.querySelector("#story-number").textContent = t("lobby.caseNumber", { n: number });
  dialog.querySelector("#story-title").textContent = detail.title;
  dialog.querySelector("#story-inspiration").textContent = inspiredBy(detail);
  dialog.querySelector("#story-premise").textContent = detail.premise ?? detail.description;
  dialog.querySelector("#story-roles").replaceChildren(
    ...detail.roles.map((role) => {
      const item = el("li", "story-modal__role");
      item.append(el("strong", null, role.name), el("span", null, role.focus));
      return item;
    }),
  );
  const source = dialog.querySelector("#story-source");
  source.href = detail.inspiration.source_url;
  source.textContent = t("lobby.detail.original", { language: detail.inspiration.language });
  dialog.showModal();
}

function storyCard(story, number, genreLabels) {
  const item = el("li", `story-card case-card${story.playable ? " story-card--open" : " story-card--soon"}`);
  item.dataset.slug = story.slug;
  // Coming-soon cards say so with a visual stamp; the label carries it for screen readers.
  const labelClass = story.playable ? "case-card__label" : "case-card__label visually-hidden";
  item.append(el("span", labelClass, story.playable ? t("lobby.caseNumber", { n: number }) : t("lobby.comingSoon")));
  item.append(el("h3", "case-card__title", story.title));
  item.append(el("p", "case-card__body", story.description));

  const tags = el("ul", "story-card__tags");
  for (const genre of story.genres) tags.append(el("li", "story-card__tag", genreLabels.get(genre) ?? genre));
  tags.append(el("li", "story-card__tag", t("lobby.players", { min: story.min_players, max: story.max_players })));
  if (story.est_minutes) tags.append(el("li", "story-card__tag", t("lobby.minutes", { n: story.est_minutes })));
  item.append(tags);
  item.append(el("p", "story-card__inspiration", inspiredBy(story)));

  if (story.playable) {
    const open = el("button", "btn btn--seal story-card__open", t("lobby.openCase"));
    open.type = "button";
    open.addEventListener("click", () => openStory(story, number, open));
    item.append(open);
  } else {
    const stamp = el("span", "story-card__stamp", t("lobby.comingSoon"));
    stamp.setAttribute("aria-hidden", "true");
    item.append(stamp);
  }
  return item;
}

function renderCatalogue(stories, meta) {
  const genreLabels = new Map(meta.genres.map((g) => [g.id, g.label]));
  if (stories.length === 0) {
    grid.replaceChildren(el("li", "catalogue__empty", t("lobby.catalogueEmpty")));
    return;
  }
  let caseNumber = 0;
  grid.replaceChildren(...stories.map((story) => storyCard(story, story.playable ? ++caseNumber : null, genreLabels)));
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
  try {
    const [stories, meta] = await Promise.all([
      api("/stories", { auth: false }),
      api("/meta/interests", { auth: false }),
    ]);
    renderCatalogue(stories, meta);
  } catch {
    setPageState(statePanel, "error", { message: t("lobby.catalogueError"), onRetry: () => load(user) });
    return;
  }
  document.querySelector("#welcome").textContent = t("lobby.welcome", { name: user.display_name });
  setPageState(statePanel, null);
  content.hidden = false;
}

applyStrings();
initAtmosphere();
dialog.querySelector("#story-close").addEventListener("click", () => dialog.close());

const user = requireSession();
if (user) {
  mountAppHeader(user, signOut);
  load(user);
}
