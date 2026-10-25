"""Provider contract for the AI chain. Providers return parsed JSON; the chain validates it."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_VERSION = "v1"


@dataclass(frozen=True)
class ProviderResult:
    data: Any  # parsed JSON from the model (validated by the chain, never trusted)
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


class ProviderError(Exception):
    """kind: "timeout" | "error" (HTTP/network/429) | "invalid" (unparseable output)."""

    def __init__(self, kind: str, detail: str = "") -> None:
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


class Provider(Protocol):
    name: str

    async def complete(self, system: str, user: str, max_tokens: int) -> ProviderResult: ...

    async def aclose(self) -> None: ...


def load_prompt(purpose: str) -> tuple[str, str]:
    """Returns (system prompt text, prompt_version label such as "narrate.v1")."""
    path = PROMPTS_DIR / f"{purpose}.{PROMPT_VERSION}.txt"
    return path.read_text(encoding="utf-8").strip(), f"{purpose}.{PROMPT_VERSION}"
