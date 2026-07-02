# Multi-Provider Matrix

Test the same canary suite across multiple providers simultaneously using
a GitHub Actions matrix — and schedule each tier by cost.

## Matrix Workflow

```yaml
name: PromptCanary Multi-Provider Drift Check
on:
  schedule:
    - cron: "0 9 * * 1"

jobs:
  canary:
    name: Canary (${{ matrix.provider }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - provider: openai/gpt-5.5
            baseline: baselines/openai-gpt-5.5-latest.json
          - provider: anthropic/claude-sonnet-4-6
            baseline: baselines/claude-sonnet-4.6-latest.json
          - provider: gemini/gemini-3.5-flash
            baseline: baselines/gemini-3.5-flash-latest.json
          - provider: ollama/qwen3.6:27b
            baseline: baselines/qwen3.6-27b-latest.json

    steps:
      - uses: actions/checkout@v4

      - name: Set up Ollama (local models only)
        if: startsWith(matrix.provider, 'ollama/')
        run: |
          curl -fsSL https://ollama.ai/install.sh | sh
          ollama pull ${{ matrix.provider }} | sed 's|ollama/||'

      - run: pip install promptcanary

      - name: Run and compare
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          promptcanary run --provider "${{ matrix.provider }}" --output-json results.json
          promptcanary compare --baseline "${{ matrix.baseline }}" --current results.json --fail-on-drift
```

`fail-fast: false` ensures one provider's drift doesn't cancel checks for
the others — each provider's result is independently meaningful.

## Cost-Aware Scheduling

Different models warrant different check frequencies. A reasonable
strategy:

| Tier | Example | Schedule | Rationale |
|------|---------|----------|-----------|
| Free, local | `ollama/qwen3.6:27b` | Hourly | Zero cost — catches fast rollouts immediately |
| Cheap cloud | `openai/gpt-5.4-mini`, `gemini/gemini-3.1-flash-lite` | Every 4–6h | Low cost, frequent enough to narrow the detection window |
| Balanced | `gemini/gemini-3.5-flash`, `anthropic/claude-sonnet-4-6` | 2x/week | Moderate cost, broad coverage |
| Flagship | `openai/gpt-5.5`, `anthropic/claude-opus-4-8` | Weekly | Premium cost, lower drift frequency expected |

Use separate `cron` schedules per job (or per workflow file) rather than
running every provider on the same schedule — this keeps the most
expensive checks infrequent without sacrificing fast detection on the
cheap/free tiers.

## Interpreting Cross-Provider Results

If only **one** provider in the matrix regresses, the issue is
provider-specific drift — investigate that vendor's recent model changes.

If **all** providers regress simultaneously on the same prompts, suspect
your own harness: a `canary.yaml` edit, a probe configuration change, or
an infrastructure issue — not the model providers themselves.

See [`notebooks/ci_integration.ipynb`](https://github.com/Mattral/PromptCanary/blob/main/notebooks/ci_integration.ipynb)
for a runnable version of this scheduling strategy with a live provider
reference table.
