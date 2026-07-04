# Trend Visualization

Track score history, per-probe heatmaps, and drift timelines across
multiple runs using `promptcanary.utils.visualization`.

## Zero-Dependency ASCII Mode

Always available, no extra install required:

```python
from promptcanary.storage.file import FileBaselineStore
from promptcanary.utils.visualization import plot_score_history
from pathlib import Path

store = FileBaselineStore("baselines/")
snapshots = [store.load_from_path(p) for p in sorted(Path("baselines").glob("*.json"))]

plot_score_history(snapshots, mode="ascii")
```

```
Score History -- PromptCanary
------------------------------------------------------------
Sparkline: XXXXXXXX765321

Timestamp              Model                            Score   Pass
----------------------------------------------------------------
2026-06-23 09:00        openai/gpt-5.4                   100.0%  100.0%
2026-06-24 09:00        openai/gpt-5.4                    90.0%   90.0%
2026-06-25 09:00        openai/gpt-5.4                    51.0%   60.0%
```

## Interactive HTML Mode (Plotly)

```bash
pip install "promptcanary[viz]"
```

```python
plot_score_history(snapshots, output_path="trend.html")
plot_probe_heatmap(snapshots, output_path="heatmap.html")
```

`mode="auto"` (the default) tries Plotly first and falls back to ASCII
automatically if the `viz` extra isn't installed -- no functionality is
ever lost, just the interactive rendering.

## Three Chart Types

### Score History

`plot_score_history(snapshots)` -- overall score and pass rate over time.
The fastest way to see whether drift is gradual (linear decline) or sudden
(a sharp drop, usually indicating a hard provider switch).

### Probe Heatmap

`plot_probe_heatmap(snapshots)` -- probe x time grid showing per-probe
score at every snapshot. Reveals *which* probe regresses first -- your most
sensitive "canary in the coal mine" for this suite.

### Drift Timeline

`plot_drift_timeline(drift_reports)` -- regression count and severity over
a series of `compare()` calls against a fixed baseline.

```python
from promptcanary import compare
from promptcanary.utils.visualization import plot_drift_timeline

baseline = snapshots[0]
reports = [compare(baseline, snap.run_result) for snap in snapshots[1:]]
plot_drift_timeline(reports, output_path="drift_timeline.html")
```

## Full Walkthrough

See [`notebooks/analyzing_drift_trends.ipynb`](https://github.com/Mattral/PromptCanary/blob/main/notebooks/analyzing_drift_trends.ipynb)
for a complete, runnable example that simulates seven days of gradual
provider drift and identifies the first-failing probe at each stage.
