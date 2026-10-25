"""Groq provider over raw httpx (OpenAI-compatible chat completions, JSON object mode).

Endpoint and parameters checked against console.groq.com/docs (2026-10): POST
/openai/v1/chat/completions, `Authorization: Bearer`, `response_format: {"type": "json_object"}`
(the prompt must ask for JSON), `max_completion_tokens`, usage in `usage.prompt_tokens` /
`usage.completion_tokens`. The model name comes from GROQ_MODEL (we use the production
`openai/gpt-oss-120b`; Llama models were not available to our key).
"""

import json

import httpx

from backend.app.ai.base import ProviderError, ProviderResult

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    name = "groq"

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
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    async def complete(self, system: str, user: str, max_tokens: int) -> ProviderResult:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": max_tokens,
            "temperature": 0.7,
        }
        if self.model.startswith("openai/gpt-oss"):
            # Reasoning models think before answering; keep that short so the reply fits the budget.
            body["reasoning_effort"] = "low"
        try:
            res = await self._client.post(GROQ_URL, json=body, timeout=self._timeout)
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
            content = payload["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("invalid", "unparseable response") from exc
        usage = payload.get("usage") or {}
        return ProviderResult(
            data=data,
            model=payload.get("model", self.model),
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
