# Tool Use Probes

For agent workflows where model output drives downstream function dispatch,
silent changes to function names, argument keys, or call structure break
parsers without raising any exception. These probes are designed for that
exact failure mode.

All four probes parse OpenAI's `tool_calls` format, Anthropic's
`name`/`input` format, and plain `{"function": ..., "args": ...}` JSON —
no configuration needed to handle multiple provider conventions.

## ToolCallPresenceProbe

`probe_id: tool_call_presence`

Detects whether *any* tool/function call is present in the response.

```python
from promptcanary.core.probes import ToolCallPresenceProbe

probe = ToolCallPresenceProbe(expect_tool_call=True, strategy="auto")
```

`strategy` controls detection: `"auto"` (JSON parse, fall back to text
patterns), `"json"` (JSON only), or `"text"` (regex patterns only).

**Score:** Binary — `1.0` if expectation matches.

---

## ToolCallNameProbe

`probe_id: tool_call_name`

Checks that the model calls a *specific* named function.

```python
from promptcanary.core.probes import ToolCallNameProbe

probe = ToolCallNameProbe(
    "search_web",
    case_sensitive=False,
    allow_aliases=["web_search"],   # accept legacy/alternate names too
)
```

**Score:**

- `1.0` — correct function name found
- `0.3` — a *different* function was called (a meaningful drift signal,
  distinguished from total failure)
- `0.0` — no function call detected at all

---

## ToolCallArgsProbe

`probe_id: tool_call_args`

Verifies required arguments are present (and forbidden ones absent) in the
extracted call.

```python
from promptcanary.core.probes import ToolCallArgsProbe

probe = ToolCallArgsProbe(
    required_args=["query", "limit"],
    forbidden_args=["api_key"],   # catch credential leakage into the call
)
```

**Score:** Fraction of `required_args` present, halved if any
`forbidden_args` leak through.

---

## ToolCallSchemaProbe

`probe_id: tool_call_schema`

Full structural validation combining name, argument presence, and argument
*types* into a single weighted score — the most comprehensive tool-call
probe, suited to tightly-specified agent pipelines.

```python
from promptcanary.core.probes import ToolCallSchemaProbe

probe = ToolCallSchemaProbe(schema={
    "name": "search_web",
    "required_args": ["query", "limit"],
    "forbidden_args": ["api_key"],
    "arg_types": {"query": str, "limit": int},
})
```

**Score:** Weighted average — name (40%), argument presence (40%), argument
types (20%). Passes at ≥ 0.85.

## Example: Full Agent Canary Suite

```yaml
name: search-agent-suite
probes:
  - type: tool_call_schema
    schema:
      name: search_web
      required_args: ["query", "limit"]
      arg_types:
        query: str
        limit: int
prompts:
  - text: "Search the web for the latest news about renewable energy. Limit to 5 results."
```

This single probe catches: the model not calling a function at all, calling
the wrong function, missing the `limit` argument, or returning `limit` as a
string instead of an integer — all common silent regressions in agent
pipelines.
