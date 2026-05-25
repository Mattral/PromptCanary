# OpenAI

```bash
export OPENAI_API_KEY=sk-...
```

```python
from promptcanary import LiteLLMProvider

provider = LiteLLMProvider("openai/gpt-5.4", temperature=0.0)
```

## Recommended Models

| Tier | Model string | Notes |
|------|---------------|-------|
| Flagship | `openai/gpt-5.5` | Highest capability, highest cost. |
| Balanced | `openai/gpt-5.4` | Good default for most canary suites. |
| Fast / cheap | `openai/gpt-5.4-mini` | Suitable for frequent (hourly/daily) checks. |

## CLI Usage

```bash
promptcanary run --provider openai/gpt-5.4 --save-baseline
promptcanary compare --provider openai/gpt-5.4 --fail-on-drift
```

## JSON Mode

To test structured output specifically, pass `response_format` through
`extra_params`:

```python
provider = LiteLLMProvider(
    "openai/gpt-5.4",
    extra_params={"response_format": {"type": "json_object"}},
)
```

Pair this with `JsonValidityProbe` and `JsonSchemaProbe` to catch any
regression in structured-output reliability.

## Cost Awareness

OpenAI's flagship models are the most expensive tier in most canary
matrices. See [Multi-Provider Matrix](../ci-cd/multi-provider.md) for a
scheduling strategy that runs expensive models weekly while cheaper or
free models run more frequently.
