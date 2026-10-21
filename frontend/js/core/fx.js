// Atmosphere (fog, grain, vignette, gaslight flicker) and the reduced-motion switch.
const reducedQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

export function motionReduced() {
  return reducedQuery.matches;
}

// GSAP is optional: pages must look complete without it.
export function canAnimate() {
  return !motionReduced() && typeof window.gsap !== "undefined";
}

function syncMotionFlag() {
  document.documentElement.dataset.motion = motionReduced() ? "reduced" : "full";
}

function addLayer(name) {
  if (document.querySelector(`.fx-${name}`)) return;
  const layer = document.createElement("div");
  layer.className = `fx-layer fx-${name}`;
  layer.setAttribute("aria-hidden", "true");
  document.body.prepend(layer);
}

export function initAtmosphere() {
  syncMotionFlag();
  addLayer("vignette");
  addLayer("fog");
  addLayer("grain");

  reducedQuery.addEventListener("change", () => {
    syncMotionFlag();
    // Jump running timelines to their end state so nothing is left half-hidden.
    if (motionReduced() && window.gsap) {
      for (const child of window.gsap.globalTimeline.getChildren(true, true, true)) {
        child.progress(1).kill();
      }
    }
  });
}
