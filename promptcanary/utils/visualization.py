"""
promptcanary.utils.visualization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Trend visualization utilities for PromptCanary.

Generates score-over-time charts, per-probe heatmaps, and regression timelines
from a sequence of baseline snapshots or run results. Works in three modes:

  1. **Notebook mode** — calls ``display()`` with rich HTML/Plotly figures.
  2. **File mode**     — saves standalone HTML files (no external deps at render).
  3. **ASCII mode**    — terminal sparklines when neither Plotly nor a notebook
                         is available (zero extra deps).

Optional dependency: ``pip install promptcanary[viz]``  (adds plotly).
The module degrades gracefully — ASCII mode is always available.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from promptcanary.core.models import BaselineSnapshot, DriftReport


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def plot_score_history(
    snapshots: list[BaselineSnapshot],
    *,
    title: str = "PromptCanary — Score History",
    output_path: str | Path | None = None,
    mode: str = "auto",
) -> str | None:
    """Plot overall score over time from a list of baseline snapshots.

    Args:
        snapshots:    Ordered list of :class:`BaselineSnapshot` objects.
        title:        Chart title.
        output_path:  If set, save HTML to this path.
        mode:         ``"auto"`` (try plotly → ASCII), ``"plotly"``, or ``"ascii"``.

    Returns:
        For plotly mode: the HTML string.
        For ascii mode: the printed sparkline (also printed to stdout).
        None if display-only (notebook mode).

    Example::

        from promptcanary.storage.file import FileBaselineStore
        from promptcanary.utils.visualization import plot_score_history

        store = FileBaselineStore("baselines/")
        snaps = [store.load_from_path(p) for p in sorted(Path("baselines").glob("*.json"))]
        html = plot_score_history(snaps, output_path="trend.html")
    """
    if not snapshots:
        raise ValueError("At least one snapshot is required.")

    points = [
        {
            "ts": snap.created_at,
            "score": snap.run_result.overall_score,
            "pass_rate": snap.run_result.pass_rate,
            "model": snap.provider.model_id,
            "suite": snap.suite_name,
            "snap_id": snap.snapshot_id[:8],
        }
        for snap in sorted(snapshots, key=lambda s: s.created_at)
    ]

    if mode == "ascii" or (mode == "auto" and not _plotly_available()):
        return _ascii_score_history(points, title)

    return _plotly_score_history(points, title=title, output_path=output_path)


def plot_probe_heatmap(
    snapshots: list[BaselineSnapshot],
    *,
    title: str = "PromptCanary — Probe Score Heatmap",
    output_path: str | Path | None = None,
    mode: str = "auto",
) -> str | None:
    """Plot a probe x time heatmap showing score drift at probe granularity.

    Args:
        snapshots:    Ordered list of :class:`BaselineSnapshot` objects.
        title:        Chart title.
        output_path:  If set, save HTML to this path.
        mode:         ``"auto"``, ``"plotly"``, or ``"ascii"``.

    Returns:
        HTML string or ASCII table.
    """
    if not snapshots:
        raise ValueError("At least one snapshot is required.")

    sorted_snaps = sorted(snapshots, key=lambda s: s.created_at)

    # Build matrix: probe_name → [scores over time]
    probe_names: list[str] = []
    seen: set[str] = set()
    for snap in sorted_snaps:
        for pr in snap.run_result.probe_results:
            if pr.probe_name not in seen:
                probe_names.append(pr.probe_name)
                seen.add(pr.probe_name)

    timestamps = [s.created_at.strftime("%Y-%m-%d") for s in sorted_snaps]
    matrix: dict[str, list[float | None]] = {pn: [] for pn in probe_names}

    for snap in sorted_snaps:
        snap_scores: dict[str, float] = {
            pr.probe_name: pr.score for pr in snap.run_result.probe_results
        }
        for pn in probe_names:
            matrix[pn].append(snap_scores.get(pn))

    if mode == "ascii" or (mode == "auto" and not _plotly_available()):
        return _ascii_heatmap(probe_names, timestamps, matrix)

    return _plotly_heatmap(probe_names, timestamps, matrix, title=title, output_path=output_path)


def plot_drift_timeline(
    drift_reports: list[DriftReport],
    *,
    title: str = "PromptCanary — Drift Timeline",
    output_path: str | Path | None = None,
    mode: str = "auto",
) -> str | None:
    """Plot a regression-count timeline from a series of DriftReport objects.

    Args:
        drift_reports:  Ordered list of :class:`DriftReport` objects.
        title:          Chart title.
        output_path:    If set, save HTML to this path.
        mode:           ``"auto"``, ``"plotly"``, or ``"ascii"``.
    """
    if not drift_reports:
        raise ValueError("At least one drift report is required.")

    from promptcanary.core.models import DriftSeverity

    _SEVERITY_RANK = {  # noqa: N806  (module-level constant semantics inside function)
        DriftSeverity.NONE: 0,
        DriftSeverity.LOW: 1,
        DriftSeverity.MEDIUM: 2,
        DriftSeverity.HIGH: 3,
        DriftSeverity.CRITICAL: 4,
    }

    points = [
        {
            "ts": dr.generated_at,
            "regressions": len(dr.regressions),
            "improvements": len(dr.improvements),
            "severity": dr.severity.value,
            "severity_rank": _SEVERITY_RANK[dr.severity],
            "score_delta": dr.overall_score_delta,
            "run_id": dr.current_run_id[:8],
        }
        for dr in sorted(drift_reports, key=lambda d: d.generated_at)
    ]

    if mode == "ascii" or (mode == "auto" and not _plotly_available()):
        return _ascii_drift_timeline(points, title)

    return _plotly_drift_timeline(points, title=title, output_path=output_path)


# ─────────────────────────────────────────────────────────────────────────────
# ASCII fallback renderers (zero dependencies)
# ─────────────────────────────────────────────────────────────────────────────

_SPARKLINE_CHARS = " ▁▂▃▄▅▆▇█"


def _sparkline(values: list[float], width: int = 40) -> str:
    """Render a list of 0-1 floats as a terminal sparkline."""
    if not values:
        return ""
    normalised = [max(0.0, min(1.0, v)) for v in values]
    return "".join(_SPARKLINE_CHARS[int(v * (len(_SPARKLINE_CHARS) - 1))] for v in normalised)


def _score_bar(score: float, width: int = 20) -> str:
    filled = int(score * width)
    colour = "🟢" if score >= 0.9 else "🟡" if score >= 0.7 else "🔴"
    return f"{colour} {'█' * filled}{'░' * (width - filled)} {score:.0%}"


def _ascii_score_history(points: list[dict[str, Any]], title: str) -> str:
    lines = [f"\n{title}", "─" * 60]
    scores = [p["score"] for p in points]
    lines.append(f"Sparkline: {_sparkline(scores)}")
    lines.append("")
    lines.append(f"{'Timestamp':<22} {'Model':<30} {'Score':>8} {'Pass':>6}")
    lines.append("─" * 70)
    for p in points:
        ts = p["ts"].strftime("%Y-%m-%d %H:%M") if isinstance(p["ts"], datetime) else str(p["ts"])
        lines.append(f"{ts:<22} {p['model'][:28]:<30} {p['score']:>7.1%} {p['pass_rate']:>5.1%}")
    result = "\n".join(lines) + "\n"
    print(result)
    return result


def _ascii_heatmap(
    probe_names: list[str],
    timestamps: list[str],
    matrix: dict[str, list[float | None]],
) -> str:
    lines = ["\nProbe Score Heatmap", "─" * 60]
    header = f"{'Probe':<35}" + "".join(f" {t[-5:]:>7}" for t in timestamps)
    lines.append(header)
    lines.append("─" * (35 + 8 * len(timestamps)))
    for pn in probe_names:
        row_scores = matrix[pn]
        cells = []
        for s in row_scores:
            if s is None:
                cells.append("   N/A")
            else:
                colour = "🟢" if s >= 0.9 else "🟡" if s >= 0.7 else "🔴"
                cells.append(f" {colour}{s:.2f}")
        lines.append(f"{pn[:33]:<35}" + "".join(cells))
    result = "\n".join(lines) + "\n"
    print(result)
    return result


def _ascii_drift_timeline(points: list[dict[str, Any]], title: str) -> str:
    lines = [f"\n{title}", "─" * 60]
    lines.append(f"{'Timestamp':<22} {'Severity':<10} {'Regressions':>12} {'Δ Score':>9}")
    lines.append("─" * 55)
    for p in points:
        ts = p["ts"].strftime("%Y-%m-%d %H:%M") if isinstance(p["ts"], datetime) else str(p["ts"])
        delta = f"{p['score_delta']:+.1%}"
        lines.append(f"{ts:<22} {p['severity']:<10} {p['regressions']:>12} {delta:>9}")
    result = "\n".join(lines) + "\n"
    print(result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Plotly renderers (optional dep)
# ─────────────────────────────────────────────────────────────────────────────


def _plotly_available() -> bool:
    try:
        import plotly  # noqa: F401

        return True
    except ImportError:
        return False


_HTML_WRAPPER = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PromptCanary — {title}</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
  <style>
    body {{ background: #0f172a; color: #f1f5f9; font-family: ui-monospace, monospace;
           margin: 0; padding: 2rem; }}
    h1 {{ color: #60a5fa; font-size: 1.4rem; margin-bottom: 1.5rem; }}
    .chart-wrap {{ background: #1e293b; border-radius: 8px; padding: 1rem;
                   margin-bottom: 1.5rem; }}
    footer {{ color: #475569; font-size: 0.75rem; margin-top: 2rem; }}
    a {{ color: #60a5fa; }}
  </style>
</head>
<body>
  <h1>🐦 PromptCanary — {title}</h1>
  <div class="chart-wrap" id="chart"></div>
  <footer>Generated by <a href="https://github.com/Mattral/PromptCanary">PromptCanary</a></footer>
  <script>
    {plotly_json}
  </script>
</body>
</html>"""


