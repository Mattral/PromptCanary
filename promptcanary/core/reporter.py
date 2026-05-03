"""
promptcanary.core.reporter
~~~~~~~~~~~~~~~~~~~~~~~~~~

Report generation for CanaryRunResult and DriftReport.

Supported formats:
  - Terminal (Rich):  Beautiful colour-coded table + summary, printed in-place.
  - Markdown:         GitHub-flavoured markdown, ideal for PR comments.
  - HTML:             Self-contained interactive HTML file.
  - JSON:             Machine-readable, for downstream automation.

Usage::

    from promptcanary.core.reporter import Reporter

    # After a run:
    reporter = Reporter(run_result)
    reporter.print_terminal()
    reporter.to_markdown("report.md")
    reporter.to_html("report.html")

    # After a comparison:
    drift_reporter = DriftReporter(drift_report)
    drift_reporter.print_terminal()
    drift_reporter.to_markdown("drift_report.md")
"""

from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from promptcanary.core.comparator import score_to_emoji
from promptcanary.core.models import (
    CanaryRunResult,
    DriftReport,
    DriftSeverity,
    ProbeCategory,
)


# ─────────────────────────────────────────────────────────────────────────────
# Colour helpers
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORY_COLOURS: dict[ProbeCategory, str] = {
    ProbeCategory.FORMAT: "cyan",
    ProbeCategory.REASONING: "magenta",
    ProbeCategory.SAFETY: "yellow",
    ProbeCategory.FACTUAL: "blue",
    ProbeCategory.TOOL_USE: "green",
    ProbeCategory.CUSTOM: "white",
}

_SEVERITY_COLOURS: dict[DriftSeverity, str] = {
    DriftSeverity.NONE: "green",
    DriftSeverity.LOW: "yellow",
    DriftSeverity.MEDIUM: "orange3",
    DriftSeverity.HIGH: "red",
    DriftSeverity.CRITICAL: "bold red",
}


def _score_colour(score: float) -> str:
    if score >= 0.95:
        return "green"
    if score >= 0.80:
        return "yellow"
    if score >= 0.60:
        return "orange3"
    return "red"


def _bool_cell(passed: bool) -> Text:
    return Text("✓ PASS", style="green bold") if passed else Text("✗ FAIL", style="red bold")


# ─────────────────────────────────────────────────────────────────────────────
# Run Reporter
# ─────────────────────────────────────────────────────────────────────────────


