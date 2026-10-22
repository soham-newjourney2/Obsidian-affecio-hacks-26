"""Curated profile options (students and newcomers). The server is the single source of truth:
the onboarding UI renders these, and profile validation accepts nothing else."""

from typing import Final

Option = tuple[str, str]

INTERESTS: Final[tuple[Option, ...]] = (
    ("books", "Books"),
    ("film", "Film"),
    ("music", "Music"),
    ("gaming", "Video games"),
    ("board_games", "Board games"),
    ("puzzles", "Puzzles & riddles"),
    ("history", "History"),
    ("science", "Science"),
    ("technology", "Technology"),
    ("art_design", "Art & design"),
    ("photography", "Photography"),
    ("writing", "Writing"),
    ("theatre", "Theatre"),
    ("comics_anime", "Comics & anime"),
    ("cooking", "Cooking"),
    ("coffee_tea", "Coffee & tea"),
    ("fitness", "Fitness"),
    ("outdoors", "Outdoors"),
    ("travel", "Travel"),
    ("languages", "Languages"),
    ("volunteering", "Volunteering"),
    ("startups", "Startups"),
    ("philosophy", "Philosophy"),
    ("podcasts", "Podcasts"),
)

GENRES: Final[tuple[Option, ...]] = (
    ("mystery", "Mystery"),
    ("gothic", "Gothic"),
    ("adventure", "Adventure"),
    ("science_fiction", "Science fiction"),
    ("fantasy", "Fantasy"),
    ("ghost_story", "Ghost stories"),
)

ACTIVITIES: Final[tuple[Option, ...]] = (
    ("coffee", "Grab a coffee"),
    ("study_session", "Study together"),
    ("walk", "Go for a walk"),
    ("board_game_night", "Board game night"),
    ("museum", "Museums & galleries"),
    ("live_music", "Live music"),
    ("sport", "Play a sport"),
    ("cook_together", "Cook together"),
    ("campus_event", "Campus events"),
    ("online_game", "Play online"),
)

INTERACTION_STYLES: Final[tuple[Option, ...]] = (
    ("thoughtful", "Thoughtful — I listen first, then speak"),
    ("playful", "Playful — I keep things light and lively"),
    ("analytical", "Analytical — I like to work through the logic"),
)

ROLES: Final[tuple[Option, ...]] = (
    ("investigator", "Investigator — physical evidence"),
    ("archivist", "Archivist — letters and records"),
    ("listener", "Listener — testimony and sounds"),
    ("strategist", "Strategist — timelines and floor plans"),
)

AVAILABILITY: Final[tuple[Option, ...]] = (
    ("weekday_mornings", "Weekday mornings"),
    ("weekday_afternoons", "Weekday afternoons"),
    ("weekday_evenings", "Weekday evenings"),
    ("weekend_mornings", "Weekend mornings"),
    ("weekend_afternoons", "Weekend afternoons"),
    ("weekend_evenings", "Weekend evenings"),
)

VISIBILITY: Final[tuple[Option, ...]] = (
    ("private", "Private — only you see your profile"),
    ("match_only", "Match only — shared interests may explain a match to your group"),
)

# (min, max) selections per list field.
LIMITS: Final[dict[str, tuple[int, int]]] = {
    "interests": (3, 8),
    "genres": (0, 6),
    "activities": (0, 6),
    "preferred_roles": (0, 2),
    "availability": (1, 6),
}

OPTIONS: Final[dict[str, tuple[Option, ...]]] = {
    "interests": INTERESTS,
    "genres": GENRES,
    "activities": ACTIVITIES,
    "interaction_style": INTERACTION_STYLES,
    "preferred_roles": ROLES,
    "availability": AVAILABILITY,
    "visibility": VISIBILITY,
}

SUMMARY_MAX = 160


def ids(field: str) -> frozenset[str]:
    return frozenset(option_id for option_id, _ in OPTIONS[field])
