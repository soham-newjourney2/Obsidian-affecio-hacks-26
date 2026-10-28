import { api } from "../core/api.js";
import { canAnimate, initAtmosphere } from "../core/fx.js";
import { t } from "../core/strings.js";
import { applyStrings } from "../core/ui.js";

const ART = ["story-card--manor", "story-card--expedition", "story-card--archive"];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

// The shelf shows the real catalogue (rule 13); with nothing to show, the section hides.
async function renderShelf() {
  const section = document.querySelector("#stories");
  let stories = [];
  try {
    stories = await api("/stories", { auth: false });
  } catch {
    // hidden below
  }
  if (!Array.isArray(stories) || !stories.length) {
    section.hidden = true;
    return;
  }
  const cards = stories.slice(0, 3).map((story, i) => {
    const card = el("li", `story-card ${ART[i % ART.length]}`);
    card.dataset.card = "";
    const tags = el("p", "story-card__tags");
    tags.append(
      el("span", "tag", story.playable ? t("lobby.playable") : t("lobby.comingSoon")),
      el("span", "tag", t("lobby.players", { min: story.min_players, max: story.max_players })),
    );
    card.append(el("h3", "story-card__title", story.title), tags);
    return card;
  });
  document.querySelector("#story-shelf").replaceChildren(...cards);
}

function playIntro(gsap) {
  gsap
    .timeline({ defaults: { ease: "power3.out" } })
    .from(".site-header", { opacity: 0, y: -12, duration: 0.6 })
    .from(".hero__art", { opacity: 0, scale: 1.04, duration: 1.6, ease: "power2.out" }, 0)
    .from(".hero [data-reveal]", { opacity: 0, y: 28, duration: 0.9, stagger: 0.12 }, "-=1.1")
    .from("[data-feature]", { opacity: 0, y: 40, duration: 0.7, stagger: 0.08 }, "-=0.5");
}

function revealCards(gsap) {
  const cards = document.querySelectorAll("[data-card]");
  if (!("IntersectionObserver" in window) || cards.length === 0) return;

  gsap.set(cards, { opacity: 0, y: 36 });
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer.unobserve(entry.target);
        gsap.to(entry.target, { opacity: 1, y: 0, duration: 0.8, ease: "power3.out" });
      }
    },
    { threshold: 0.2 },
  );
  for (const card of cards) observer.observe(card);
}

applyStrings();
initAtmosphere();

const shelf = renderShelf();
if (canAnimate()) {
  playIntro(window.gsap);
  shelf.then(() => revealCards(window.gsap));
}
