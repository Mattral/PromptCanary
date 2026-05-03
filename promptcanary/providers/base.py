"""
promptcanary.providers.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Abstract base class for all LLM providers.

Implementing a new provider requires only two things:
  1. Inherit from BaseLLMProvider.
  2. Implement the `complete()` method.

Everything else — config validation, response wrapping — is handled here
or by the caller.
"""

from __future__ import annotations

import abc

from promptcanary.core.models import CanaryPrompt, LLMResponse, ProviderConfig


class BaseLLMProvider(abc.ABC):
    """Abstract base class for LLM provider adapters.

    Subclasses must implement :meth:`complete`.

    Args:
        config: A :class:`ProviderConfig` describing the model and parameters.
    """

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    @property
    def config(self) -> ProviderConfig:
        return self._config

    @abc.abstractmethod
    def complete(
        self,
        prompt: CanaryPrompt,
        *,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Send a prompt to the provider and return a structured response.

        Args:
            prompt:        The :class:`CanaryPrompt` to send.
            system_prompt: Optional system-level instruction override.

        Returns:
            A :class:`LLMResponse` with content and metadata.

        Raises:
            ProviderError: On any API or network error.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.config.model_id!r})"


class ProviderError(Exception):
    """Raised when an LLM provider call fails.

    Attributes:
        model_id:   The model that was being called.
        status_code: HTTP status code if applicable.
        raw_error:  The original exception.
    """

    def __init__(
        self,
        message: str,
        *,
        model_id: str = "",
        status_code: int | None = None,
        raw_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.model_id = model_id
        self.status_code = status_code
        self.raw_error = raw_error

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.model_id:
            parts.append(f"model={self.model_id!r}")
        if self.status_code:
            parts.append(f"status={self.status_code}")
        return " | ".join(parts)
