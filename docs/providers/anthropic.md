# Anthropic

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

```python
from promptcanary import LiteLLMProvider

provider = LiteLLMProvider("anthropic/claude-sonnet-4-6", temperature=0.0)
```

## Recommended Models

| Tier | Model string | Notes |
|------|---------------|-------|
| Flagship | `anthropic/claude-opus-4-8` | Highest capability tier. |
| Balanced | `anthropic/claude-sonnet-4-6` | Strong default for most canary suites. |

## CLI Usage

```bash
promptcanary run --provider anthropic/claude-sonnet-4-6 --save-baseline
promptcanary compare --provider anthropic/claude-sonnet-4-6 --fail-on-drift
```

## A Note on Reasoning-Style Probes

Anthropic models historically default to more structured, step-by-step
reasoning on complex prompts than some competitors. If your suite uses
`StepByStepProbe(expect_steps=False)`, calibrate your baseline against
Anthropic specifically — what counts as "verbose" or "direct" varies
meaningfully across providers, which is exactly why baselines are
per-provider rather than universal.
