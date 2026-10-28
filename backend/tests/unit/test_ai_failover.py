"""Gemini provider, Groq -> Gemini -> fallback, and the circuit breaker."""

import json

import httpx
import pytest

from backend.app.ai.chain import AIChain, CircuitBreaker, build_user_message
from backend.app.ai.factory import build_chain
from backend.app.ai.gemini import GEMINI_BASE, GeminiProvider
from backend.app.ai.groq import GroqProvider
from backend.app.core.config import Settings
from backend.tests.unit.test_ai import BASE, FAKE_KEY, INPUTS, Recorder, groq_reply, logs

FAKE_GOOGLE_KEY = "test-google-key-not-real"


def gemini_reply(content: object, finish: str = "STOP", status: int = 200) -> httpx.Response:
    text = content if isinstance(content, str) else json.dumps(content)
    body = {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
        "usageMetadata": {"promptTokenCount": 90, "candidatesTokenCount": 30},
        "modelVersion": "gemini-3.5-flash-lite",
    }
    return httpx.Response(status, json=body)


def down(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, json={"error": "down"})


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_chain(maker, groq_handler, gemini_handler, clock=None):
    groq = Recorder(groq_handler)
    gemini = Recorder(gemini_handler)
    providers = [
        GroqProvider(FAKE_KEY, "openai/gpt-oss-120b", 8, httpx.MockTransport(groq)),
        GeminiProvider(FAKE_GOOGLE_KEY, "gemini-3.5-flash-lite", 8, httpx.MockTransport(gemini)),
    ]
    breaker = CircuitBreaker(clock=clock) if clock else None
    chain = AIChain(
        providers,
        maker,
        max_output_tokens=400,
        max_calls_per_session=1000,
        timeout_s=8,
        breaker=breaker,
    )
    return chain, groq, gemini


async def narrate(chain: AIChain):
    return await chain.run(purpose="narrate", inputs=INPUTS, fallback=BASE)


# --- the Gemini provider ---------------------------------------------------------------------


async def test_gemini_request_matches_the_documented_api(maker) -> None:
    rec = Recorder(lambda r: gemini_reply({"text": "Rain needles the glass."}))
    provider = GeminiProvider(FAKE_GOOGLE_KEY, "gemini-3.5-flash-lite", 8, httpx.MockTransport(rec))
    result = await provider.complete("Reply in JSON.", build_user_message(INPUTS), 400)
    assert result.data == {"text": "Rain needles the glass."}
    assert (result.tokens_in, result.tokens_out) == (90, 30)
    req = rec.requests[0]
    assert str(req.url) == f"{GEMINI_BASE}/gemini-3.5-flash-lite:generateContent"
    assert req.headers["x-goog-api-key"] == FAKE_GOOGLE_KEY
    assert FAKE_GOOGLE_KEY not in str(req.url)  # keys never in URLs
    body = json.loads(req.content)
    assert body["systemInstruction"] == {"parts": [{"text": "Reply in JSON."}]}
    assert body["contents"][0]["role"] == "user"
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseSchema"]["required"] == ["text"]
    assert config["maxOutputTokens"] == 400
    await provider.aclose()


@pytest.mark.parametrize(
    ("reply", "status"),
    [
        (lambda r: gemini_reply({"text": "x"}, finish="SAFETY"), "invalid"),
        (lambda r: gemini_reply({"text": "x"}, finish="MAX_TOKENS"), "invalid"),
        (lambda r: gemini_reply("not json"), "invalid"),
        (
            lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
            "invalid",
        ),
        (lambda r: httpx.Response(429, json={"error": "quota"}), "error"),
        (lambda r: httpx.Response(404, json={"error": "no such model"}), "error"),
    ],
    ids=["safety", "truncated", "malformed", "no-candidates", "429", "404"],
)
async def test_gemini_failures_fall_back(maker, db_path, reply, status) -> None:
    rec = Recorder(reply)
    provider = GeminiProvider(FAKE_GOOGLE_KEY, "m", 8, httpx.MockTransport(rec))
    chain = AIChain([provider], maker, max_output_tokens=400, max_calls_per_session=30, timeout_s=8)
    assert (await narrate(chain)).provider == "fallback"
    assert [row[:2] for row in logs(db_path)] == [("gemini", status), ("fallback", "fallback")]
    await chain.aclose()


# --- failover ---------------------------------------------------------------------------------


async def test_groq_down_gemini_answers(maker, db_path) -> None:
    chain, groq, gemini = make_chain(maker, down, lambda r: gemini_reply({"text": "From Gemini."}))
    result = await narrate(chain)
    assert (result.text, result.provider) == ("From Gemini.", "gemini")
    assert [row[:2] for row in logs(db_path)] == [("groq", "error"), ("gemini", "success")]
    await chain.aclose()


