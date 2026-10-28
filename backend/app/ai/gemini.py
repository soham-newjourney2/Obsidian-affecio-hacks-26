"""Gemini provider over raw httpx: models.generateContent with a JSON response schema.

Checked against ai.google.dev (2026-10): POST /v1beta/models/{model}:generateContent,
`systemInstruction`, `generationConfig.responseMimeType` + `responseSchema`, `maxOutputTokens`;
text in `candidates[0].content.parts[0].text`, usage in `usageMetadata`. The key goes in the
`x-goog-api-key` header, never the URL. Failover only: its free tier may use inputs for
training, and it gets the same minimal inputs as every provider.
"""

import json

import httpx

from backend.app.ai.base import ProviderError, ProviderResult

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
TEXT_SCHEMA = {"type": "OBJECT", "properties": {"text": {"type": "STRING"}}, "required": ["text"]}


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._timeout = timeout_s
        self._client = httpx.AsyncClient(
            transport=transport,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        )

    async def complete(self, system: str, user: str, max_tokens: int) -> ProviderResult:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": TEXT_SCHEMA,
                "maxOutputTokens": max_tokens,
                "temperature": 0.7,
            },
        }
        url = f"{GEMINI_BASE}/{self.model}:generateContent"
        try:
            res = await self._client.post(url, json=body, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("error", type(exc).__name__) from exc
        if res.status_code == 429:
            raise ProviderError("error", "rate limited (429)")
        if res.status_code >= 400:
            raise ProviderError("error", f"HTTP {res.status_code}")
        try:
            payload = res.json()
            candidate = payload["candidates"][0]
            if candidate.get("finishReason", "STOP") != "STOP":  # safety block, truncation...
                raise ProviderError("invalid", f"finish {candidate.get('finishReason')}")
            data = json.loads(candidate["content"]["parts"][0]["text"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("invalid", "unparseable response") from exc
        usage = payload.get("usageMetadata") or {}
        return ProviderResult(
            data=data,
            model=payload.get("modelVersion", self.model),
            tokens_in=usage.get("promptTokenCount"),
            tokens_out=usage.get("candidatesTokenCount"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
