# Google Gemini

```bash
export GEMINI_API_KEY=...
```

```python
from promptcanary import LiteLLMProvider

provider = LiteLLMProvider("gemini/gemini-3.5-flash", temperature=0.0)
```

## Recommended Models

| Tier | Model string | Notes |
|------|---------------|-------|
| Flagship | `gemini/gemini-3.1-pro` | Highest capability, strongest reasoning. |
| Balanced | `gemini/gemini-3.5-flash` | Good default — fast and capable. |
| Fast / cheap | `gemini/gemini-3.1-flash-lite` | Cheapest Gemini 3 tier, good for frequent checks. |

## CLI Usage

```bash
promptcanary run --provider gemini/gemini-3.5-flash --save-baseline
promptcanary compare --provider gemini/gemini-3.5-flash --fail-on-drift
```

## Multi-Provider Example

A common pattern is running the same suite across OpenAI, Gemini, and a
free local model to spot provider-specific drift versus universal harness
issues:

```python
from promptcanary import CanarySuite, LiteLLMProvider

suite = CanarySuite.from_yaml("canary.yaml")

for model_id in [
    "openai/gpt-5.4",
    "gemini/gemini-3.5-flash",
    "ollama/qwen3.6:27b",
]:
    provider = LiteLLMProvider(model_id, temperature=0.0)
    result = suite.run(provider, show_progress=False)
    print(f"{model_id:35s}  score={result.overall_score:.1%}")
```

If only one provider regresses, the issue is provider-specific drift. If
all three regress simultaneously, suspect your suite's prompts or your
own harness instead.
