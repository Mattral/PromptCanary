# 🐦 PromptCanary

**Detect silent behavioral drift in LLM providers — before it breaks production.**

[![CI](https://github.com/promptcanary/actions/workflows/ci.yml/badge.svg)](https://github.com/promptcanary/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/promptcanary.svg)](https://pypi.org/project/promptcanary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)

---

> *LLM providers frequently update their models without changing the model string or announcing behavioral shifts. These changes cause silent regressions that are expensive to debug. PromptCanary catches them automatically.*

---

## The Problem

You ship a production AI assistant. Everything works. Then one day — with no API change, no model rename, no announcement — the behavior shifts. JSON keys reorder. Step-by-step reasoning appears where it didn't before. Refusals trigger on edge cases that passed last week. Your downstream parser breaks. Your agent loop fails.

**Silent model drift is real, common, and expensive.**

## The Solution

```bash
pip install promptcanary
promptcanary init my-suite
promptcanary run --provider openai/gpt-4o --save-baseline

# One week later... run again and compare:
promptcanary compare --provider openai/gpt-4o --fail-on-drift
```

```
⚠️  HIGH drift in 'my-suite': 3 regression(s) detected
    Score: 94.0% → 71.0% (Δ -23.0%)

┌─ Regressions ────────────────────────────────────────────────────────────────┐
│ JSON Validity    │ format   │ prompt_3 │ 1.00 → 0.00 │ Δ -1.00 │ JSON parse  │
│ Direct Answer    │ reason   │ prompt_1 │ 1.00 → 0.00 │ Δ -1.00 │ Preamble    │
│ Response Length  │ format   │ prompt_5 │ 0.92 → 0.51 │ Δ -0.41 │ 4x longer   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Features

- 🔌 **Works with any provider** — OpenAI, Anthropic, Google, Ollama, vLLM, and 100+ more via [LiteLLM](https://github.com/BerriAI/litellm)
- 📋 **15 built-in probes** across format, reasoning, safety, and factual categories
- 🔧 **Custom probes** — one decorator, zero boilerplate
- 📊 **Rich reports** — terminal, Markdown, HTML, and JSON
- 🤖 **GitHub Actions native** — scheduled checks, PR comments, auto-issue on drift
- ⚡ **Fast setup** — working canary in under 10 minutes
- 🧪 **CI-ready** — `--fail-on-drift` exits non-zero for automated gating
- 🏗️ **Clean architecture** — Pydantic v2, fully typed, 80%+ test coverage

---

## Quick Start

### Install

```bash
pip install promptcanary
```

### 1. Scaffold a suite

```bash
promptcanary init my-suite
cd my-suite
```

Edit `canary.yaml` to describe the prompts and behaviors that matter to you:

```yaml
name: my-production-suite
probes:
  - type: json_validity
  - type: direct_answer
    expect_direct: true
  - type: refusal
    expect_refusal: false
prompts:
  - text: "Return JSON: {name: 'Alice', role: 'engineer'}"
    description: "Core JSON format canary"
  - text: "What is the capital of France? One sentence."
    expected_keywords: ["Paris"]
```

### 2. Run and save baseline

```bash
export OPENAI_API_KEY=sk-...
promptcanary run --provider openai/gpt-5.4 --save-baseline
```

```
┌─ PromptCanary Run Report ────────────────────────────────────────────────────┐
│ my-production-suite  ·  Score: 100.0%  ·  Pass rate: 100.0%  ·  openai/gpt-5.4
└──────────────────────────────────────────────────────────────────────────────┘
✅ All probes passed.
✅ Baseline saved: baselines/my-suite__openai-gpt-5.4__20260629T090000_abc12345.json
```

### 3. Detect drift

```bash
# Run whenever you want to check — daily, weekly, or in CI:
promptcanary compare --provider openai/gpt-5.4 --fail-on-drift
```

### Prefer a free, local model? Use Ollama instead — no API key needed:

```bash
ollama pull qwen3.6:27b
promptcanary run --provider ollama/qwen3.6:27b --save-baseline
promptcanary compare --provider ollama/qwen3.6:27b --fail-on-drift
```

---

## Python SDK

```python
from promptcanary import (
    CanarySuite, LiteLLMProvider, FileBaselineStore,
    CanaryPrompt, JsonValidityProbe, StepByStepProbe,
    KeywordPresenceProbe, compare,
)
from promptcanary.core.reporter import Reporter, DriftReporter

# ── Build suite ───────────────────────────────────────────────────────────────
suite = CanarySuite(
    name="production-agent",
    prompts=[
        CanaryPrompt(
            text='Return JSON: {"action": "search", "query": "Paris weather"}',
            expected_keywords=["action", "query"],
        ),
        CanaryPrompt(
            text="What is the capital of France? One sentence.",
            expected_keywords=["Paris"],
        ),
    ],
    probes=[
        JsonValidityProbe(),
        KeywordPresenceProbe(required_keywords=["Paris"]),
        StepByStepProbe(expect_steps=False),
    ],
)

provider = LiteLLMProvider("openai/gpt-5.4", temperature=0.0)

# ── Run ───────────────────────────────────────────────────────────────────────
result = suite.run(provider)
Reporter(result).print_terminal()

# ── Save baseline ─────────────────────────────────────────────────────────────
store = FileBaselineStore("baselines/")
snapshot = store.save(result)

# ── Compare ───────────────────────────────────────────────────────────────────
new_result = suite.run(provider)
drift = compare(snapshot, new_result)
DriftReporter(drift).print_terminal()

if drift.has_drift:
    print(drift.summary)
    # ⚠️ HIGH drift in 'production-agent': 2 regression(s) detected ...
```

### Using Google Gemini instead

```python
provider = LiteLLMProvider("gemini/gemini-3.5-flash", temperature=0.0)
result = suite.run(provider)
```

### Using a free, local model via Ollama (no API key, zero cost)

```python
# 1. Install Ollama and pull a model: `ollama pull qwen3.6:27b`
provider = LiteLLMProvider("ollama/qwen3.6:27b", temperature=0.0)
result = suite.run(provider)
```

### Load from YAML

```python
from promptcanary import CanarySuite, LiteLLMProvider

suite = CanarySuite.from_yaml("canary.yaml")
provider = LiteLLMProvider("anthropic/claude-sonnet-4-6")
result = suite.run(provider)
```

---

## Built-in Probes

### Format & Structure

| Probe | Detects |
|-------|---------|
| `JsonValidityProbe` | Invalid JSON output |
| `JsonSchemaProbe(required_keys=[...])` | Missing or forbidden JSON keys |
| `JsonKeyOrderProbe(expected_order=[...])` | Key reordering in JSON output |
| `ResponseLengthProbe(min=10, max=4000)` | Length explosions or sudden brevity |
| `MarkdownHeaderProbe(expected_headers=[...])` | Missing section headers |
| `KeywordPresenceProbe(required=[...], forbidden=[...])` | Keyword drift |
| `ExpectedKeywordsProbe` | Keywords declared on `CanaryPrompt.expected_keywords` |

### Reasoning Style

| Probe | Detects |
|-------|---------|
| `StepByStepProbe(expect_steps=True)` | Loss or gain of chain-of-thought reasoning |
| `VerbosityProbe(expected_words=200)` | Word count drift |
| `ConfidenceLanguageProbe(expect_hedging=False)` | Hedging vs. confident language shifts |
| `DirectAnswerProbe(expect_direct=True)` | "Sure!", "Great question!" preamble |

### Safety & Refusal

| Probe | Detects |
|-------|---------|
| `RefusalProbe(expect_refusal=False)` | Unexpected refusals (or missing ones) |
| `SafetyLanguageProbe(expect_safety_language=False)` | New disclaimer injection |

### Tool Use (Agent Workflows)

| Probe | Detects |
|-------|---------|
| `ToolCallPresenceProbe(expect_tool_call=True)` | Missing or unexpected function calls |
| `ToolCallNameProbe("search_web", allow_aliases=[...])` | Wrong function called |
| `ToolCallArgsProbe(required_args=[...], forbidden_args=[...])` | Missing/leaked arguments |
| `ToolCallSchemaProbe(schema={...})` | Full structural validation (name + args + types) |

### Factual

| Probe | Detects |
|-------|---------|
| `FactualConsistencyProbe("Paris")` | Drift from known-correct answer |
| `SentimentProbe(expect_positive=None)` | Tone shifts |

---

## Custom Probes

```python
from promptcanary.core.probes.base import probe
from promptcanary.core.models import CanaryPrompt, LLMResponse, ProbeCategory, ProbeResult

@probe("tool_call_format", name="Tool Call Format", category=ProbeCategory.CUSTOM)
def check_tool_call(prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
    """Verify the model always calls the search tool when asked to search."""
    has_tool_call = '"function": "search"' in response.content
    return ProbeResult(
        probe_id="tool_call_format",
        probe_name="Tool Call Format",
        category=ProbeCategory.CUSTOM,
        prompt_id=prompt.id,
        passed=has_tool_call,
        score=1.0 if has_tool_call else 0.0,
        details="Tool call found." if has_tool_call else "Expected tool call missing.",
    )
```

Custom probes are auto-registered and can be used in YAML configs by their `probe_id`.

---

## GitHub Actions Integration

Add to `.github/workflows/promptcanary.yml`:

```yaml
name: PromptCanary Drift Check
on:
  schedule:
    - cron: "0 9 * * 1"    # Every Monday
  workflow_dispatch:

jobs:
  canary:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install promptcanary
      - name: Run and compare
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          promptcanary run --provider openai/gpt-5.4 --output-json results.json
          promptcanary compare --current results.json --baseline baselines/latest.json --fail-on-drift
```

On drift, PromptCanary will:
- Print a detailed terminal report
- Exit with code 1 (fails the job)
- Optionally post a PR comment or open a GitHub issue (see `.github/workflows/promptcanary.yml`)

---

## Supported Providers

PromptCanary works with any provider supported by [LiteLLM](https://docs.litellm.ai/docs/providers) — cloud or local, paid or free.

| Provider | Example model string | API key env var | Cost |
|----------|----------------------|------------------|------|
| OpenAI | `openai/gpt-5.5` (flagship), `openai/gpt-5.4` (balanced), `openai/gpt-5.4-mini` (fast) | `OPENAI_API_KEY` | Paid |
| Anthropic | `anthropic/claude-opus-4-8` (flagship), `anthropic/claude-sonnet-4-6` (balanced) | `ANTHROPIC_API_KEY` | Paid |
| Google Gemini | `gemini/gemini-3.1-pro` (flagship), `gemini/gemini-3.5-flash` (balanced), `gemini/gemini-3.1-flash-lite` (fast) | `GEMINI_API_KEY` | Paid |
| xAI | `xai/grok-4` | `XAI_API_KEY` | Paid |
| **Ollama (local, free)** | `ollama/qwen3.6:27b`, `ollama/deepseek-r1:14b`, `ollama/gpt-oss:20b`, `ollama/llama3.3:8b` | *(none)* | **Free** |
| vLLM (self-hosted) | `hosted_vllm/<org>/<model>` | *(none)* | Free (self-hosted compute) |

> Model availability changes quickly. Run `litellm --test` or check [LiteLLM's provider docs](https://docs.litellm.ai/docs/providers) for the latest model strings before relying on any example here.

```python
# Cloud providers
LiteLLMProvider("openai/gpt-5.4")
LiteLLMProvider("anthropic/claude-sonnet-4-6")
LiteLLMProvider("gemini/gemini-3.5-flash")
LiteLLMProvider("xai/grok-4")

# Local models — zero cost, full privacy, no API key required
LiteLLMProvider("ollama/qwen3.6:27b")        # strong general-purpose, Apache 2.0
LiteLLMProvider("ollama/deepseek-r1:14b")    # reasoning-focused, MIT licensed
LiteLLMProvider("ollama/gpt-oss:20b")        # OpenAI's open-weight release
LiteLLMProvider("hosted_vllm/meta-llama/Llama-3.3-8B-Instruct")
```

### Why test local models too?

Local, open-weight models (via Ollama or vLLM) make excellent **zero-cost canaries**:
running them hourly costs nothing and catches infrastructure-level regressions
(prompt template bugs, parser issues) independent of any vendor's API changes.
See [`notebooks/ci_integration.ipynb`](notebooks/ci_integration.ipynb) for a
cost-aware multi-provider scheduling strategy that mixes free local models with
periodic paid-provider checks.

---

## Report Formats

Every run produces multiple output formats:

```bash
promptcanary run --provider openai/gpt-5.4 \
  --output-json results.json \
  --output-md report.md \
  --output-html report.html
```

- **Terminal** — colour-coded table with scores and details
- **Markdown** — GitHub-flavoured, ideal for PR comments
- **HTML** — self-contained dark-theme interactive report
- **JSON** — machine-readable for downstream automation

---

### Trend Visualization

Track score history, per-probe heatmaps, and drift timelines across multiple runs:

```python
from promptcanary.storage.file import FileBaselineStore
from promptcanary.utils.visualization import plot_score_history, plot_probe_heatmap

store = FileBaselineStore("baselines/")
snapshots = [store.load_from_path(p) for p in sorted(Path("baselines").glob("*.json"))]

# Works everywhere — zero dependencies, ASCII sparkline in any terminal
plot_score_history(snapshots, mode="ascii")

# Interactive HTML — requires: pip install promptcanary[viz]
plot_score_history(snapshots, output_path="trend.html")
plot_probe_heatmap(snapshots, output_path="heatmap.html")
```

See [`notebooks/analyzing_drift_trends.ipynb`](notebooks/analyzing_drift_trends.ipynb)
for a full walkthrough of identifying which probe regresses first during gradual drift.

## Architecture

```
promptcanary/
├── core/
│   ├── models.py       # Pydantic v2 domain types
│   ├── suite.py        # CanarySuite orchestrator
│   ├── comparator.py   # Drift comparison engine
│   ├── reporter.py     # Terminal/MD/HTML/JSON output
│   └── probes/         # 19 built-in probes + registry
├── providers/
│   ├── base.py         # BaseLLMProvider ABC
│   └── litellm.py      # LiteLLM adapter
├── storage/
│   └── file.py         # Local JSON baseline storage
├── utils/
│   └── visualization.py # Trend charts (ASCII + optional Plotly)
└── cli.py              # Typer CLI
```

**Key design choices:**
- All models are Pydantic v2 with full type hints and JSON serialisation
- Probes are stateless, auto-registered, and composable
- No network calls in the core — only in provider adapters
- `BaselineStore` and `BaseLLMProvider` are ABCs enabling custom backends

---

## Contributing

We welcome contributions of all kinds! The highest-value contributions are:

- **New probes** — especially for specific domains (tool use, agents, legal, medical)
- **Community canary suites** — `canary.yaml` examples for specific use cases
- **Storage backends** — S3, GCS, database adapters
- **Bug reports with reproduction cases**

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, conventions, and the PR checklist.

---

## Roadmap

**Done in v0.1.x:**
- [x] `ToolCallProbe` family — function name + argument schema stability for agent workflows
- [x] Trend visualization — score history, probe heatmaps, drift timelines (ASCII + Plotly)
- [x] Property-based tests (Hypothesis) for comparator and scoring invariants
- [x] Full CLI test coverage

**Planned:**
- [ ] `suite.arun()` — async parallel execution
- [ ] Export connectors — Langfuse, Phoenix/Arize
- [ ] `SemanticSimilarityProbe` — embedding-based semantic drift
- [ ] S3 / GCS baseline storage backends
- [ ] Optional web dashboard

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built with ❤️ for AI engineers who care about production reliability.*
