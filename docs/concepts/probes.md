# Probes

A probe is a stateless, callable unit that evaluates one
`(CanaryPrompt, LLMResponse)` pair and returns a `ProbeResult`.

## The Probe Contract

Every probe — built-in or custom — follows the same interface:

```python
class BaseProbe(abc.ABC):
    probe_id: str
    name: str
    category: ProbeCategory
    description: str

    @abc.abstractmethod
    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        ...
```

Calling a probe instance directly (`probe(prompt, response)`) is equivalent
to calling `.evaluate(prompt, response)`.

## ProbeResult

| Field | Type | Meaning |
|-------|------|---------|
| `passed` | `bool` | Binary pass/fail — used for CI gating. |
| `score` | `float` | Normalised 0.0–1.0 score — used for trend tracking and partial credit. |
| `details` | `str` | Human-readable explanation, shown in all reports. |
| `metadata` | `dict` | Probe-specific diagnostic data (e.g. which keys were missing). |

`passed` and `score` are intentionally separate: a probe can give partial
credit (`score=0.75`) while still marking the result as failed
(`passed=False`) if a hard requirement wasn't met.

## Categories

| Category | Purpose |
|----------|---------|
| `FORMAT` | Output structure: JSON validity, key order, length, headers. |
| `REASONING` | Reasoning style: step-by-step, verbosity, confidence, preamble. |
| `SAFETY` | Refusals and safety disclaimers. |
| `TOOL_USE` | Function/tool call presence, name, arguments, schema. |
| `FACTUAL` | Fixed-answer factual consistency, sentiment. |
| `CUSTOM` | User-defined probes that don't fit the above. |

See the full [Probe Reference](../probes/index.md) for every built-in probe.

## The Probe Registry

Every `BaseProbe` subclass with a non-empty `probe_id` is automatically
registered when its module is imported — no manual registration step.

```python
from promptcanary.core.probes import get_probe_registry, get_probe

registry = get_probe_registry()
print(list(registry.keys()))
# ['json_validity', 'json_schema', 'step_by_step', ...]

probe_cls = get_probe("json_validity")
probe = probe_cls()
```

This registry is what powers YAML config loading — the `type:` field in
`canary.yaml` is looked up against `probe_id`.

## Writing Custom Probes

See [Writing Custom Probes](../probes/custom.md) for the full guide,
including the `@probe` decorator for simple cases and the `BaseProbe`
subclass pattern for stateful, configurable probes.