def _plotly_score_history(
    points: list[dict[str, Any]],
    *,
    title: str,
    output_path: str | Path | None,
) -> str:
    import plotly.graph_objects as go

    timestamps = [p["ts"] for p in points]
    scores = [round(p["score"] * 100, 1) for p in points]
    pass_rates = [round(p["pass_rate"] * 100, 1) for p in points]
    hover = [
        f"<b>{p['suite']}</b><br>Model: {p['model']}<br>Score: {p['score']:.1%}<br>Pass: {p['pass_rate']:.1%}<br>ID: {p['snap_id']}"
        for p in points
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=scores,
            name="Overall Score (%)",
            mode="lines+markers",
            line={"color": "#60a5fa", "width": 2},
            marker={"size": 8, "color": "#60a5fa"},
            hovertext=hover,
            hoverinfo="text",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=pass_rates,
            name="Pass Rate (%)",
            mode="lines+markers",
            line={"color": "#34d399", "width": 2, "dash": "dot"},
            marker={"size": 6, "color": "#34d399"},
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#1e293b",
        plot_bgcolor="#0f172a",
        font={"family": "ui-monospace, monospace", "color": "#f1f5f9"},
        yaxis={"range": [0, 105], "title": "Score (%)"},
        xaxis={"title": "Date"},
        legend={"bgcolor": "#1e293b"},
        margin={"l": 50, "r": 20, "t": 30, "b": 50},
    )

    return _emit(fig, title, output_path)


