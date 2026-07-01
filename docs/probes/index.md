# Probe Reference

PromptCanary ships with 19 built-in probes across five categories. Each
probe is independently configurable and composable — mix and match to
build a suite that covers the drift dimensions that matter to you.

## By Category

| Category | Probes | Use when... |
|----------|--------|--------------|
| [Format & Structure](format.md) | 7 probes | You care about JSON validity, schema, key order, length, headers, keywords |
| [Reasoning Style](reasoning.md) | 4 probes | You care about step-by-step reasoning, verbosity, hedging, preamble |
| [Safety & Refusal](safety.md) | 2 probes | You care about refusal behavior or disclaimer injection |
| [Tool Use](tool-use.md) | 4 probes | You're running agent workflows with function/tool calling |
| [Factual](factual.md) | 2 probes | You have fixed-answer prompts or care about tone/sentiment |

## Quick Reference Table

| `probe_id` | Class | Category |
|-----------|-------|----------|
| `json_validity` | `JsonValidityProbe` | format |
| `json_schema` | `JsonSchemaProbe` | format |
| `json_key_order` | `JsonKeyOrderProbe` | format |
| `response_length` | `ResponseLengthProbe` | format |
| `markdown_headers` | `MarkdownHeaderProbe` | format |
| `keyword_presence` | `KeywordPresenceProbe` | format |
| `expected_keywords` | `ExpectedKeywordsProbe` | format |
| `step_by_step` | `StepByStepProbe` | reasoning |
| `verbosity` | `VerbosityProbe` | reasoning |
| `confidence_language` | `ConfidenceLanguageProbe` | reasoning |
| `direct_answer` | `DirectAnswerProbe` | reasoning |
| `refusal` | `RefusalProbe` | safety |
| `safety_language` | `SafetyLanguageProbe` | safety |
| `tool_call_presence` | `ToolCallPresenceProbe` | tool_use |
| `tool_call_name` | `ToolCallNameProbe` | tool_use |
| `tool_call_args` | `ToolCallArgsProbe` | tool_use |
| `tool_call_schema` | `ToolCallSchemaProbe` | tool_use |
| `factual_consistency` | `FactualConsistencyProbe` | factual |
| `sentiment` | `SentimentProbe` | reasoning |

## Using Probes in YAML

Reference any probe by its `probe_id` with constructor arguments as keys:

```yaml
probes:
  - type: json_schema
    required_keys: ["name", "age"]
    forbidden_keys: ["password"]
  - type: refusal
    expect_refusal: false
```

## Using Probes in Python

```python
from promptcanary.core.probes import JsonSchemaProbe, RefusalProbe

probes = [
    JsonSchemaProbe(required_keys=["name", "age"], forbidden_keys=["password"]),
    RefusalProbe(expect_refusal=False),
]
```

## Don't See What You Need?

See [Writing Custom Probes](custom.md) — most custom probes take under
20 lines of code using the `@probe` decorator.
