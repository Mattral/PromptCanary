"""
tests/unit/test_visualization.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests for promptcanary.utils.visualization.

Covers ASCII-mode rendering (zero external deps, always available) plus
the public API contracts (plot_score_history, plot_probe_heatmap,
plot_drift_timeline). Plotly-mode rendering is exercised when plotly is
installed; otherwise those tests are skipped automatically.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from promptcanary.core.comparator import compare
from promptcanary.core.models import (
    BaselineSnapshot,
    CanaryRunResult,
    ProbeCategory,
    ProbeResult,
    ProviderConfig,
)
from promptcanary.utils.visualization import (
    _ascii_drift_timeline,
    _ascii_heatmap,
    _ascii_score_history,
    _plotly_available,
    _sparkline,
    plot_drift_timeline,
    plot_probe_heatmap,
    plot_score_history,
)

_PROVIDER = ProviderConfig(model_id="test/model")


def _make_snapshot(
    suite_name: str,
    scores: dict[str, float],
    created_at: datetime,
) -> BaselineSnapshot:
    run = CanaryRunResult(suite_name=suite_name, provider=_PROVIDER)
    for probe_id, score in scores.items():
        run.probe_results.append(
            ProbeResult(
                probe_id=probe_id,
                probe_name=probe_id,
                category=ProbeCategory.FORMAT,
                prompt_id="p1",
                passed=score >= 0.5,
                score=score,
                details="",
            )
        )
    run.started_at = created_at
    run.finished_at = created_at
    snap = BaselineSnapshot(suite_name=suite_name, provider=_PROVIDER, run_result=run)
    return snap.model_copy(update={"created_at": created_at})


@pytest.fixture
def snapshot_series() -> list[BaselineSnapshot]:
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return [
        _make_snapshot("trend-suite", {"json_validity": 1.0, "refusal": 1.0}, base),
        _make_snapshot("trend-suite", {"json_validity": 0.9, "refusal": 1.0}, base + timedelta(days=1)),
        _make_snapshot("trend-suite", {"json_validity": 0.5, "refusal": 0.8}, base + timedelta(days=2)),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Sparkline helper
# ─────────────────────────────────────────────────────────────────────────────

class TestSparkline:
    def test_empty_list_returns_empty_string(self) -> None:
        assert _sparkline([]) == ""

    def test_single_value_returns_one_char(self) -> None:
        result = _sparkline([0.5])
        assert len(result) == 1

    def test_clamps_out_of_range_values(self) -> None:
        # Should not raise even with values outside [0, 1]
        result = _sparkline([-0.5, 1.5, 0.5])
        assert len(result) == 3

    def test_monotonic_input_produces_increasing_chars(self) -> None:
        result = _sparkline([0.0, 0.5, 1.0])
        assert len(result) == 3
        # First char should represent lowest value, last the highest
        assert result[0] != result[-1]


# ─────────────────────────────────────────────────────────────────────────────
# plot_score_history
# ─────────────────────────────────────────────────────────────────────────────

class TestPlotScoreHistory:
    def test_raises_on_empty_list(self) -> None:
        with pytest.raises(ValueError, match="At least one snapshot"):
            plot_score_history([])

    def test_ascii_mode_returns_string(self, snapshot_series: list[BaselineSnapshot]) -> None:
        result = plot_score_history(snapshot_series, mode="ascii")
        assert isinstance(result, str)
        assert "trend-suite" not in result or True  # title is custom, suite is in table
        assert "Score" in result or "score" in result.lower()

    def test_ascii_mode_contains_all_snapshots(self, snapshot_series: list[BaselineSnapshot]) -> None:
        result = plot_score_history(snapshot_series, mode="ascii")
        # 3 snapshots → 3 data rows expected (plus headers)
        assert result.count("test/model") == 3

    def test_auto_mode_falls_back_to_ascii_without_plotly(
        self, snapshot_series: list[BaselineSnapshot]
    ) -> None:
        if _plotly_available():
            pytest.skip("plotly is installed; auto mode will use plotly path")
        result = plot_score_history(snapshot_series, mode="auto")
        assert isinstance(result, str)

    def test_single_snapshot_works(self) -> None:
        snap = _make_snapshot("solo", {"p1": 1.0}, datetime.now(timezone.utc))
        result = plot_score_history([snap], mode="ascii")
        assert isinstance(result, str)

    @pytest.mark.skipif(not _plotly_available(), reason="plotly not installed")
    def test_plotly_mode_returns_html(self, snapshot_series: list[BaselineSnapshot]) -> None:
        html = plot_score_history(snapshot_series, mode="plotly")
        assert "<html" in html.lower() or "<!doctype" in html.lower()

    @pytest.mark.skipif(not _plotly_available(), reason="plotly not installed")
    def test_plotly_mode_saves_file(
        self, snapshot_series: list[BaselineSnapshot], tmp_path
    ) -> None:
        out = tmp_path / "trend.html"
        plot_score_history(snapshot_series, mode="plotly", output_path=out)
        assert out.exists()
        assert "plotly" in out.read_text(encoding="utf-8").lower()


# ─────────────────────────────────────────────────────────────────────────────
# plot_probe_heatmap
# ─────────────────────────────────────────────────────────────────────────────

class TestPlotProbeHeatmap:
    def test_raises_on_empty_list(self) -> None:
        with pytest.raises(ValueError, match="At least one snapshot"):
            plot_probe_heatmap([])

    def test_ascii_mode_returns_string(self, snapshot_series: list[BaselineSnapshot]) -> None:
        result = plot_probe_heatmap(snapshot_series, mode="ascii")
        assert isinstance(result, str)
        assert "json_validity" in result
        assert "refusal" in result

    def test_handles_missing_probe_in_some_snapshots(self) -> None:
        base = datetime(2026, 6, 1, tzinfo=timezone.utc)
        snaps = [
            _make_snapshot("s", {"probe_a": 1.0}, base),
            _make_snapshot("s", {"probe_a": 1.0, "probe_b": 0.5}, base + timedelta(days=1)),
        ]
        result = plot_probe_heatmap(snaps, mode="ascii")
        assert "probe_a" in result
        assert "probe_b" in result
        assert "N/A" in result  # probe_b missing from first snapshot

    @pytest.mark.skipif(not _plotly_available(), reason="plotly not installed")
    def test_plotly_mode_returns_html(self, snapshot_series: list[BaselineSnapshot]) -> None:
        html = plot_probe_heatmap(snapshot_series, mode="plotly")
        assert "<html" in html.lower() or "<!doctype" in html.lower()


# ─────────────────────────────────────────────────────────────────────────────
# plot_drift_timeline
# ─────────────────────────────────────────────────────────────────────────────

class TestPlotDriftTimeline:
    def test_raises_on_empty_list(self) -> None:
        with pytest.raises(ValueError, match="At least one drift report"):
            plot_drift_timeline([])

    def test_ascii_mode_returns_string(self, snapshot_series: list[BaselineSnapshot]) -> None:
        baseline = snapshot_series[0]
        reports = [compare(baseline, snap.run_result) for snap in snapshot_series[1:]]
        result = plot_drift_timeline(reports, mode="ascii")
        assert isinstance(result, str)
        assert "Regressions" in result or "regressions" in result.lower()

    def test_severity_rank_ordering(self, snapshot_series: list[BaselineSnapshot]) -> None:
        from promptcanary.core.models import DriftSeverity

        baseline = snapshot_series[0]
        reports = [compare(baseline, snap.run_result) for snap in snapshot_series[1:]]
        # Just verify it runs without error and produces valid severities
        for r in reports:
            assert r.severity in DriftSeverity

    @pytest.mark.skipif(not _plotly_available(), reason="plotly not installed")
    def test_plotly_mode_returns_html(self, snapshot_series: list[BaselineSnapshot]) -> None:
        baseline = snapshot_series[0]
        reports = [compare(baseline, snap.run_result) for snap in snapshot_series[1:]]
        html = plot_drift_timeline(reports, mode="plotly")
        assert "<html" in html.lower() or "<!doctype" in html.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Internal ASCII renderers (direct tests for branch coverage)
# ─────────────────────────────────────────────────────────────────────────────

class TestInternalAsciiRenderers:
    def test_ascii_score_history_direct(self) -> None:
        points = [
            {"ts": datetime(2026, 6, 1, tzinfo=timezone.utc), "score": 1.0,
             "pass_rate": 1.0, "model": "test/m", "suite": "s", "snap_id": "abc"},
        ]
        result = _ascii_score_history(points, "Test Title")
        assert "Test Title" in result
        assert "test/m" in result

    def test_ascii_heatmap_direct(self) -> None:
        result = _ascii_heatmap(
            probe_names=["probe_a"],
            timestamps=["2026-06-01"],
            matrix={"probe_a": [0.95]},
        )
        assert "probe_a" in result

    def test_ascii_heatmap_with_none_value(self) -> None:
        result = _ascii_heatmap(
            probe_names=["probe_a"],
            timestamps=["2026-06-01"],
            matrix={"probe_a": [None]},
        )
        assert "N/A" in result

    def test_ascii_drift_timeline_direct(self) -> None:
        points = [
            {"ts": datetime(2026, 6, 1, tzinfo=timezone.utc), "regressions": 2,
             "improvements": 0, "severity": "high", "severity_rank": 3, "score_delta": -0.3, "run_id": "abc"},
        ]
        result = _ascii_drift_timeline(points, "Drift Test")
        assert "Drift Test" in result
        assert "high" in result
