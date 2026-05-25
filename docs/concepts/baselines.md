# Baselines & Comparison

A baseline is a saved, known-good `CanaryRunResult` that future runs are
compared against. PromptCanary's drift detection is entirely built on
comparing a current run to a stored baseline.

## Saving a Baseline

=== "CLI"

    ```bash
    promptcanary run --provider openai/gpt-5.4 --save-baseline
    ```

=== "Python SDK"

    ```python
    from promptcanary.storage.file import FileBaselineStore

    store = FileBaselineStore("baselines/")
    result = suite.run(provider)
    snapshot = store.save(result, note="Pre-release baseline v1")
    ```

## Storage Format

Baselines are stored as plain JSON files in a directory, one file per
snapshot, named:

```
{suite_name}__{model_slug}__{ISO_timestamp}_{snapshot_id_prefix}.json
```

This makes baselines:

- **git-friendly** — commit them alongside your `canary.yaml` for free version history
- **diffable** — `git diff` on a baseline file shows exactly what changed
- **portable** — no database or cloud dependency required

## FileBaselineStore API

```python
from promptcanary.storage.file import FileBaselineStore

store = FileBaselineStore("baselines/")

# Save
snapshot = store.save(run_result, note="optional note")

# Load by ID
snapshot = store.load(snapshot_id)

# Load the most recent baseline for a suite + model combo
snapshot = store.load_latest(suite_name="my-suite", model_id="openai/gpt-5.4")

# Load directly from a known file path
snapshot = store.load_from_path("baselines/my-suite__openai-gpt-5.4__....json")

# List all baselines with lightweight metadata
for item in store.list_baselines():
    print(item["snapshot_id"], item["suite_name"], item["created_at"])

# Delete
store.delete(snapshot_id)
```

## Comparing

```python
from promptcanary import compare

drift_report = compare(snapshot, new_result)
```

`compare()` matches `ProbeResult`s between baseline and current run by
`(probe_id, prompt_id)` pairs — order-independent. Probes or prompts present
in only one side are treated as missing on the other (scored as a failure),
so removing a prompt or probe between runs is itself detectable as drift.

### Thresholds

```python
drift_report = compare(
    snapshot,
    new_result,
    regression_threshold=0.05,    # min score drop to count as regression
    improvement_threshold=0.05,   # min score gain to count as improvement
)
```

## Baseline Promotion Workflow

When a provider intentionally changes behavior (e.g. you upgrade to a new
model version on purpose), promote the new run as the accepted baseline:

```bash
# 1. Review the drift
promptcanary compare --provider openai/gpt-5.5 --output-html drift.html

# 2. If the change is acceptable, save a new baseline
promptcanary run --provider openai/gpt-5.5 --save-baseline

# 3. Commit the new baseline file to git
git add baselines/
git commit -m "chore: promote gpt-5.5 baseline after model upgrade"
```

See [Baseline Promotion](../ci-cd/baseline-promotion.md) for the full CI workflow.
