# Baseline Promotion

Drift detection is only useful if your team has a clear process for what
happens *after* drift is detected. There are exactly two outcomes:

1. The change is **acceptable** (an intentional model upgrade) → promote
   the new run to become the baseline.
2. The change is **unacceptable** (an unexpected regression) → pin the
   previous model version and investigate.

## The Workflow

```bash
# 1. Drift is detected (happens automatically in CI)
promptcanary compare --provider openai/gpt-5.5 --fail-on-drift
# → exit code 1

# 2. Review the drift report manually
promptcanary compare --provider openai/gpt-5.5 --output-html drift.html
open drift.html

# 3a. ACCEPTABLE — promote the new baseline
promptcanary run --provider openai/gpt-5.5 --save-baseline --baseline-dir baselines/
git add baselines/
git commit -m "chore: promote gpt-5.5 baseline after model upgrade"
git tag baseline/gpt-5.5-2026-07-01

# 3b. UNACCEPTABLE — pin the previous version, open an incident
# Update your provider call to a versioned string:
#   LiteLLMProvider("openai/gpt-5.4")  # pinned until the regression is resolved
```

## Why Commit Baselines to Git

Baselines are plain JSON files. Committing them gives you:

- **Version history** — `git log baselines/my-suite__openai-gpt-5.4__*.json`
  shows every promotion, with commit messages explaining why.
- **Diffability** — `git diff` on a baseline file shows exactly which
  probe scores changed between promotions.
- **Auditability** — code review on baseline promotion PRs creates a
  natural approval gate before accepting a behavioral change.
- **Rollback** — `git revert` a bad baseline promotion just like any
  other code change.

## Recommended Git Convention

```
baselines/
├── my-suite__openai-gpt-5.4__20260615T090000_abc12345.json
├── my-suite__openai-gpt-5.5__20260701T090000_def67890.json   ← promoted
└── my-suite__gemini-3.5-flash__20260620T090000_ghi13579.json
```

Keep old baseline files in git history rather than deleting them — they
serve as a record of what "good" looked like at each point in time, useful
for retrospective analysis if a regression is discovered later.

## Requiring Review for Baseline Changes

Add a `CODEOWNERS` entry to require review on baseline promotions:

```
# .github/CODEOWNERS
/baselines/  @your-team/ml-platform
```

This ensures a human reviews every behavioral baseline change before it's
accepted — treating prompt/model behavior with the same rigor as code.
