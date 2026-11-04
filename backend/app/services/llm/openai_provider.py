"""OpenAI provider using strict structured outputs (JSON schema derived from Pydantic models)."""

import logging

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.errors import ServiceNotConfigured
from app.services.llm.base import SYSTEM_GUARD, LLMError, LLMProvider, LLMUsage, T, wrap_untrusted

log = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    name = "openai"
    is_mock = False

    def __init__(self, client=None):
        s = get_settings()
        if client is None:
            if not s.openai_api_key:
                raise ServiceNotConfigured("OPENAI_API_KEY is not configured")
            from openai import OpenAI

            kwargs = {"api_key": s.openai_api_key, "timeout": 60.0, "max_retries": 2}
            if s.openai_base_url:
                kwargs["base_url"] = s.openai_base_url
            client = OpenAI(**kwargs)
        self.client = client

    def _model(self, tier: str) -> str:
        s = get_settings()
        return s.openai_model_advanced if tier == "advanced" else s.openai_model_default

    def complete(self, *, task: str, system: str, inputs: dict[str, str], schema: type[T], tier: str = "default"):
        model = self._model(tier)
        user_content = "\n\n".join(wrap_untrusted(label, text) for label, text in inputs.items())
        messages = [
            {"role": "system", "content": SYSTEM_GUARD + "\nTASK: " + system},
            {"role": "user", "content": user_content},
        ]
        chat = self.client.chat.completions
        parse = getattr(chat, "parse", None) or self.client.beta.chat.completions.parse
        try:
            completion = parse(model=model, messages=messages, response_format=schema, temperature=0.2)
        except Exception as exc:  # network, rate limit, API errors
            log.warning("OpenAI call failed for task=%s: %s", task, type(exc).__name__)
            raise LLMError(f"AI request failed ({type(exc).__name__})") from exc
        message = completion.choices[0].message
        if getattr(message, "refusal", None):
            raise LLMError("The AI declined to process this content")
        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise LLMError("The AI returned no structured output")
        try:
            result = schema.model_validate(parsed.model_dump() if hasattr(parsed, "model_dump") else parsed)
        except ValidationError as exc:
            raise LLMError("The AI returned output that failed validation") from exc
        usage = getattr(completion, "usage", None)
        return result, LLMUsage(
            provider=self.name,
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
