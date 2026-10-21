// Every user-facing string lives here (D14). Look up with t("dotted.key").

export const STRINGS = Object.freeze({
  common: {
    brand: "ECHO",
    skip: "Skip to content",
    home: "ECHO home",
    close: "Close",
    ok: "OK",
    cancel: "Cancel",
  },
  landing: {
    nav: {
      label: "Main",
      how: "How it works",
      start: "Start a case",
    },
    hero: {
      eyebrow: "A cooperative mystery for 3–⁠4 players", // word joiner keeps "3–4" together
      title: "Every clue is half a conversation.",
      lede: "Each of you holds a different piece of the case. It only opens when you talk, share what you know, and decide together.",
      cta: "Start a case",
      secondary: "How it works",
    },
    how: {
      eyebrow: "The case file",
      title: "How it works",
      one: {
        label: "Chapter I",
        title: "Find your table",
        body: "Join a small group matched on shared interests, or invite friends with a private code.",
      },
      two: {
        label: "Chapter II",
        title: "Hold your own clues",
        body: "Everyone sees something different. Share what you know, test theories and vote on every move.",
      },
      three: {
        label: "Chapter III",
        title: "Close the case, keep the company",
        body: "After the ending, reflect in private. Stay in touch only if you both choose to.",
      },
    },
    audience: {
      title: "New here? That's the point.",
      body: "Made for students and newcomers who'd like to meet people without the pressure of a one-to-one chat. The story gives you something to talk about; the people are why you stay.",
      cta: "Open your first case",
    },
    footer: {
      stories: "Stories adapted from public-domain classics.",
      age: "For players 18 and over.",
    },
  },
  auth: {
    soon: {
      eyebrow: "The door is nearly open",
      title: "Accounts are on their way.",
      body: "Sign-up and sign-in arrive in the next build. Until then, the case file stays sealed.",
      back: "Back to the start",
    },
  },
});

export function t(key) {
  const value = key.split(".").reduce((node, part) => (node == null ? node : node[part]), STRINGS);
  if (typeof value !== "string") {
    console.warn(`Missing string: ${key}`);
    return key;
  }
  return value;
}
