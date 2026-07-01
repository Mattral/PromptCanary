# LangChain Integration

PromptCanary doesn't require LangChain, but it's common to test the LLM
backing a LangChain chain or agent. Two patterns work well.

## Pattern 1: Test the Underlying Model Directly

Most of the time, you want to canary-test the model itself, independent
of LangChain's prompt templates — this is what `LiteLLMProvider` already
does, since LangChain typically wraps the same providers PromptCanary
supports natively.

```python
from promptcanary import CanarySuite, LiteLLMProvider

# If your LangChain chain uses ChatOpenAI(model="gpt-5.4"), test the
# same underlying model directly:
suite = CanarySuite.from_yaml("canary.yaml")
provider = LiteLLMProvider("openai/gpt-5.4")
result = suite.run(provider)
```

## Pattern 2: Wrap Your LangChain Chain as a Custom Provider

If you want to test your *full* LangChain pipeline (including prompt
templates, output parsers, and retrieval) rather than the raw model,
wrap it in a `BaseLLMProvider`:

```python
from promptcanary.providers.base import BaseLLMProvider
from promptcanary.core.models import CanaryPrompt, LLMResponse, ProviderConfig

class LangChainProvider(BaseLLMProvider):
    """Wraps a LangChain chain so it can be canary-tested end-to-end."""

    def __init__(self, chain, model_id: str = "langchain/custom-chain"):
        super().__init__(ProviderConfig(model_id=model_id))
        self.chain = chain

    def complete(self, prompt: CanaryPrompt, *, system_prompt: str | None = None) -> LLMResponse:
        result = self.chain.invoke({"input": prompt.text})
        content = result.get("output", str(result)) if isinstance(result, dict) else str(result)
        return LLMResponse(
            prompt_id=prompt.id,
            provider_model_id=self.config.model_id,
            content=content,
            finish_reason="stop",
        )


# Usage:
# from your_app import my_langchain_chain
# provider = LangChainProvider(my_langchain_chain)
# result = suite.run(provider)
```

This approach catches drift introduced anywhere in your pipeline — prompt
template changes, retrieval result shifts, output parser bugs — not just
raw model behavior.

## Which Pattern to Choose

| Goal | Pattern |
|------|---------|
| Detect provider-side model drift | Pattern 1 — direct `LiteLLMProvider` |
| Detect drift in your full RAG/agent pipeline | Pattern 2 — wrap the chain |
| Both | Run both suites; compare results to isolate where drift originates |