def _plotly_heatmap(
    probe_names: list[str],
    timestamps: list[str],
    matrix: dict[str, list[float | None]],
    *,
    title: str,
    output_path: str | Path | None,
) -> str:
    import plotly.graph_objects as go

    z = [[v if v is not None else -1 for v in matrix[pn]] for pn in probe_names]
    text = [[f"{v:.2f}" if v is not None else "N/A" for v in matrix[pn]] for pn in probe_names]

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=timestamps,
            y=probe_names,
            text=text,
            texttemplate="%{text}",
            colorscale=[
                [0.0, "#ef4444"],
                [0.5, "#eab308"],
                [0.8, "#22c55e"],
                [1.0, "#16a34a"],
            ],
            zmin=0,
            zmax=1,
            colorbar={"title": "Score", "tickformat": ".0%"},
            hoverongaps=False,
        )
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#1e293b",
        plot_bgcolor="#0f172a",
        font={"family": "ui-monospace, monospace", "color": "#f1f5f9"},
        xaxis={"title": "Date"},
        yaxis={"title": "Probe", "autorange": "reversed"},
        margin={"l": 200, "r": 20, "t": 30, "b": 80},
    )

    return _emit(fig, title, output_path)


def _plotly_drift_timeline(
    points: list[dict[str, Any]],
    *,
    title: str,
    output_path: str | Path | None,
) -> str:
    import plotly.graph_objects as go

    _SEVERITY_COLOURS = {  # noqa: N806  (constant semantics inside function)
        "none": "#22c55e",
        "low": "#eab308",
        "medium": "#f97316",
        "high": "#ef4444",
        "critical": "#7f1d1d",
    }

    timestamps = [p["ts"] for p in points]
    regressions = [p["regressions"] for p in points]
    colours = [_SEVERITY_COLOURS.get(p["severity"], "#94a3b8") for p in points]
    hover = [
        f"<b>{p['severity'].upper()}</b><br>Regressions: {p['regressions']}<br>"
        f"Improvements: {p['improvements']}<br>Δ Score: {p['score_delta']:+.1%}"
        for p in points
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=timestamps,
            y=regressions,
            marker_color=colours,
            hovertext=hover,
            hoverinfo="text",
            name="Regressions",
        )
    )
    fig.add_hline(y=0, line_color="#475569", line_width=1)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#1e293b",
        plot_bgcolor="#0f172a",
        font={"family": "ui-monospace, monospace", "color": "#f1f5f9"},
        yaxis={"title": "# Regressions", "rangemode": "tozero"},
        xaxis={"title": "Date"},
        margin={"l": 50, "r": 20, "t": 30, "b": 50},
        showlegend=False,
    )

    return _emit(fig, title, output_path)


def _emit(fig: Any, title: str, output_path: str | Path | None) -> str:
    """Render a Plotly figure to HTML and optionally save it."""
    import plotly.io as pio

    div = pio.to_html(fig, full_html=False, include_plotlyjs=False)
    html = _HTML_WRAPPER.format(
        title=title,
        plotly_json=f"Plotly.newPlot('chart', {pio.to_json(fig, validate=False)});",
    )

    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")

    # Notebook detection
    try:
        from IPython.display import HTML, display

        display(HTML(div))
        return html
    except ImportError:
        pass

    return html
