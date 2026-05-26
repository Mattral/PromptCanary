"""
tests/unit/test_litellm_provider.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests for promptcanary.providers.litellm.LiteLLMProvider.

Per ADR-008, no real network calls are made anywhere in the test suite.
These tests mock ``litellm.completion`` directly at the point of use,
exercising the full request-building and response-parsing logic in
LiteLLMProvider.complete() without depending on any provider's API.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from promptcanary.core.models import CanaryPrompt, ProviderConfig
from promptcanary.providers.base import ProviderError
from promptcanary.providers.litellm import LiteLLMProvider

# ─────────────────────────────────────────────────────────────────────────────
# Mock LiteLLM response objects
# ─────────────────────────────────────────────────────────────────────────────


class _MockMessage:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _MockChoice:
    def __init__(self, content: str | None, finish_reason: str = "stop") -> None:
        self.message = _MockMessage(content)
        self.finish_reason = finish_reason


class _MockUsage:
    def __init__(
        self,
        prompt_tokens: int = 10,
        completion_tokens: int = 20,
        total_tokens: int = 30,
    ) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class _MockLiteLLMResponse:
    """Mimics the shape of litellm.completion()'s return value."""

    def __init__(
        self,
        content: str | None = "Mock response content.",
        finish_reason: str = "stop",
        usage: _MockUsage | None = None,
        include_model_dump: bool = True,
    ) -> None:
        self.choices = [_MockChoice(content, finish_reason)]
        self.usage = usage
        self._include_model_dump = include_model_dump

    def model_dump(self) -> dict:
        if not self._include_model_dump:
            raise AttributeError("model_dump not available")
        return {"id": "mock-id", "object": "chat.completion"}


def _prompt(text: str = "What is the capital of France?", pid: str = "p1") -> CanaryPrompt:
    return CanaryPrompt(id=pid, text=text)


# ─────────────────────────────────────────────────────────────────────────────
# Construction
# ─────────────────────────────────────────────────────────────────────────────


