"""
promptcanary.providers
~~~~~~~~~~~~~~~~~~~~~~~

LLM provider adapters for PromptCanary.

The default and recommended provider is :class:`LiteLLMProvider`, which
supports 100+ models via a single interface.

Custom providers can be built by subclassing :class:`BaseLLMProvider`
and implementing the ``complete()`` method.
"""

from promptcanary.providers.base import BaseLLMProvider, ProviderError
from promptcanary.providers.litellm import LiteLLMProvider

__all__ = [
    "BaseLLMProvider",
    "LiteLLMProvider",
    "ProviderError",
]
