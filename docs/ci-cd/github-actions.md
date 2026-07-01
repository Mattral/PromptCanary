# GitHub Actions

The most common PromptCanary deployment: a scheduled weekly check that
opens a GitHub issue or posts a PR comment when drift is detected.

## Minimal Setup

Add to `.github/workflows/promptcanary.yml`:

```yaml
name: PromptCanary Drift Check
on:
  schedule:
    - cron: "0 9 * * 1"    # Every Monday 9am UTC
  workflow_dispatch:

jobs:
  canary:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install promptcanary

      - name: Run and compare
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          promptcanary run --provider openai/gpt-5.4 --output-json results.json
          promptcanary compare --current results.json --baseline baselines/latest.json --fail-on-drift
```

## Full-Featured Workflow

The repository ships a production-ready workflow at
[`.github/workflows/promptcanary.yml`](https://github.com/promptcanary/promptcanary/blob/main/.github/workflows/promptcanary.yml)
with:

- Scheduled weekly run + manual `workflow_dispatch` trigger with a
  configurable provider input
- PR-triggered runs on changes to `canary.yaml` or `baselines/`
- Automatic baseline creation on first run
- Markdown + HTML report artifact upload (30-day retention)
- PR comment with the drift report
- Automatic GitHub issue creation on scheduled-run drift detection,
  labeled `promptcanary`, `drift-detected`, `llm-ops`

Copy it directly into your repository and adjust the `provider` default
and secrets as needed.

## Required Secrets

| Secret | Required for |
|--------|---------------|
| `OPENAI_API_KEY` | OpenAI provider checks |
| `ANTHROPIC_API_KEY` | Anthropic provider checks |
| `GEMINI_API_KEY` | Google Gemini provider checks |

Local Ollama checks require no secrets — see
[Local Models via Ollama](../providers/ollama.md) for the Ollama CI setup.

## Exit Codes

| Command | Exit code 1 when |
|---------|-------------------|
| `promptcanary run --fail-on-failure` | Any probe fails in the run itself |
| `promptcanary compare --fail-on-drift` | Drift is detected versus baseline |

Both flags are designed for direct use as CI gates — no extra parsing of
output required.

## Next Steps

- [Multi-Provider Matrix](multi-provider.md) — testing several providers in parallel
- [Baseline Promotion](baseline-promotion.md) — handling intentional model upgrades
