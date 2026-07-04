# PromptCanary

**Detect silent behavioral drift in LLM providers — before it breaks production.**

---

## The Problem

LLM providers frequently update their models without changing the model string
or announcing behavioral shifts. JSON keys reorder. Reasoning style changes.
Refusals trigger on prompts that passed last week. Your downstream parser
breaks silently, with no exception and no warning — until a user reports it.

## The Solution

```bash
pip install promptcanary
promptcanary init my-suite
promptcanary run --provider openai/gpt-5.4 --save-baseline

# One week later...
promptcanary compare --provider openai/gpt-5.4 --fail-on-drift
```

```
⚠️  HIGH drift in 'my-suite': 3 regression(s) detected
    Score: 94.0% → 71.0% (Δ -23.0%)
```

## Why PromptCanary

<div class="grid cards" markdown>

- :material-lightning-bolt: **Fast setup**
  Working canary suite in under 10 minutes — `init`, edit, `run`.

- :material-puzzle: **19 built-in probes**
  Format, reasoning, safety, factual, and tool-use categories out of the box.

- :material-cog: **Any provider**
  OpenAI, Anthropic, Gemini, xAI, or free local models via Ollama — one interface.

- :material-robot: **CI-native**
  GitHub Actions integration with `--fail-on-drift` exit codes and PR comments.

- :material-chart-line: **Trend visualization**
  Score history, probe heatmaps, drift timelines — ASCII or interactive Plotly.

- :material-language-python: **Fully typed**
  Pydantic v2 throughout, 89%+ test coverage, mypy strict mode.

</div>

## Where to Start

- New to PromptCanary? → [Quick Start](getting-started/quickstart.md)
- Want the full probe list? → [Probe Reference](probes/index.md)
- Setting up CI? → [GitHub Actions](ci-cd/github-actions.md)
- Writing a custom probe? → [Custom Probes](probes/custom.md)
- Want the architecture rationale? → [Decision Log](decision-log.md)

## Quick Example

```python
from promptcanary import (
    CanarySuite, LiteLLMProvider, FileBaselineStore,
    CanaryPrompt, JsonValidityProbe, compare,
)

suite = CanarySuite(
    name="production-agent",
    prompts=[CanaryPrompt(text='Return JSON: {"status": "ok"}')],
    probes=[JsonValidityProbe()],
)

provider = LiteLLMProvider("openai/gpt-5.4", temperature=0.0)
result = suite.run(provider)

store = FileBaselineStore("baselines/")
snapshot = store.save(result)

# Later...
new_result = suite.run(provider)
drift = compare(snapshot, new_result)
print(drift.summary)
```

---

*PromptCanary is MIT-licensed and built for AI engineers who care about
production reliability. [View on GitHub](https://github.com/Mattral/PromptCanary) ·
[View on PyPI](https://pypi.org/project/promptcanary/)*
