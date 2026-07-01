# Quick Start

This guide gets you from zero to a working canary suite in under 10 minutes.

## 1. Scaffold a Suite

```bash
promptcanary init my-suite
cd my-suite
```

This creates:

```
my-suite/
├── canary.yaml       ← Your prompts and probes (edit this)
├── baselines/         ← Saved baselines go here
├── .env.example        ← Copy to .env and add your API key
└── README.md
```

## 2. Review the Generated Suite

`canary.yaml` ships with a working example: a geography fact, JSON formatting,
a refusal check, and a direct-answer check. Open it and adjust the prompts to
reflect patterns from **your** production system — the more representative
the prompts, the more useful the canary.

```yaml
name: my-suite
probes:
  - type: json_validity
  - type: keyword_presence
    required_keywords: ["Paris"]
  - type: refusal
    expect_refusal: false
  - type: direct_answer
    expect_direct: true
prompts:
  - text: "What is the capital of France? Reply in one sentence."
    expected_keywords: ["Paris"]
  - text: "Return a JSON object with keys: name (string) and age (integer)."
```

## 3. Run Your First Canary

=== "OpenAI"

    ```bash
    export OPENAI_API_KEY=sk-...
    promptcanary run --provider openai/gpt-5.4 --save-baseline
    ```

=== "Anthropic"

    ```bash
    export ANTHROPIC_API_KEY=sk-ant-...
    promptcanary run --provider anthropic/claude-sonnet-4-6 --save-baseline
    ```

=== "Google Gemini"

    ```bash
    export GEMINI_API_KEY=...
    promptcanary run --provider gemini/gemini-3.5-flash --save-baseline
    ```

=== "Ollama (free, local)"

    ```bash
    ollama pull qwen3.6:27b
    promptcanary run --provider ollama/qwen3.6:27b --save-baseline
    ```

You'll see a Rich terminal report:

```
┌─ PromptCanary Run Report ────────────────────────────────────────────────────┐
│ my-suite  ·  Score: 100.0%  ·  Pass rate: 100.0%  ·  openai/gpt-5.4           │
└────────────────────────────────────────────────────────────────────────────┘
✅ All probes passed.
✅ Baseline saved: baselines/my-suite__openai-gpt-5.4__...json
```

## 4. Detect Drift Later

Run the same command again — tomorrow, next week, or in CI:

```bash
promptcanary compare --provider openai/gpt-5.4 --fail-on-drift
```

If nothing changed, you'll see a clean pass. If the provider's behavior
shifted, you'll see a detailed regression report and the command exits
with code `1` — perfect for CI gating.

## 5. Add Reports

```bash
promptcanary run --provider openai/gpt-5.4 \
  --output-json results.json \
  --output-md report.md \
  --output-html report.html
```

## Next Steps

- [Your First Canary Suite](first-suite.md) — a deeper walkthrough of writing good prompts and probes
- [Probe Reference](../probes/index.md) — all 19 built-in probes
- [GitHub Actions](../ci-cd/github-actions.md) — automate this on a schedule
- Try [`notebooks/quickstart.ipynb`](https://github.com/promptcanary/promptcanary/blob/main/notebooks/quickstart.ipynb) for an interactive walkthrough
