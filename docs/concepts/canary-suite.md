# CanarySuite

`CanarySuite` is the central orchestrator: it holds prompts and probes, and
drives the run loop against a provider.

## Construction

### From Python

```python
from promptcanary import CanarySuite, CanaryPrompt
from promptcanary.core.probes import JsonValidityProbe, KeywordPresenceProbe

suite = CanarySuite(
    name="my-suite",
    description="Optional description shown in reports.",
    prompts=[
        CanaryPrompt(
            id="geo001",                       # optional, auto-generated if omitted
            text="What is the capital of France?",
            expected_keywords=["Paris"],
            tags=["geography"],
        ),
    ],
    probes=[
        KeywordPresenceProbe(required_keywords=["Paris"]),
        JsonValidityProbe(),
    ],
    default_system_prompt="You are a helpful assistant.",  # optional
)
```

### From YAML

```python
suite = CanarySuite.from_yaml("canary.yaml")
```

```yaml
name: my-suite
description: "Optional description"
default_system_prompt: "You are a helpful assistant."
probes:
  - type: keyword_presence
    required_keywords: ["Paris"]
  - type: json_validity
prompts:
  - text: "What is the capital of France?"
    expected_keywords: ["Paris"]
```

Both `prompts` and `probes` accept a shorthand string form:

```yaml
probes:
  - json_validity          # equivalent to {type: json_validity}
prompts:
  - "What is the capital of France?"   # equivalent to {text: "..."}
```

## CanaryPrompt

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Stable identifier. Auto-generated (8 hex chars) if omitted. |
| `text` | `str` | The prompt text sent to the LLM. Required, non-empty. |
| `tags` | `list[str]` | Optional free-form tags. |
| `description` | `str` | Human-readable note shown in reports. |
| `system_prompt` | `str \| None` | Per-prompt system prompt override. |
| `expected_keywords` | `list[str]` | Convenience field used by `ExpectedKeywordsProbe`. |

## Running

```python
result = suite.run(
    provider,
    temperature=0.0,     # override provider default
    max_tokens=1024,
    seed=42,
    show_progress=True,  # Rich progress bar
)
```

Returns a `CanaryRunResult` with:

| Property | Description |
|----------|--------------|
| `overall_score` | Mean score across all probe results (0.0–1.0). |
| `pass_rate` | Fraction of probes that passed. |
| `failed_probes` | List of `ProbeResult` objects that did not pass. |
| `by_category` | Probe results grouped by `ProbeCategory`. |
| `duration_ms` | Total wall-clock run time. |

## Error Handling

If a probe raises an exception during evaluation, `CanarySuite.run()` catches
it and converts it into a failed `ProbeResult` rather than crashing the run.
This means a single buggy custom probe can never take down an entire canary
run — see [ADR in the Decision Log](../decision-log.md) for the rationale.

## Reusability

A `CanarySuite` instance is stateless and can be reused across multiple
providers and multiple runs:

```python
gpt_result = suite.run(LiteLLMProvider("openai/gpt-5.4"))
gemini_result = suite.run(LiteLLMProvider("gemini/gemini-3.5-flash"))
local_result = suite.run(LiteLLMProvider("ollama/qwen3.6:27b"))
```
