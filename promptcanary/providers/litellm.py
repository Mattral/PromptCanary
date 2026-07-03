"""
promptcanary.providers.litellm
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

LiteLLM-backed provider — the recommended and default provider for PromptCanary.

LiteLLM gives us a unified interface to 100+ LLM providers:
  - OpenAI: "openai/gpt-4o", "openai/gpt-4o-mini"
  - Anthropic: "anthropic/claude-3-5-sonnet-20241022"
  - Google: "gemini/gemini-1.5-pro"
  - Local (Ollama): "ollama/llama3"
  - Local (vLLM): "hosted_vllm/meta-llama/Llama-3-8b-Instruct"
  - Grok: "xai/grok-beta"
  - ... and many more

Usage::

    from promptcanary import LiteLLMProvider

    provider = LiteLLMProvider("openai/gpt-4o")
    # or with full config:
    from promptcanary.core.models import ProviderConfig
    cfg = ProviderConfig(model_id="anthropic/claude-3-5-sonnet-20241022", temperature=0.0)
    provider = LiteLLMProvider.from_config(cfg)
"""

from __future__ import annotations

from promptcanary.core.models import CanaryPrompt, LLMResponse, ProviderConfig
from promptcanary.providers.base import BaseLLMProvider, ProviderError


class LiteLLMProvider(BaseLLMProvider):
    """LLM provider backed by the LiteLLM library.

    This is the recommended provider for PromptCanary. It supports all major
    cloud providers and local models via a single unified interface.

    Args:
        model_id_or_config: Either a LiteLLM model string (e.g. ``"openai/gpt-4o"``)
                            or a :class:`ProviderConfig`.
        temperature:        Sampling temperature (default: 0.0 for reproducibility).
        max_tokens:         Max tokens in the response (default: 1024).
        seed:               Determinism seed (default: 42).
        **extra_params:     Additional kwargs forwarded to ``litellm.completion()``.

    Examples::

        # Quickstart
        provider = LiteLLMProvider("openai/gpt-4o-mini")

        # Anthropic
        provider = LiteLLMProvider("anthropic/claude-3-5-sonnet-20241022")

        # Local Ollama
        provider = LiteLLMProvider("ollama/llama3", temperature=0.0)

        # Full config
        provider = LiteLLMProvider(
            "openai/gpt-4o",
            temperature=0.0,
            max_tokens=2048,
            extra_params={"response_format": {"type": "json_object"}},
        )
    """

    def __init__(
        self,
        model_id_or_config: str | ProviderConfig,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        seed: int | None = 42,
        **extra_params: object,
    ) -> None:
        if isinstance(model_id_or_config, ProviderConfig):
            config = model_id_or_config
        else:
            config = ProviderConfig(
                model_id=model_id_or_config,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
                extra_params=dict(extra_params),
            )
        super().__init__(config)

    @classmethod
    def from_config(cls, config: ProviderConfig) -> LiteLLMProvider:
        """Create a provider directly from a :class:`ProviderConfig`."""
        return cls(config)

    def complete(
        self,
        prompt: CanaryPrompt,
        *,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Call the LLM via LiteLLM and return a structured :class:`LLMResponse`.

        Args:
            prompt:        The :class:`CanaryPrompt` to send.
            system_prompt: Optional system instruction.

        Returns:
            A :class:`LLMResponse` with content, token counts, and metadata.

        Raises:
            ProviderError: On API errors, auth failures, or network issues.
        """
        try:
            import litellm
        except ImportError as e:
            raise ProviderError(
                "LiteLLM is not installed. Run: pip install litellm",
                model_id=self.config.model_id,
                raw_error=e,
            ) from e

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt.text})

        # Build kwargs from config
        kwargs: dict[str, object] = {
            "model": self.config.model_id,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            **self.config.extra_params,
        }

        # Seed is provider-dependent; pass it if set
        if self.config.seed is not None:
            kwargs["seed"] = self.config.seed

        try:
            response = litellm.completion(**kwargs)
        except Exception as exc:
            # Normalise all litellm/provider errors into ProviderError
            status = getattr(exc, "status_code", None)
            raise ProviderError(
                f"Provider call failed: {exc}",
                model_id=self.config.model_id,
                status_code=status,
                raw_error=exc,
            ) from exc

        # Extract content safely
        try:
            content = response.choices[0].message.content or ""
            finish_reason = response.choices[0].finish_reason
        except (AttributeError, IndexError) as exc:
            raise ProviderError(
                f"Unexpected response structure from {self.config.model_id}: {exc}",
                model_id=self.config.model_id,
                raw_error=exc,
            ) from exc

        # Token usage (optional fields)
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)

        return LLMResponse(
            prompt_id=prompt.id,
            provider_model_id=self.config.model_id,
            content=content,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            raw_response=response.model_dump() if hasattr(response, "model_dump") else {},
        )
