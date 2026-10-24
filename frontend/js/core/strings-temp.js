// TEMPORARY string table for pages built while teammates own strings.js (plan rule 18).
// Teammates fold these into strings.js; until then use tt("room.key") and data-st="room.key".

export const TEMP_STRINGS = Object.freeze({
  common: {
    brand: "ECHO",
    skip: "Skip to content",
    signOut: "Sign out",
    navLabel: "Main",
    lobby: "Lobby",
    table: "Your table",
    profile: "Profile",
  },
  room: {
    title: "Your table",
    loading: "Opening your table…",
    loadError: "We couldn't open this table.",
    gate: {
      eyebrow: "Gather your table",
      title: "Three or four people, one case.",
      lede: "Start a table and share the code, or join one with a code from your host.",
      createTitle: "Start a table",
      storyLabel: "Case",
      noStories: "No case is open right now.",
      create: "Start the table",
      joinTitle: "Join with a code",
      codeLabel: "Invite code",
      codeHint: "Eight letters and numbers, from your host.",
      codeInvalid: "Enter the 8-character code.",
      join: "Join the table",
    },
    status: {
      connecting: "Connecting…",
      connected: "Live",
      reconnecting: "Reconnecting…",
      offline: "You're offline. We'll reconnect when you're back.",
      closed: "Disconnected",
    },
    invite: {
      label: "Invite code",
      hint: "Share it with two or three others. It expires in two hours.",
      unknown: "Only the tab that started the table can show its code.",
      copy: "Copy code",
      copied: "Code copied.",
      copyFailed: "Couldn't copy. Select the code and copy it by hand.",
    },
    members: {
      title: "At the table ({count} of {max})",
      you: "you",
      host: "host",
      online: "here",
      away: "away",
      ready: "Ready",
      notReady: "Not ready",
    },
    actions: {
      ready: "I'm ready",
      notReady: "Not ready yet",
      start: "Start the case",
      leave: "Leave the table",
      leaveTitle: "Leave this table?",
      leaveBody: "You can rejoin with the code while the case hasn't started.",
      leaveConfirm: "Leave",
      stay: "Stay",
    },
    hints: {
      needPlayers: "Waiting for at least {min} players.",
      needReady: "Waiting for everyone to be ready.",
      waitingHost: "Waiting for {name} to start the case.",
      canStart: "Everyone's ready.",
    },
    chat: {
      title: "Table talk",
      empty: "No messages yet. Say hello.",
      label: "Message",
      placeholderHint: "Enter to send, Shift+Enter for a new line.",
      send: "Send",
      sending: "Sending…",
      counter: "{count} / {max}",
      tooLong: "Keep it under {max} characters.",
    },
    errors: {
      RATE_LIMITED: "Slow down a little; your message will go through in a moment.",
      ROOM_CLOSED: "This table has closed.",
      FRAME_TOO_LARGE: "That message is too long.",
      VALIDATION_ERROR: "That message couldn't be sent.",
      NOT_A_MEMBER: "You're no longer at this table.",
      ROOM_NOT_WAITING: "The case has already begun.",
      generic: "Something went wrong. Please try again.",
    },
    gone: "You're no longer at that table.",
  },
  game: {
    tabs: { label: "Case views", story: "Story", clues: "Your clues", board: "Board", chat: "Chat" },
    story: {
      chapter: "Chapter {index} of {total}",
      objective: "Objective:",
      skip: "Show all",
    },
    clues: {
      title: "Your clues",
      role: "You are {role}",
      roleFocus: "{focus}",
      empty: "No clues yet. New ones appear as the story moves.",
      private: "Private",
      shared: "Shared",
      share: "Pin to board",
      unlocked: "Clue unlocked: only you can see it until you pin it.",
    },
    board: {
      title: "Evidence board",
      empty: "Nothing pinned yet. Pin a clue to share it with the table.",
      public: "Found by everyone",
      sharedBy: "Pinned by {name}",
      pinned: "{name} pinned a clue to the board.",
    },
    decision: {
      continuePrompt: "Ready to move on?",
      continueLabel: "Continue",
      status: "{voted} of {seats} voted",
      deadline: "Deciding in {seconds}s unless everyone votes sooner.",
      votes: "{count} vote(s)",
      yourVote: "Your vote",
      vote: "Vote",
      change: "Change vote",
      resolved: "The table chose: {label}",
      tie: "It's a tie. Here's a nudge, then vote again.",
    },
    hints: {
      request: "Ask for a hint ({left} left)",
      none: "No hints left for this chapter",
      level: "Hint {level}",
    },
    ending: {
      success: "Case solved",
      partial: "Night survived",
      safe: "Safe retreat",
      abandoned: "Case closed",
      solution: "What really happened",
      next: "Your reflection and results arrive in the next build.",
    },
    reconnect: {
      title: "Reconnecting…",
      body: "Your place at the table is kept. Everything will catch up when you're back.",
    },
    errors: {
      STALE_STATE: "The table moved on; here's where things stand now.",
      ALREADY_SHARED: "That clue is already on the board.",
      NO_MORE_HINTS: "No hints left for this chapter.",
      GAME_OVER: "This case is closed.",
      RATE_LIMITED: "One moment; too many actions at once.",
    },
  },
});

export function tt(key, params) {
  const value = key.split(".").reduce((node, part) => (node == null ? node : node[part]), TEMP_STRINGS);
  if (typeof value !== "string") {
    console.warn(`Missing temp string: ${key}`);
    return key;
  }
  if (!params) return value;
  return value.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

export function applyTempStrings(root = document) {
  for (const el of root.querySelectorAll("[data-st]")) el.textContent = tt(el.dataset.st);
  for (const el of root.querySelectorAll("[data-st-label]")) el.setAttribute("aria-label", tt(el.dataset.stLabel));
}
