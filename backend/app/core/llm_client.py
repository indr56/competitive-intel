from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Provider-agnostic LLM interface."""

    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
        """Send a chat completion request and return the assistant message text."""
        ...

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Send a chat request expecting JSON back. Parses and returns dict."""
        raw = self.chat(system_prompt, user_prompt, json_mode=True)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("LLM returned non-JSON response: %s", raw[:500])
            return {"error": "invalid_json", "raw": raw}


class OpenAIClient(BaseLLMClient):
    def __init__(self) -> None:
        from openai import OpenAI

        settings = get_settings()
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.LLM_MODEL

    def chat(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


class AnthropicClient(BaseLLMClient):
    def __init__(self) -> None:
        from anthropic import Anthropic

        settings = get_settings()
        self._client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = settings.LLM_MODEL or "claude-sonnet-4-20250514"

    def chat(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
        prompt = user_prompt
        if json_mode:
            prompt += "\n\nRespond ONLY with valid JSON. No markdown, no extra text."
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


_client_instance: BaseLLMClient | None = None


def get_llm_client() -> BaseLLMClient:
    """Factory: returns singleton LLM client based on LLM_PROVIDER env var."""
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    settings = get_settings()
    provider = settings.LLM_PROVIDER.lower()

    if provider == "openai":
        _client_instance = OpenAIClient()
    elif provider == "anthropic":
        _client_instance = AnthropicClient()
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}. Use 'openai' or 'anthropic'.")

    logger.info("Initialized LLM client: %s (model=%s)", provider, settings.LLM_MODEL)
    return _client_instance
