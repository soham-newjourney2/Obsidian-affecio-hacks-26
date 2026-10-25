"""Names for AI companions (demo mode). Always shown with an "AI companion" label."""

COMPANION_NAMES = ("Wren", "Moss", "Ember")


def companion_name(key: str | None) -> str:
    """companion_key "companion-2" -> "Moss"."""
    try:
        index = int((key or "").rsplit("-", 1)[1]) - 1
    except (IndexError, ValueError):
        index = 0
    return COMPANION_NAMES[index % len(COMPANION_NAMES)]
