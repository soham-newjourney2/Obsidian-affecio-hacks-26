"""Builds the AI chain from settings: mock for tests/offline, otherwise the real providers."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.ai.chain import AIChain
from backend.app.ai.groq import GroqProvider
from backend.app.ai.mock import MockProvider
from backend.app.core.config import Settings

log = logging.getLogger("echo.ai")


def build_chain(settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]) -> AIChain:
    providers = []
    if settings.ai_provider == "mock":
        providers.append(MockProvider())
    else:
        key = settings.groq_api_key.get_secret_value() if settings.groq_api_key else ""
        if key and settings.groq_model:
            providers.append(GroqProvider(key, settings.groq_model, settings.ai_timeout_s))
        else:
            log.warning("AI_PROVIDER=chain but Groq is not configured: authored text only")
    return AIChain(
        providers,
        sessionmaker,
        max_output_tokens=settings.ai_max_output_tokens,
        max_calls_per_session=settings.ai_max_calls_per_session,
        timeout_s=settings.ai_timeout_s,
    )
