# Supported Providers

PromptCanary works with any provider supported by
[LiteLLM](https://docs.litellm.ai/docs/providers) — cloud or local, paid or
free — through a single unified interface: `LiteLLMProvider`.

## Provider Comparison

| Provider | Example model string | API key env var | Cost |
|----------|----------------------|------------------|------|
| OpenAI | `openai/gpt-5.5`, `openai/gpt-5.4`, `openai/gpt-5.4-mini` | `OPENAI_API_KEY` | Paid |
| Anthropic | `anthropic/claude-opus-4-8`, `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` | Paid |
| Google Gemini | `gemini/gemini-3.1-pro`, `gemini/gemini-3.5-flash`, `gemini/gemini-3.1-flash-lite` | `GEMINI_API_KEY` | Paid |
| xAI | `xai/grok-4` | `XAI_API_KEY` | Paid |
| **Ollama (local)** | `ollama/qwen3.6:27b`, `ollama/deepseek-r1:14b`, `ollama/gpt-oss:20b` | *(none)* | **Free** |
| vLLM (self-hosted) | `hosted_vllm/<org>/<model>` | *(none)* | Free (self-hosted compute) |

!!! note "Model availability changes quickly"
    LLM providers release new models frequently. The model strings above
    were current as of mid-2026 — check
    [LiteLLM's provider documentation](https://docs.litellm.ai/docs/providers)
    for the latest before relying on any specific string in production.

## Basic Usage

```python
from promptcanary import LiteLLMProvider

provider = LiteLLMProvider(
    "openai/gpt-5.4",
    temperature=0.0,    # recommended for reproducibility
    max_tokens=1024,
    seed=42,
)
```

## Per-Provider Guides

- [OpenAI](openai.md)
- [Anthropic](anthropic.md)
- [Google Gemini](gemini.md)
- [Local Models via Ollama](ollama.md)

## Why Test Free, Local Models Too?

Local, open-weight models (via Ollama or vLLM) make excellent **zero-cost
canaries**: running them hourly costs nothing and catches
infrastructure-level regressions (prompt template bugs, parser issues,
malformed YAML) independent of any vendor's API changes. They're also
useful as an early-warning layer that runs far more frequently than your
paid-provider checks — see the
[multi-provider scheduling strategy](../ci-cd/multi-provider.md) for a
concrete cost-aware setup.

## Custom Providers

If LiteLLM doesn't support your backend, implement `BaseLLMProvider`
directly:

```python
from promptcanary.providers.base import BaseLLMProvider
from promptcanary.core.models import CanaryPrompt, LLMResponse, ProviderConfig

class MyCustomProvider(BaseLLMProvider):
    def __init__(self):
        super().__init__(ProviderConfig(model_id="custom/my-model"))

    def complete(self, prompt: CanaryPrompt, *, system_prompt: str | None = None) -> LLMResponse:
        # Call your backend here
        content = my_backend_call(prompt.text, system_prompt)
        return LLMResponse(
            prompt_id=prompt.id,
            provider_model_id=self.config.model_id,
            content=content,
            finish_reason="stop",
        )
```

`MyCustomProvider` is a drop-in replacement for `LiteLLMProvider` anywhere
in the SDK or CLI.
