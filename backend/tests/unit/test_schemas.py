import pytest
from pydantic import ValidationError

from backend.app.schemas.auth import RegisterIn, normalize_email

BASE = {
    "email": "a@example.com",
    "password": "x" * 10,
    "display_name": "Ada",
    "age_confirmed": True,
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ada@Example.COM", "ada@example.com"),
        ("  ada@example.com\t", "ada@example.com"),
        ("ADA.LOVELACE+echo@EXAMPLE.org", "ada.lovelace+echo@example.org"),
    ],
)
def test_normalize_email(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", ["", "ada", "ada@", "@example.com", "a b@example.com"])
def test_normalize_email_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_email(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  Ada   Lovelace ", "Ada Lovelace"), ("Zoë", "Zoë"), ("o'neil-2_x.y", "o'neil-2_x.y")],
)
def test_display_name_normalized(raw: str, expected: str) -> None:
    assert RegisterIn(**{**BASE, "display_name": raw}).display_name == expected


@pytest.mark.parametrize("raw", ["A", "A" * 25, "  ", "-ada", "ada<b>", "ada\u0000"])
def test_display_name_rejected(raw: str) -> None:
    with pytest.raises(ValidationError):
        RegisterIn(**{**BASE, "display_name": raw})


def test_age_must_be_confirmed() -> None:
    with pytest.raises(ValidationError):
        RegisterIn(**{**BASE, "age_confirmed": False})
