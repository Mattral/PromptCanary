# LlamaIndex Integration

LlamaIndex-based RAG pipelines introduce an extra drift surface beyond the
raw model: retrieval quality and context assembly can shift silently even
when the underlying LLM hasn't changed. Two patterns cover most needs.

## Pattern 1: Test the Underlying LLM Directly

If you only care about model-level drift (not retrieval), test the same
model your LlamaIndex `Settings.llm` points to, using `LiteLLMProvider`
directly -- no LlamaIndex dependency needed for this path.

```python
from promptcanary import CanarySuite, LiteLLMProvider

# If your LlamaIndex app uses:
#   Settings.llm = OpenAI(model="gpt-5.4")
# test the same model directly:
suite = CanarySuite.from_yaml("canary.yaml")
provider = LiteLLMProvider("openai/gpt-5.4")
result = suite.run(provider)
```

## Pattern 2: Wrap Your Query Engine as a Custom Provider

To canary-test your full RAG pipeline -- retrieval, context assembly,
synthesis -- wrap your LlamaIndex query engine in a `BaseLLMProvider`:

```python
from promptcanary.providers.base import BaseLLMProvider
from promptcanary.core.models import CanaryPrompt, LLMResponse, ProviderConfig

class LlamaIndexProvider(BaseLLMProvider):
    """Wraps a LlamaIndex query engine for end-to-end canary testing."""

    def __init__(self, query_engine, model_id: str = "llamaindex/custom-rag"):
        super().__init__(ProviderConfig(model_id=model_id))
        self.query_engine = query_engine

    def complete(self, prompt: CanaryPrompt, *, system_prompt: str | None = None) -> LLMResponse:
        response = self.query_engine.query(prompt.text)
        return LLMResponse(
            prompt_id=prompt.id,
            provider_model_id=self.config.model_id,
            content=str(response),
            finish_reason="stop",
            raw_response={"source_node_count": len(getattr(response, "source_nodes", []))},
        )


# Usage:
# from your_app import my_query_engine
# provider = LlamaIndexProvider(my_query_engine)
# result = suite.run(provider)
```

This catches drift from anywhere in the pipeline: embedding model changes,
index rebuilds that shift retrieval results, chunking strategy edits, or
synthesis prompt changes -- not just the underlying LLM.

## Detecting Retrieval Drift Specifically

If you want to isolate *retrieval* drift from *generation* drift, add a
custom probe that inspects the retrieved-node count (captured above in
`raw_response`) rather than only the final answer text:

```python
from promptcanary.core.probes.base import BaseProbe
from promptcanary.core.models import CanaryPrompt, LLMResponse, ProbeCategory

class RetrievalCountProbe(BaseProbe):
    """Flags when the number of retrieved source nodes changes unexpectedly."""

    probe_id = "retrieval_count"
    name = "Retrieval Node Count"
    category = ProbeCategory.CUSTOM

    def __init__(self, expected_min: int = 1) -> None:
        self.expected_min = expected_min

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse):
        count = response.raw_response.get("source_node_count", 0)
        passed = count >= self.expected_min
        return self._make_result(
            prompt.id,
            passed=passed,
            score=1.0 if passed else 0.0,
            details=f"Retrieved {count} source node(s) (min expected: {self.expected_min}).",
        )
```

`LLMResponse.raw_response` is a `dict[str, Any]` field designed exactly
for this: stashing pipeline-specific metadata that a custom probe can
read back, without needing to extend the core model.

## Which Pattern to Choose

| Goal | Pattern |
|------|---------|
| Detect provider-side model drift only | Pattern 1 -- direct `LiteLLMProvider` |
| Detect drift anywhere in your RAG pipeline | Pattern 2 -- wrap the query engine |
| Isolate retrieval drift from generation drift | Pattern 2 + a custom retrieval-aware probe |
| Both model and pipeline coverage | Run both suites; a regression in Pattern 1 only means the model changed; a regression in Pattern 2 only means your pipeline changed |
