from app.core.config import get_settings
from app.services.llm.base import LLMError, LLMProvider, LLMUsage

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        s = get_settings()
        if s.ai_provider == "openai":
            from app.services.llm.openai_provider import OpenAIProvider

            _provider = OpenAIProvider()
        else:
            from app.services.llm.mock_provider import MockProvider

            _provider = MockProvider()
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """Override the provider (tests)."""
    global _provider
    _provider = provider


__all__ = ["LLMError", "LLMProvider", "LLMUsage", "get_provider", "set_provider"]