class Reporter:
    """Generates reports for a single :class:`CanaryRunResult`."""

    def __init__(self, result: CanaryRunResult) -> None:
        self.result = result

    # ── Terminal ─────────────────────────────────────────────────────────────

    def print_terminal(self, console: Console | None = None) -> None:
        """Print a rich terminal report to stdout (or provided console)."""
        console = console or Console()
        r = self.result

        # Header
        score = r.overall_score
        score_colour = _score_colour(score)
        console.print()
        console.print(
            Panel(
                f"[bold]{r.suite_name}[/bold]  ·  "
                f"[{score_colour}]Score: {score:.1%}[/{score_colour}]  ·  "
                f"Pass rate: [{score_colour}]{r.pass_rate:.1%}[/{score_colour}]  ·  "
                f"Provider: [cyan]{r.provider.model_id}[/cyan]  ·  "
                f"Probes: {len(r.probe_results)}",
                title="[bold blue]PromptCanary Run Report[/bold blue]",
                border_style="blue",
            )
        )

        # Per-probe table
        table = Table(
            box=box.ROUNDED,
            show_header=True,
            header_style="bold blue",
            expand=True,
        )
        table.add_column("Probe", style="bold", no_wrap=True, min_width=24)
        table.add_column("Category", no_wrap=True)
        table.add_column("Prompt", no_wrap=True)
        table.add_column("Result", justify="center", no_wrap=True)
        table.add_column("Score", justify="right", no_wrap=True)
        table.add_column("Details", ratio=1)

        for pr in r.probe_results:
            cat_colour = _CATEGORY_COLOURS.get(pr.category, "white")
            score_text = Text(f"{pr.score:.2f}", style=_score_colour(pr.score))
            details_preview = pr.details[:120] + ("…" if len(pr.details) > 120 else "")
            table.add_row(
                pr.probe_name,
                Text(pr.category.value, style=cat_colour),
                pr.prompt_id,
                _bool_cell(pr.passed),
                score_text,
                details_preview,
            )

        console.print(table)

        # Summary footer
        status = (
            "[green bold]✅ All probes passed.[/green bold]"
            if r.pass_rate == 1.0
            else f"[red bold]⚠️  {len(r.failed_probes)} probe(s) failed.[/red bold]"
        )
        duration = f"{r.duration_ms:.0f}ms" if r.duration_ms else "N/A"
        console.print(
            Panel(
                f"{status}\n"
                f"Overall score: [{_score_colour(score)}]{score:.1%}[/{_score_colour(score)}]  ·  "
                f"Duration: {duration}  ·  "
                f"Run ID: [dim]{r.run_id}[/dim]",
                border_style=_score_colour(score),
            )
        )
        console.print()

    # ── Markdown ─────────────────────────────────────────────────────────────

    def to_markdown(self, path: str | Path | None = None) -> str:
        """Generate a Markdown report string. Optionally save to file."""
        r = self.result
        score = r.overall_score
        emoji = score_to_emoji(score)
        lines: list[str] = [
            f"# {emoji} PromptCanary Run Report — `{r.suite_name}`",
            "",
            f"> **Provider**: `{r.provider.model_id}`  |  "
            f"**Score**: `{score:.1%}`  |  "
            f"**Pass rate**: `{r.pass_rate:.1%}`  |  "
            f"**Run ID**: `{r.run_id}`",
            "",
            "## Summary",
            "",
        ]

        if r.pass_rate == 1.0:
            lines.append("✅ **All probes passed.** No drift detected in this run.")
        else:
            lines.append(
                f"⚠️ **{len(r.failed_probes)} probe(s) failed.** Review the table below."
            )

        # Stats table
        by_cat = r.by_category
        lines += [
            "",
            "### Stats by Category",
            "",
            "| Category | Probes Run | Passed | Score |",
            "|----------|-----------|--------|-------|",
        ]
        for cat, results in sorted(by_cat.items(), key=lambda x: x[0].value):
            passed = sum(1 for rr in results if rr.passed)
            avg_score = sum(rr.score for rr in results) / len(results)
            lines.append(
                f"| {cat.value} | {len(results)} | {passed} | {avg_score:.1%} |"
            )

        # Detailed table
        lines += [
            "",
            "## Probe Results",
            "",
            "| Probe | Category | Prompt ID | Result | Score | Details |",
            "|-------|----------|-----------|--------|-------|---------|",
        ]
        for pr in r.probe_results:
            result_badge = "✅ PASS" if pr.passed else "❌ FAIL"
            details_safe = pr.details.replace("|", "\\|")[:200]
            lines.append(
                f"| {pr.probe_name} | {pr.category.value} | `{pr.prompt_id}` "
                f"| {result_badge} | {pr.score:.2f} | {details_safe} |"
            )

        lines += [
            "",
            "---",
            f"*Generated by [PromptCanary](https://github.com/promptcanary/promptcanary). "
            f"Run started: {r.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}*",
        ]

        md = "\n".join(lines)
        if path:
            Path(path).write_text(md, encoding="utf-8")
        return md

    # ── JSON ─────────────────────────────────────────────────────────────────

    def to_json(self, path: str | Path | None = None) -> str:
        """Serialise the run result to JSON. Optionally save to file."""
        data = self.result.model_dump(mode="json")
        out = json.dumps(data, indent=2, default=str)
        if path:
            Path(path).write_text(out, encoding="utf-8")
        return out

    # ── HTML ─────────────────────────────────────────────────────────────────

    def to_html(self, path: str | Path | None = None) -> str:
        """Generate a self-contained HTML report. Optionally save to file."""
        html = _build_run_html(self.result)
        if path:
            Path(path).write_text(html, encoding="utf-8")
        return html


# ─────────────────────────────────────────────────────────────────────────────
# Drift Reporter
# ─────────────────────────────────────────────────────────────────────────────


