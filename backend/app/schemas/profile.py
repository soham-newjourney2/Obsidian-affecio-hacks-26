import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.content import profile_options as opts

InteractionStyle = Literal["thoughtful", "playful", "analytical"]
Visibility = Literal["private", "match_only"]

# Raw lists are capped (Field max_length) before validation so oversized payloads fail fast.
RawList = list[str]


def _check_list(field: str, values: list[str]) -> list[str]:
    allowed = opts.ids(field)
    unique = list(dict.fromkeys(values))  # de-duplicate, keep order
    unknown = [v for v in unique if v not in allowed]
    if unknown:
        raise ValueError(f"unknown {field}: {', '.join(unknown[:3])}")
    low, high = opts.LIMITS[field]
    if not low <= len(unique) <= high:
        raise ValueError(f"choose {low}–{high} {field}")
    return unique


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interests: RawList = Field(max_length=32)
    genres: RawList = Field(default_factory=list, max_length=32)
    activities: RawList = Field(default_factory=list, max_length=32)
    interaction_style: InteractionStyle
    preferred_roles: RawList = Field(default_factory=list, max_length=32)
    availability: RawList = Field(max_length=32)
    visibility: Visibility = "private"
    shareable_summary: str = Field(default="", max_length=opts.SUMMARY_MAX + 40)

    @field_validator("interests", "genres", "activities", "preferred_roles", "availability")
    @classmethod
    def _lists(cls, v: list[str], info) -> list[str]:
        return _check_list(info.field_name, v)

    @field_validator("shareable_summary")
    @classmethod
    def _summary(cls, v: str) -> str:
        v = " ".join(v.split())
        if any(unicodedata.category(ch).startswith("C") for ch in v):
            raise ValueError("summary contains control characters")
        if len(v) > opts.SUMMARY_MAX:
            raise ValueError(f"summary must be at most {opts.SUMMARY_MAX} characters")
        return v


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    interests: list[str]
    genres: list[str]
    activities: list[str]
    interaction_style: InteractionStyle
    preferred_roles: list[str]
    availability: list[str]
    visibility: Visibility
    shareable_summary: str
    updated_at: datetime


class OptionOut(BaseModel):
    id: str
    label: str


class ProfileOptionsOut(BaseModel):
    interests: list[OptionOut]
    genres: list[OptionOut]
    activities: list[OptionOut]
    interaction_styles: list[OptionOut]
    roles: list[OptionOut]
    availability: list[OptionOut]
    visibility: list[OptionOut]
    limits: dict[str, tuple[int, int]]
    summary_max: int


def profile_options() -> ProfileOptionsOut:
    def as_out(options: tuple[opts.Option, ...]) -> list[OptionOut]:
        return [OptionOut(id=i, label=label) for i, label in options]

    return ProfileOptionsOut(
        interests=as_out(opts.INTERESTS),
        genres=as_out(opts.GENRES),
        activities=as_out(opts.ACTIVITIES),
        interaction_styles=as_out(opts.INTERACTION_STYLES),
        roles=as_out(opts.ROLES),
        availability=as_out(opts.AVAILABILITY),
        visibility=as_out(opts.VISIBILITY),
        limits=dict(opts.LIMITS),
        summary_max=opts.SUMMARY_MAX,
    )
