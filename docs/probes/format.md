# Format & Structure Probes

These probes detect changes in *how* a model formats its output — JSON
validity, schema, key order, length, headers, and keyword presence.

## JsonValidityProbe

`probe_id: json_validity`

Checks whether the response is valid JSON. Strips markdown code fences
(` ```json ... ``` `) before parsing.

```python
from promptcanary.core.probes import JsonValidityProbe
probe = JsonValidityProbe()
```

**Score:** `1.0` if valid JSON, `0.0` otherwise (binary).

---

## JsonSchemaProbe

`probe_id: json_schema`

Checks for required/forbidden keys in a JSON object.

```python
from promptcanary.core.probes import JsonSchemaProbe

probe = JsonSchemaProbe(
    required_keys=["name", "age"],
    forbidden_keys=["password", "ssn"],
    score_per_key=True,   # partial credit for partial matches
)
```

**Score:** Fraction of `required_keys` present, halved if any
`forbidden_keys` are found.

---

## JsonKeyOrderProbe

`probe_id: json_key_order`

Detects key reordering using a longest-common-subsequence comparison —
useful because some downstream parsers are sensitive to field order even
though JSON technically isn't ordered.

```python
from promptcanary.core.probes import JsonKeyOrderProbe

probe = JsonKeyOrderProbe(expected_order=["name", "age", "email"])
```

**Score:** LCS-based similarity (0.0–1.0). Passes at ≥ 0.9 to tolerate minor reordering.

---

## ResponseLengthProbe

`probe_id: response_length`

Catches verbosity explosions or sudden brevity, either via hard bounds or
drift relative to a baseline length.

```python
from promptcanary.core.probes import ResponseLengthProbe

probe = ResponseLengthProbe(
    min_chars=10,
    max_chars=2000,
    baseline_chars=500,   # optional — enables drift scoring
    tolerance=0.5,         # ±50% before penalty applies
)
```

**Score:** `1.0` within bounds; degrades linearly outside tolerance when
`baseline_chars` is set.

---

## MarkdownHeaderProbe

`probe_id: markdown_headers`

Verifies expected markdown section headers (`#`–`######`) are present.

```python
from promptcanary.core.probes import MarkdownHeaderProbe

probe = MarkdownHeaderProbe(
    expected_headers=["Summary", "Details", "Next Steps"],
    case_sensitive=False,
)
```

**Score:** Fraction of expected headers found.

---

## KeywordPresenceProbe

`probe_id: keyword_presence`

Required/forbidden keyword matching — the most flexible, general-purpose
format probe.

```python
from promptcanary.core.probes import KeywordPresenceProbe

probe = KeywordPresenceProbe(
    required_keywords=["Paris"],
    forbidden_keywords=["I cannot help", "As an AI language model"],
    case_sensitive=False,
)
```

**Score:** `1.0 − (violations / total_checks)`.

---

## ExpectedKeywordsProbe

`probe_id: expected_keywords`

Zero-configuration probe that reads `expected_keywords` directly from the
`CanaryPrompt` — convenient when you've already declared keywords on the
prompt and don't want to repeat them in the probe config.

```yaml
prompts:
  - text: "What is the capital of France?"
    expected_keywords: ["Paris"]
probes:
  - type: expected_keywords   # no extra config needed
```

**Score:** Fraction of `prompt.expected_keywords` found in the response.
Always passes (with a note) if the prompt has no `expected_keywords` set.