class DriftReporter:
    """Generates reports for a :class:`DriftReport`."""

    def __init__(self, report: DriftReport) -> None:
        self.report = report

    # ── Terminal ─────────────────────────────────────────────────────────────

    def print_terminal(self, console: Console | None = None) -> None:
        """Print a rich terminal drift report."""
        console = console or Console()
        dr = self.report
        severity_colour = _SEVERITY_COLOURS.get(dr.severity, "white")

        console.print()
        console.print(
            Panel(
                f"[bold]{dr.suite_name}[/bold]  ·  "
                f"Provider: [cyan]{dr.provider.model_id}[/cyan]\n"
                f"Severity: [{severity_colour}]{dr.severity.value.upper()}[/{severity_colour}]  ·  "
                f"Regressions: [red]{len(dr.regressions)}[/red]  ·  "
                f"Improvements: [green]{len(dr.improvements)}[/green]  ·  "
                f"Stable: {len(dr.stable)}",
                title="[bold yellow]PromptCanary Drift Report[/bold yellow]",
                border_style=severity_colour,
            )
        )

        if dr.has_drift:
            console.print(f"\n[red bold]⚠️  DRIFT DETECTED — {dr.severity.value.upper()}[/red bold]")
            console.print(f"   Score: {dr.overall_baseline_score:.1%} → {dr.overall_current_score:.1%} "
                          f"({dr.overall_score_delta:+.1%})")

            # Regressions table
            table = Table(
                title="Regressions",
                box=box.ROUNDED,
                header_style="bold red",
                expand=True,
            )
            table.add_column("Probe", style="bold", min_width=22)
            table.add_column("Category")
            table.add_column("Prompt")
            table.add_column("Baseline", justify="right")
            table.add_column("Current", justify="right")
            table.add_column("Δ", justify="right")
            table.add_column("Details", ratio=1)

            for c in dr.regressions:
                delta_text = Text(f"{c.score_delta:+.2f}", style="red bold")
                table.add_row(
                    c.probe_name,
                    c.category.value,
                    c.prompt_id,
                    f"{c.baseline_score:.2f}",
                    Text(f"{c.current_score:.2f}", style="red"),
                    delta_text,
                    c.current_details[:120],
                )
            console.print(table)
        else:
            console.print(
                Panel(
                    "[green bold]✅ No drift detected. All probes are stable.[/green bold]",
                    border_style="green",
                )
            )

        if dr.improvements:
            console.print(f"\n[green]↑ {len(dr.improvements)} improvement(s) detected.[/green]")

        console.print(f"\n[dim]{dr.summary}[/dim]\n")

    # ── Markdown ─────────────────────────────────────────────────────────────

    def to_markdown(self, path: str | Path | None = None) -> str:
        """Generate GitHub-flavoured Markdown drift report."""
        dr = self.report
        sev_emoji = {
            DriftSeverity.NONE: "✅",
            DriftSeverity.LOW: "⚠️",
            DriftSeverity.MEDIUM: "🟠",
            DriftSeverity.HIGH: "🔴",
            DriftSeverity.CRITICAL: "🚨",
        }.get(dr.severity, "⚠️")

        lines = [
            f"# {sev_emoji} PromptCanary Drift Report — `{dr.suite_name}`",
            "",
            f"> **Provider**: `{dr.provider.model_id}`  |  "
            f"**Severity**: `{dr.severity.value.upper()}`  |  "
            f"**Baseline**: `{dr.baseline_snapshot_id[:8]}`  |  "
            f"**Current Run**: `{dr.current_run_id[:8]}`",
            "",
            "## Summary",
            "",
            dr.summary,
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Baseline score | {dr.overall_baseline_score:.1%} |",
            f"| Current score | {dr.overall_current_score:.1%} |",
            f"| Score delta | {dr.overall_score_delta:+.1%} |",
            f"| Regressions | {len(dr.regressions)} |",
            f"| Improvements | {len(dr.improvements)} |",
            f"| Stable probes | {len(dr.stable)} |",
            "",
        ]

        if dr.has_drift:
            lines += [
                "## Regressions",
                "",
                "| Probe | Category | Prompt | Baseline | Current | Δ | Details |",
                "|-------|----------|--------|----------|---------|---|---------|",
            ]
            for c in dr.regressions:
                details_safe = c.current_details.replace("|", "\\|")[:200]
                lines.append(
                    f"| {c.probe_name} | {c.category.value} | `{c.prompt_id}` "
                    f"| {c.baseline_score:.2f} | {c.current_score:.2f} "
                    f"| {c.score_delta:+.2f} | {details_safe} |"
                )
            lines.append("")

        if dr.improvements:
            lines += [
                "## Improvements",
                "",
                "| Probe | Category | Prompt | Baseline | Current | Δ |",
                "|-------|----------|--------|----------|---------|---|",
            ]
            for c in dr.improvements:
                lines.append(
                    f"| {c.probe_name} | {c.category.value} | `{c.prompt_id}` "
                    f"| {c.baseline_score:.2f} | {c.current_score:.2f} | {c.score_delta:+.2f} |"
                )
            lines.append("")

        lines += [
            "---",
            f"*Generated by [PromptCanary](https://github.com/promptcanary/promptcanary). "
            f"Report ID: `{dr.report_id}`*",
        ]

        md = "\n".join(lines)
        if path:
            Path(path).write_text(md, encoding="utf-8")
        return md

    # ── JSON ─────────────────────────────────────────────────────────────────

    def to_json(self, path: str | Path | None = None) -> str:
        data = self.report.model_dump(mode="json")
        out = json.dumps(data, indent=2, default=str)
        if path:
            Path(path).write_text(out, encoding="utf-8")
        return out

    # ── HTML ─────────────────────────────────────────────────────────────────

    def to_html(self, path: str | Path | None = None) -> str:
        html = _build_drift_html(self.report)
        if path:
            Path(path).write_text(html, encoding="utf-8")
        return html


