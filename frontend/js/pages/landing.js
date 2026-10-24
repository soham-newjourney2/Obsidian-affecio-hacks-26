import { canAnimate, initAtmosphere } from "../core/fx.js";
import { applyStrings } from "../core/ui.js";

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

if (canAnimate()) {
  playIntro(window.gsap);
  revealCards(window.gsap);
}