class TestConstruction:
    def test_construct_from_model_string(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")
        assert provider.config.model_id == "openai/gpt-5.4"
        assert provider.config.temperature == 0.0
        assert provider.config.max_tokens == 1024
        assert provider.config.seed == 42

    def test_construct_with_custom_params(self) -> None:
        provider = LiteLLMProvider(
            "anthropic/claude-sonnet-4-6",
            temperature=0.7,
            max_tokens=2048,
            seed=None,
        )
        assert provider.config.temperature == 0.7
        assert provider.config.max_tokens == 2048
        assert provider.config.seed is None

    def test_construct_with_extra_params(self) -> None:
        provider = LiteLLMProvider(
            "openai/gpt-5.4",
            response_format={"type": "json_object"},
        )
        assert provider.config.extra_params == {"response_format": {"type": "json_object"}}

    def test_construct_from_provider_config(self) -> None:
        cfg = ProviderConfig(model_id="gemini/gemini-3.5-flash", temperature=0.2)
        provider = LiteLLMProvider(cfg)
        assert provider.config is cfg

    def test_from_config_classmethod(self) -> None:
        cfg = ProviderConfig(model_id="ollama/qwen3.6:27b")
        provider = LiteLLMProvider.from_config(cfg)
        assert provider.config.model_id == "ollama/qwen3.6:27b"

    def test_repr(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")
        assert "openai/gpt-5.4" in repr(provider)


# ─────────────────────────────────────────────────────────────────────────────
# complete() — happy path
# ─────────────────────────────────────────────────────────────────────────────


class TestCompleteHappyPath:
    def test_returns_llm_response_with_content(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")
        mock_response = _MockLiteLLMResponse(content="Paris is the capital of France.")

        with patch("litellm.completion", return_value=mock_response) as mock_complete:
            result = provider.complete(_prompt())

        assert result.content == "Paris is the capital of France."
        assert result.finish_reason == "stop"
        assert result.provider_model_id == "openai/gpt-5.4"
        assert result.prompt_id == "p1"
        mock_complete.assert_called_once()

    def test_includes_system_prompt_when_provided(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")
        mock_response = _MockLiteLLMResponse()

        with patch("litellm.completion", return_value=mock_response) as mock_complete:
            provider.complete(_prompt(), system_prompt="You are a geography expert.")

        call_kwargs = mock_complete.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "You are a geography expert."}
        assert messages[1] == {"role": "user", "content": "What is the capital of France?"}

    def test_omits_system_message_when_not_provided(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")
        mock_response = _MockLiteLLMResponse()

        with patch("litellm.completion", return_value=mock_response) as mock_complete:
            provider.complete(_prompt())

        messages = mock_complete.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_passes_model_temperature_max_tokens(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4", temperature=0.3, max_tokens=512)
        mock_response = _MockLiteLLMResponse()

        with patch("litellm.completion", return_value=mock_response) as mock_complete:
            provider.complete(_prompt())

        kwargs = mock_complete.call_args.kwargs
        assert kwargs["model"] == "openai/gpt-5.4"
        assert kwargs["temperature"] == 0.3
        assert kwargs["max_tokens"] == 512

    def test_passes_seed_when_set(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4", seed=123)
        mock_response = _MockLiteLLMResponse()

        with patch("litellm.completion", return_value=mock_response) as mock_complete:
            provider.complete(_prompt())

        assert mock_complete.call_args.kwargs["seed"] == 123

    def test_omits_seed_when_none(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4", seed=None)
        mock_response = _MockLiteLLMResponse()

        with patch("litellm.completion", return_value=mock_response) as mock_complete:
            provider.complete(_prompt())

        assert "seed" not in mock_complete.call_args.kwargs

    def test_extra_params_forwarded_to_completion_call(self) -> None:
        provider = LiteLLMProvider(
            "openai/gpt-5.4",
            response_format={"type": "json_object"},
        )
        mock_response = _MockLiteLLMResponse()

        with patch("litellm.completion", return_value=mock_response) as mock_complete:
            provider.complete(_prompt())

        assert mock_complete.call_args.kwargs["response_format"] == {"type": "json_object"}

    def test_extracts_token_usage(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")
        usage = _MockUsage(prompt_tokens=15, completion_tokens=25, total_tokens=40)
        mock_response = _MockLiteLLMResponse(usage=usage)

        with patch("litellm.completion", return_value=mock_response):
            result = provider.complete(_prompt())

        assert result.prompt_tokens == 15
        assert result.completion_tokens == 25
        assert result.total_tokens == 40

    def test_missing_usage_gives_none_token_counts(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")
        mock_response = _MockLiteLLMResponse(usage=None)

        with patch("litellm.completion", return_value=mock_response):
            result = provider.complete(_prompt())

        assert result.prompt_tokens is None
        assert result.completion_tokens is None
        assert result.total_tokens is None

    def test_raw_response_captured_via_model_dump(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")
        mock_response = _MockLiteLLMResponse(include_model_dump=True)

        with patch("litellm.completion", return_value=mock_response):
            result = provider.complete(_prompt())

        assert result.raw_response == {"id": "mock-id", "object": "chat.completion"}

    def test_raw_response_empty_dict_when_no_model_dump(self) -> None:
        """Response objects without model_dump() (e.g. plain dicts) degrade gracefully."""
        provider = LiteLLMProvider("openai/gpt-5.4")

        class _PlainResponse:
            def __init__(self) -> None:
                self.choices = [_MockChoice("content")]
                self.usage = None

        with patch("litellm.completion", return_value=_PlainResponse()):
            result = provider.complete(_prompt())

        assert result.raw_response == {}

    def test_none_content_becomes_empty_string(self) -> None:
        """Some providers return None content on certain finish_reasons (e.g. tool_calls)."""
        provider = LiteLLMProvider("openai/gpt-5.4")
        mock_response = _MockLiteLLMResponse(content=None, finish_reason="tool_calls")

        with patch("litellm.completion", return_value=mock_response):
            result = provider.complete(_prompt())

        assert result.content == ""
        assert result.finish_reason == "tool_calls"


# ─────────────────────────────────────────────────────────────────────────────
# complete() — error handling
# ─────────────────────────────────────────────────────────────────────────────


class TestCompleteErrorHandling:
    def test_import_error_raises_provider_error(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")

        with patch.dict("sys.modules", {"litellm": None}):
            with pytest.raises(ProviderError, match="LiteLLM is not installed"):
                provider.complete(_prompt())

    def test_api_failure_raises_provider_error(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")

        with patch("litellm.completion", side_effect=RuntimeError("connection refused")):
            with pytest.raises(ProviderError, match="Provider call failed"):
                provider.complete(_prompt())

    def test_api_failure_preserves_model_id(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")

        with patch("litellm.completion", side_effect=RuntimeError("boom")):
            with pytest.raises(ProviderError) as exc_info:
                provider.complete(_prompt())

        assert exc_info.value.model_id == "openai/gpt-5.4"

    def test_api_failure_captures_status_code_when_present(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")

        class _HttpError(Exception):
            status_code = 429

        with patch("litellm.completion", side_effect=_HttpError("rate limited")):
            with pytest.raises(ProviderError) as exc_info:
                provider.complete(_prompt())

        assert exc_info.value.status_code == 429

    def test_api_failure_preserves_raw_error(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")
        original = RuntimeError("original failure")

        with patch("litellm.completion", side_effect=original):
            with pytest.raises(ProviderError) as exc_info:
                provider.complete(_prompt())

        assert exc_info.value.raw_error is original

    def test_malformed_response_missing_choices_raises_provider_error(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")

        class _EmptyChoicesResponse:
            def __init__(self) -> None:
                self.choices: list = []

        with patch("litellm.completion", return_value=_EmptyChoicesResponse()):
            with pytest.raises(ProviderError, match="Unexpected response structure"):
                provider.complete(_prompt())

    def test_malformed_response_missing_message_attribute(self) -> None:
        provider = LiteLLMProvider("openai/gpt-5.4")

        class _BadChoice:
            pass  # no .message attribute

        class _BadResponse:
            def __init__(self) -> None:
                self.choices = [_BadChoice()]

        with patch("litellm.completion", return_value=_BadResponse()):
            with pytest.raises(ProviderError, match="Unexpected response structure"):
                provider.complete(_prompt())


# ─────────────────────────────────────────────────────────────────────────────
# ProviderError — str() formatting
# ─────────────────────────────────────────────────────────────────────────────


class TestProviderErrorFormatting:
    def test_str_includes_message_only(self) -> None:
        err = ProviderError("Something went wrong")
        assert str(err) == "Something went wrong"

    def test_str_includes_model_id(self) -> None:
        err = ProviderError("Failed", model_id="openai/gpt-5.4")
        assert "openai/gpt-5.4" in str(err)

    def test_str_includes_status_code(self) -> None:
        err = ProviderError("Failed", status_code=500)
        assert "status=500" in str(err)

    def test_str_includes_all_fields(self) -> None:
        err = ProviderError("Failed", model_id="openai/gpt-5.4", status_code=429)
        s = str(err)
        assert "Failed" in s
        assert "openai/gpt-5.4" in s
        assert "429" in s