# ─────────────────────────────────────────────────────────────────────────────
# HTML builders (self-contained)
# ─────────────────────────────────────────────────────────────────────────────

_HTML_STYLE = """
<style>
  :root {
    --green: #22c55e; --yellow: #eab308; --orange: #f97316;
    --red: #ef4444; --blue: #3b82f6; --bg: #0f172a;
    --surface: #1e293b; --surface2: #334155; --text: #f1f5f9;
    --text-muted: #94a3b8; --radius: 8px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family:
    ui-monospace, 'Cascadia Code', 'Fira Code', monospace; font-size: 14px;
    line-height: 1.6; padding: 2rem; }
  h1 { font-size: 1.6rem; color: var(--blue); margin-bottom: 0.5rem; }
  h2 { font-size: 1.2rem; color: var(--text-muted); margin: 1.5rem 0 0.75rem; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 99px;
    font-size: 0.75rem; font-weight: bold; margin: 0 4px; }
  .green { color: var(--green); } .yellow { color: var(--yellow); }
  .orange { color: var(--orange); } .red { color: var(--red); }
  .bg-green { background: var(--green); color: #0f172a; }
  .bg-red { background: var(--red); color: white; }
  .bg-yellow { background: var(--yellow); color: #0f172a; }
  table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
  th { background: var(--surface2); text-align: left; padding: 8px 12px;
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--text-muted); }
  td { padding: 8px 12px; border-bottom: 1px solid var(--surface2);
    vertical-align: top; }
  tr:hover td { background: var(--surface); }
  .score-bar-wrap { display: flex; align-items: center; gap: 8px; }
  .score-bar { height: 6px; border-radius: 3px; background: var(--surface2);
    flex: 1; min-width: 60px; }
  .score-fill { height: 100%; border-radius: 3px; }
  .meta { color: var(--text-muted); font-size: 0.8rem; margin-top: 1.5rem; }
  .summary-box { background: var(--surface); border-left: 4px solid var(--blue);
    padding: 1rem 1.25rem; border-radius: var(--radius); margin: 1rem 0; }
  code { background: var(--surface2); padding: 1px 6px; border-radius: 4px; }
</style>
"""


def _score_css_class(score: float) -> str:
    if score >= 0.95:
        return "green"
    if score >= 0.80:
        return "yellow"
    if score >= 0.60:
        return "orange"
    return "red"


