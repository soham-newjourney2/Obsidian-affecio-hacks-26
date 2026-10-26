// Every user-facing string lives here (D14). Look up with t("dotted.key").

export const STRINGS = Object.freeze({
  common: {
    brand: "ECHO",
    tagline: "Stories bring people closer.",
    skip: "Skip to content",
    home: "ECHO home",
    close: "Close",
    ok: "OK",
    cancel: "Cancel",
    retry: "Try again",
    loading: "Loading…",
    sample: "Sample",
    sampleHint: "Sample content — the live catalogue and matching arrive in the next build.",
  },
  nav: {
    label: "Account",
    profile: "Edit profile",
    signOut: "Sign out",
    lobby: "Lobby",
  },
  errors: {
    network: "Can't reach ECHO. Check your connection and try again.",
    generic: "Something went wrong. Please try again.",
    RATE_LIMITED: "Too many attempts. Please wait a few minutes and try again.",
    INVALID_CREDENTIALS: "Incorrect email or password.",
    EMAIL_TAKEN: "An account with this email already exists. Try signing in instead.",
    VALIDATION_ERROR: "Some details need another look.",
    UNAUTHORIZED: "Your session has ended. Please sign in again.",
  },
  // Shared story blurbs (landing shelf + lobby recommendations). Placeholders until the catalogue API lands.
  stories: {
    manor: { title: "Whispers in the Manor", genre: "Mystery", players: "4–⁠6 players", level: "Intermediate" },
    expedition: { title: "The Lost Expedition", genre: "Adventure", players: "3–⁠5 players", level: "Beginner" },
    archive: { title: "Shadows of the Archive", genre: "Mystery", players: "4–⁠6 players", level: "Intermediate" },
  },
  landing: {
    nav: {
      label: "Main",
      home: "Home",
      features: "Features",
      how: "How it works",
      stories: "Stories",
      community: "Community",
      signIn: "Sign in",
      start: "Get Started",
    },
    hero: {
      titleLead: "Find Your People Through",
      titleAccent: "Stories",
      tagline: "Play. Solve. Connect.",
      lede: "ECHO is an AI-powered social discovery platform where you meet new people through cooperative, story-driven mystery games.",
      cta: "Get Started",
      secondary: "Learn More",
    },
    features: {
      label: "What you get",
      story: "Story-Driven Games",
      people: "Meet Like-Minded People",
      gm: "AI Game Master",
      connect: "Build Real Connections",
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
    stories: {
      eyebrow: "On the shelf",
      title: "Stories waiting to be solved",
      lede: "Each case is a short, cooperative mystery for a small table, narrated by an AI game master.",
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
    title: "Sign in or create an account",
    story: {
      label: "About ECHO",
      titleLead: "Find Your People Through",
      titleAccent: "Stories",
      tagline: "Play. Solve. Connect.",
      body: "ECHO is an AI-powered social discovery platform where you meet new people through cooperative, story-driven mystery games.",
    },
    tabs: {
      label: "Account",
      login: "Sign in",
      register: "Create account",
    },
    fields: {
      email: "Email",
      password: "Password",
      displayName: "Display name",
      displayNameHint: "2–24 characters. This is what your group sees.",
      passwordHint: "At least 10 characters.",
      age: "I confirm I am 18 or older.",
      emailPlaceholder: "you@example.com",
      passwordPlaceholder: "Your password",
      newPasswordPlaceholder: "Choose a password",
      displayNamePlaceholder: "e.g. Saswata",
      showPassword: "Show password",
    },
    invalid: {
      email: "Enter a valid email address.",
      password: "Enter your password.",
      newPassword: "Use 10–128 characters.",
      displayName: "Use 2–24 letters, numbers, spaces or . ' - _",
      age: "ECHO is for adults. Please confirm you are 18 or older.",
    },
    login: {
      heading: "Welcome back",
      lede: "Your table is waiting.",
      submit: "Sign in",
      switchPrompt: "New to ECHO?",
      switchAction: "Create an account",
    },
    register: {
      heading: "Create your account",
      lede: "One account, then a short case file about you. No personality tests.",
      submit: "Create account",
      switchPrompt: "Already have an account?",
      switchAction: "Sign in instead",
    },
  },
  onboarding: {
    eyebrow: "Your case file",
    title: "Your case file",
    stepOf: "Step {step} of {total}",
    stepsLabel: "Case file steps",
    progressLabel: "Case file progress",
    loading: "Opening your case file…",
    loadError: "We couldn't open your case file.",
    counter: "{count} of {max} chosen",
    minimum: "Choose at least {min}.",
    chooseOne: "Choose one.",
    optional: "Optional",
    nothingChosen: "Nothing chosen",
    back: "Back",
    next: "Continue",
    start: "Let's continue",
    steps: {
      welcome: { title: "Welcome", sub: "Let's get started" },
      interests: { title: "Your Interests", sub: "What do you enjoy?" },
      playstyle: { title: "Your Playstyle", sub: "How do you like to play?" },
      about: { title: "A Bit About You", sub: "Write a short case file" },
      done: { title: "You're In!", sub: "Time to explore" },
    },
    welcome: {
      title: "Welcome to ECHO!",
      lede: "You're about to join a community that connects through stories, mysteries and shared adventures. A few quick questions help us find you a good table.",
      cards: {
        games: { title: "Cooperative Mystery Games", body: "Solve intriguing stories together with new people." },
        people: { title: "Meet Amazing People", body: "Find others who share your interests and vibe." },
        gm: { title: "AI Game Master", body: "Get dynamic, personalised stories powered by AI." },
      },
      quote: "“Every great connection starts with a good story.”",
    },
    interests: {
      title: "What pulls you in?",
      lede: "The things you love, the stories you'd pick, and what you might do once a case is closed. No scores, no personality tests.",
    },
    playstyle: {
      title: "How do you like to play?",
      lede: "Your style at the table, the roles you'd enjoy, and when you're usually free.",
    },
    about: {
      title: "A bit about you",
      lede: "A short line for the people you choose to connect with, and who gets to see your case file.",
    },
    done: {
      title: "You're in!",
      lede: "Here's your case file. Save it and the lobby opens; you can change any of this later.",
      editLede: "Here's your case file. Save your changes, or jump back to any step.",
    },
    sections: {
      interests: { title: "Interests", hint: "Pick what you'd happily talk about for an evening." },
      genres: { title: "Story genres", hint: "Which kinds of cases pull you in?" },
      activities: { title: "Things you'd do after a case", hint: "Only used if you and someone both choose to stay in touch." },
      interaction_style: { title: "How you play", hint: "There's no best answer; good tables mix all three." },
      preferred_roles: { title: "Roles you'd enjoy", hint: "Up to two. You may not always get them." },
      availability: { title: "When you're free", hint: "Rough windows are enough." },
      visibility: { title: "Who sees this", hint: "You're in control. Private is the default." },
      shareable_summary: { title: "A line about you", hint: "Shown only to people you choose to connect with." },
    },
    summaryCounter: "{count} / {max}",
    submitNew: "Save and continue",
    submitEdit: "Save changes",
    saved: "Case file saved.",
  },
  lobby: {
    eyebrow: "The lobby",
    welcome: "Welcome, {name}.",
    navLabel: "Lobby navigation",
    nav: {
      home: "Home",
      find: "Find a Game",
      games: "My Games",
      community: "Community",
      messages: "Messages",
      profile: "Profile",
    },
    soonToast: "That opens with the case catalogue in the next build.",
    searchLabel: "Search",
    searchPlaceholder: "Search for people, games or interests…",
    notifications: "Notifications",
    noNotifications: "No new notifications.",
    hero: {
      title: "A New Story Awaits You",
      body: "Join a game, meet new people, and be part of an unforgettable story.",
      cta: "Find a Game",
    },
    recommended: "Recommended Games for You",
    people: "People You Might Like",
    active: "Active Now",
    editProfile: "Edit your case file",
    samplePeople: [
      { name: "Aanya", note: "Loves mysteries" },
      { name: "Rohan", note: "Fantasy & lore" },
      { name: "Meera", note: "Story enthusiast" },
      { name: "Arjun", note: "Puzzle solver" },
    ],
    sampleActive: [
      { name: "Kavya", note: "In a game" },
      { name: "Nilay", note: "Looking for a team" },
      { name: "Ira", note: "Online" },
    ],
  },
});

// t("lobby.welcome", { name }) fills {name}-style placeholders.
export function t(key, params) {
  const value = key.split(".").reduce((node, part) => (node == null ? node : node[part]), STRINGS);
  if (typeof value !== "string") {
    console.warn(`Missing string: ${key}`);
    return key;
  }
  if (!params) return value;
  return value.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