async def test_groq_answers_gemini_untouched(maker, db_path) -> None:
    chain, groq, gemini = make_chain(
        maker, lambda r: groq_reply({"text": "From Groq."}), lambda r: gemini_reply({"text": "x"})
    )
    assert (await narrate(chain)).provider == "groq"
    assert gemini.requests == []  # failover only: Gemini sees nothing while Groq is healthy
    await chain.aclose()


async def test_both_down_authored_text(maker, db_path) -> None:
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    chain, _, _ = make_chain(maker, down, slow)
    result = await narrate(chain)
    assert (result.text, result.provider) == (BASE, "fallback")
    assert [row[:2] for row in logs(db_path)] == [
        ("groq", "error"),
        ("gemini", "timeout"),
        ("fallback", "fallback"),
    ]
    await chain.aclose()


async def test_invalid_groq_output_also_fails_over(maker, db_path) -> None:
    chain, _, _ = make_chain(
        maker,
        lambda r: groq_reply({"text": "x", "extra": 1}),
        lambda r: gemini_reply({"text": "ok"}),
    )
    assert (await narrate(chain)).provider == "gemini"
    assert [row[:2] for row in logs(db_path)] == [("groq", "invalid"), ("gemini", "success")]
    await chain.aclose()


# --- circuit breaker --------------------------------------------------------------------------


async def test_breaker_opens_after_three_failures_and_recovers(maker, db_path) -> None:
    clock = Clock()
    groq_ok = {"value": False}

    def groq(request):
        return groq_reply({"text": "Groq is back."}) if groq_ok["value"] else down(request)

    chain, groq_calls, _ = make_chain(maker, groq, lambda r: gemini_reply({"text": "G"}), clock)
    for _ in range(3):
        assert (await narrate(chain)).provider == "gemini"
    assert len(groq_calls.requests) == 3 and chain.breaker.is_open("groq")

    assert (await narrate(chain)).provider == "gemini"
    assert len(groq_calls.requests) == 3  # skipped while open: no call at all

    clock.now += 59
    await narrate(chain)
    assert len(groq_calls.requests) == 3  # still cooling down

    clock.now += 1  # 60 s: one trial call
    groq_ok["value"] = True
    assert (await narrate(chain)).provider == "groq"
    assert not chain.breaker.is_open("groq")
    providers = [row[0] for row in logs(db_path)]
    assert providers.count("groq") == 4  # recorded each time it was really called
    await chain.aclose()


async def test_failed_trial_reopens_the_breaker(maker) -> None:
    clock = Clock()
    chain, groq_calls, _ = make_chain(maker, down, lambda r: gemini_reply({"text": "G"}), clock)
    for _ in range(3):
        await narrate(chain)
    clock.now += 60
    await narrate(chain)  # the trial fails...
    assert len(groq_calls.requests) == 4 and chain.breaker.is_open("groq")
    await narrate(chain)  # ...so Groq is skipped again straight away
    assert len(groq_calls.requests) == 4
    await chain.aclose()


def test_breaker_counts_consecutive_failures_only() -> None:
    clock = Clock()
    breaker = CircuitBreaker(clock=clock)
    for ok in (False, False, True, False, False):
        breaker.record("groq", ok)
    assert not breaker.is_open("groq")  # the success in the middle reset the count
    breaker.record("groq", False)
    assert breaker.is_open("groq")
    assert breaker.allow("gemini")  # per provider


# --- configuration ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (
            {"groq_api_key": "g", "groq_model": "m", "gemini_api_key": "k", "gemini_model": "m"},
            ["groq", "gemini"],
        ),
        ({"gemini_api_key": "k", "gemini_model": "m"}, ["gemini"]),
        ({"groq_api_key": "g", "groq_model": ""}, []),  # a key without a model is not configured
        ({}, []),
    ],
    ids=["both", "gemini-only", "no-model", "none"],
)
async def test_factory_orders_providers(maker, settings: Settings, env, expected) -> None:
    configured = Settings(  # validated, so keys become SecretStr like in production
        _env_file=None,
        secret_key=settings.secret_key.get_secret_value(),
        ai_provider="chain",
        **env,
    )
    chain = build_chain(configured, maker)
    assert [p.name for p in chain.providers] == expected
    await chain.aclose()


async def test_factory_mock_mode(maker, settings: Settings) -> None:
    chain = build_chain(settings, maker)
    assert [p.name for p in chain.providers] == ["mock"]
