# Drift Reports

`DriftReport` is the structured output of `compare(baseline, current_run)`.
It captures every change at the `(probe, prompt)` granularity, plus derived
severity and summary fields for quick consumption.

## Structure

```python
drift_report.has_drift          # bool — True if any regressions were found
drift_report.severity           # DriftSeverity: NONE | LOW | MEDIUM | HIGH | CRITICAL
drift_report.summary            # one-sentence human-readable summary
drift_report.regressions        # list[ProbeComparison] — probes that got worse
drift_report.improvements       # list[ProbeComparison] — probes that got better
drift_report.stable             # list[ProbeComparison] — unchanged probes
drift_report.overall_baseline_score
drift_report.overall_current_score
drift_report.overall_score_delta
```

## ProbeComparison

Each entry in `comparisons`, `regressions`, `improvements`, and `stable`
is a `ProbeComparison`:

| Field | Description |
|-------|--------------|
| `probe_id`, `probe_name`, `category`, `prompt_id` | Identifies which probe/prompt pair this is. |
| `baseline_score`, `current_score`, `score_delta` | The numbers. |
| `baseline_passed`, `current_passed` | Pass/fail on each side. |
| `regression` | `True` if this is a meaningful regression. |
| `improvement` | `True` if this is a meaningful improvement. |
| `baseline_details`, `current_details` | The `details` string from each `ProbeResult`. |

## Severity Heuristic

Severity is derived from regression rate and worst-case delta:

| Severity | Trigger |
|----------|---------|
| `NONE` | No regressions detected. |
| `LOW` | Regression rate < 15% and worst delta < 0.2. |
| `MEDIUM` | Regression rate ≥ 15% or worst delta ≥ 0.2. |
| `HIGH` | Regression rate ≥ 30% or worst delta ≥ 0.4. |
| `CRITICAL` | Regression rate ≥ 50% or worst delta ≥ 0.6. |

This heuristic is intentionally simple and transparent — see
[`promptcanary/core/models.py`](https://github.com/promptcanary/promptcanary/blob/main/promptcanary/core/models.py)
for the exact implementation, and the [Decision Log](../decision-log.md)
for the rationale.

## Generating Reports

```python
from promptcanary.core.reporter import DriftReporter

reporter = DriftReporter(drift_report)

reporter.print_terminal()                  # Rich colour-coded terminal output
reporter.to_markdown("drift_report.md")     # GitHub-flavoured Markdown
reporter.to_html("drift_report.html")       # Self-contained dark-theme HTML
reporter.to_json("drift_report.json")       # Full structured JSON
```

## CI Gating

```bash
promptcanary compare --provider openai/gpt-5.4 --fail-on-drift
```

Exits with code `1` if `drift_report.has_drift` is `True` — wire this
directly into a CI pipeline to block deployment on detected regressions.