def _build_run_html(r: CanaryRunResult) -> str:
    score = r.overall_score
    rows = ""
    for pr in r.probe_results:
        cls = _score_css_class(pr.score)
        badge = '<span class="badge bg-green">PASS</span>' if pr.passed else '<span class="badge bg-red">FAIL</span>'
        bar_w = int(pr.score * 100)
        rows += (
            f"<tr><td><b>{pr.probe_name}</b></td>"
            f"<td>{pr.category.value}</td>"
            f"<td><code>{pr.prompt_id}</code></td>"
            f"<td>{badge}</td>"
            f'<td><div class="score-bar-wrap">'
            f'<span class="{cls}">{pr.score:.2f}</span>'
            f'<div class="score-bar"><div class="score-fill" style="width:{bar_w}%;'
            f'background:var(--{cls})"></div></div></div></td>'
            f"<td>{pr.details[:200]}</td></tr>\n"
        )

    overall_cls = _score_css_class(score)
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>PromptCanary — {r.suite_name}</title>{_HTML_STYLE}</head>
<body>
<h1>🐦 PromptCanary Run Report</h1>
<div class="summary-box">
  <b>Suite:</b> <code>{r.suite_name}</code> &nbsp;|&nbsp;
  <b>Provider:</b> <code>{r.provider.model_id}</code> &nbsp;|&nbsp;
  <b>Score:</b> <span class="{overall_cls}"><b>{score:.1%}</b></span> &nbsp;|&nbsp;
  <b>Pass rate:</b> {r.pass_rate:.1%} &nbsp;|&nbsp;
  <b>Probes:</b> {len(r.probe_results)}
</div>
<h2>Probe Results</h2>
<table>
<thead><tr><th>Probe</th><th>Category</th><th>Prompt</th>
<th>Result</th><th>Score</th><th>Details</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p class="meta">Run ID: <code>{r.run_id}</code> &nbsp;·&nbsp;
Generated by <a href="https://github.com/promptcanary/promptcanary"
style="color:var(--blue)">PromptCanary</a></p>
</body></html>"""


def _build_drift_html(dr: DriftReport) -> str:
    sev_colour = {
        DriftSeverity.NONE: "green", DriftSeverity.LOW: "yellow",
        DriftSeverity.MEDIUM: "orange", DriftSeverity.HIGH: "red",
        DriftSeverity.CRITICAL: "red",
    }.get(dr.severity, "yellow")

    rows = ""
    for c in dr.comparisons:
        reg_cls = "red" if c.regression else ("green" if c.improvement else "")
        delta_str = f"{c.score_delta:+.2f}"
        rows += (
            f"<tr><td><b>{c.probe_name}</b></td>"
            f"<td>{c.category.value}</td>"
            f"<td><code>{c.prompt_id}</code></td>"
            f"<td>{c.baseline_score:.2f}</td>"
            f"<td class='{reg_cls}'><b>{c.current_score:.2f}</b></td>"
            f"<td class='{reg_cls}'><b>{delta_str}</b></td>"
            f"<td>{'⬇ REG' if c.regression else '⬆ IMP' if c.improvement else '—'}</td>"
            f"<td>{c.current_details[:150]}</td></tr>\n"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>PromptCanary Drift — {dr.suite_name}</title>{_HTML_STYLE}</head>
<body>
<h1>🚨 PromptCanary Drift Report</h1>
<div class="summary-box">
  <b>Suite:</b> <code>{dr.suite_name}</code> &nbsp;|&nbsp;
  <b>Provider:</b> <code>{dr.provider.model_id}</code> &nbsp;|&nbsp;
  <b>Severity:</b> <span class="{sev_colour}"><b>{dr.severity.value.upper()}</b></span><br/>
  <b>Score:</b> {dr.overall_baseline_score:.1%} → {dr.overall_current_score:.1%}
  (<span class="{'red' if dr.overall_score_delta < 0 else 'green'}">{dr.overall_score_delta:+.1%}</span>)
  &nbsp;|&nbsp; Regressions: <span class="red"><b>{len(dr.regressions)}</b></span>
  &nbsp;|&nbsp; Improvements: <span class="green"><b>{len(dr.improvements)}</b></span>
</div>
<h2>Comparison Table</h2>
<table>
<thead><tr><th>Probe</th><th>Category</th><th>Prompt</th>
<th>Baseline</th><th>Current</th><th>Δ</th><th>Status</th><th>Details</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p class="meta">Report ID: <code>{dr.report_id}</code> &nbsp;·&nbsp;
Baseline: <code>{dr.baseline_snapshot_id[:8]}</code> &nbsp;·&nbsp;
Generated by <a href="https://github.com/promptcanary/promptcanary"
style="color:var(--blue)">PromptCanary</a></p>
</body></html>"""
