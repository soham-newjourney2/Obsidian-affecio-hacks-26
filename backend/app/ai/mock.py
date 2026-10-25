"""Deterministic offline provider (AI_PROVIDER=mock): returns the authored text unchanged."""

import json

from backend.app.ai.base import ProviderResult


class MockProvider:
    name = "mock"
    model = "mock"

    async def complete(self, system: str, user: str, max_tokens: int) -> ProviderResult:
        inputs = json.loads(user.split("\n", 1)[1].rsplit("\n", 1)[0])
        if "choices" in inputs:  # theory mapping: the mock never guesses
            return ProviderResult(data={"choice_id": None, "confidence": 0.0}, model=self.model)
        return ProviderResult(data={"text": inputs["base"]}, model=self.model)

    async def aclose(self) -> None:
        return None
