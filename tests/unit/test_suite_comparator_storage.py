"""
tests/unit/test_suite_comparator_storage.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Integration-style unit tests for the core pipeline:
  - CanarySuite construction and YAML loading
  - CanarySuite.run() with mock providers
  - compare() drift detection logic
  - FileBaselineStore save/load/list/delete
  - Reporter and DriftReporter output (no rendering, just structure)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from promptcanary.core.comparator import compare
from promptcanary.core.models import (
    BaselineSnapshot,
    CanaryPrompt,
    CanaryRunResult,
    ProbeCategory,
    ProbeComparison,
    ProbeResult,
)
from promptcanary.core.probes import JsonValidityProbe, KeywordPresenceProbe
from promptcanary.core.reporter import DriftReporter, Reporter
from promptcanary.core.suite import CanarySuite
from promptcanary.storage.file import FileBaselineStore
from tests.conftest import PROVIDER_CFG, MockLLMProvider

# ─────────────────────────────────────────────────────────────────────────────
# CanarySuite construction
# ─────────────────────────────────────────────────────────────────────────────


class TestCanarySuiteConstruction:
    def test_basic_construction(self) -> None:
        suite = CanarySuite(
            name="test",
            prompts=[CanaryPrompt(text="Hello")],
            probes=[JsonValidityProbe()],
        )
        assert suite.name == "test"
        assert len(suite.prompts) == 1
        assert len(suite.probes) == 1

    def test_rejects_empty_prompts(self) -> None:
        with pytest.raises(ValueError, match="at least one prompt"):
            CanarySuite(name="test", prompts=[], probes=[JsonValidityProbe()])

    def test_rejects_empty_probes(self) -> None:
        with pytest.raises(ValueError, match="at least one probe"):
            CanarySuite(
                name="test",
                prompts=[CanaryPrompt(text="Hello")],
                probes=[],
            )

    def test_repr(self) -> None:
        suite = CanarySuite(
            name="my-suite",
            prompts=[CanaryPrompt(text="Hello")],
            probes=[JsonValidityProbe()],
        )
        assert "my-suite" in repr(suite)
        assert "prompts=1" in repr(suite)

    def test_from_yaml(self, sample_canary_yaml: Path) -> None:
        suite = CanarySuite.from_yaml(sample_canary_yaml)
        assert suite.name == "yaml-test-suite"
        assert len(suite.prompts) == 2
        assert len(suite.probes) == 2

    def test_from_yaml_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            CanarySuite.from_yaml("/nonexistent/path/canary.yaml")

    def test_to_yaml_template_roundtrip(self, sample_canary_yaml: Path) -> None:
        suite = CanarySuite.from_yaml(sample_canary_yaml)
        yaml_str = suite.to_yaml_template()
        assert "yaml-test-suite" in yaml_str
        assert "keyword_presence" in yaml_str


# ─────────────────────────────────────────────────────────────────────────────
# CanarySuite.run()
# ─────────────────────────────────────────────────────────────────────────────


class TestCanarySuiteRun:
    def test_run_returns_result(
        self, basic_suite: CanarySuite, mock_provider: MockLLMProvider
    ) -> None:
        result = basic_suite.run(mock_provider, show_progress=False)
        assert isinstance(result, CanaryRunResult)
        assert result.suite_name == "test-suite"
        assert len(result.probe_results) == 1  # 1 prompt x 1 probe
        assert len(result.llm_responses) == 1

    def test_run_calls_provider_once_per_prompt(
        self, full_suite: CanarySuite, mock_provider: MockLLMProvider
    ) -> None:
        _result = full_suite.run(mock_provider, show_progress=False)
        assert mock_provider.call_count == 3  # 3 prompts

    def test_run_applies_all_probes(
        self, full_suite: CanarySuite, mock_provider: MockLLMProvider
    ) -> None:
        result = full_suite.run(mock_provider, show_progress=False)
        # 3 prompts x 3 probes = 9 probe results
        assert len(result.probe_results) == 9

    def test_run_captures_timestamp(
        self, basic_suite: CanarySuite, mock_provider: MockLLMProvider
    ) -> None:
        result = basic_suite.run(mock_provider, show_progress=False)
        assert result.started_at is not None
        assert result.finished_at is not None
        assert result.duration_ms is not None
        assert result.duration_ms >= 0

    def test_run_passes_system_prompt(self) -> None:
        """Verify suite's default_system_prompt is forwarded to provider."""
        calls = []

        class RecordingProvider(MockLLMProvider):
            def complete(self, prompt, *, system_prompt=None):
                calls.append(system_prompt)
                return super().complete(prompt, system_prompt=system_prompt)

        suite = CanarySuite(
            name="test",
            prompts=[CanaryPrompt(id="geo001", text="What is the capital of France?")],
            probes=[KeywordPresenceProbe(required_keywords=["Paris"])],
            default_system_prompt="You are a geography expert.",
        )
        suite.run(RecordingProvider(), show_progress=False)
        assert calls[0] == "You are a geography expert."

    def test_probe_exception_becomes_failure_not_crash(self) -> None:
        """A probe that raises must produce a failed ProbeResult, not crash the run."""
        from promptcanary.core.models import (
            LLMResponse,  # noqa: F401 -- used by BrokenProbe type signature
        )
        from promptcanary.core.probes.base import BaseProbe

        class BrokenProbe(BaseProbe):
            probe_id = "broken_test_probe"
            name = "Broken Test Probe"
            category = ProbeCategory.CUSTOM

            def evaluate(self, prompt, response):
                raise RuntimeError("Simulated probe crash")

        suite = CanarySuite(
            name="test",
            prompts=[CanaryPrompt(id="geo001", text="test")],
            probes=[BrokenProbe()],
        )
        result = suite.run(MockLLMProvider(), show_progress=False)
        assert len(result.probe_results) == 1
        assert not result.probe_results[0].passed
        assert "exception" in result.probe_results[0].details.lower()


# ─────────────────────────────────────────────────────────────────────────────
# compare()
# ─────────────────────────────────────────────────────────────────────────────


class TestComparator:
    def _make_snapshot(self, results: list[ProbeResult]) -> BaselineSnapshot:
        run = CanaryRunResult(suite_name="test-suite", provider=PROVIDER_CFG)
        run.probe_results.extend(results)
        return BaselineSnapshot(suite_name="test-suite", provider=PROVIDER_CFG, run_result=run)

    def _make_current(self, results: list[ProbeResult]) -> CanaryRunResult:
        run = CanaryRunResult(suite_name="test-suite", provider=PROVIDER_CFG)
        run.probe_results.extend(results)
        return run

    def _pr(self, probe_id: str, prompt_id: str, score: float, passed: bool) -> ProbeResult:
        return ProbeResult(
            probe_id=probe_id,
            probe_name=probe_id,
            category=ProbeCategory.FORMAT,
            prompt_id=prompt_id,
            passed=passed,
            score=score,
            details="",
        )

    def test_no_drift_when_same_scores(self) -> None:
        results = [self._pr("json_validity", "p1", 1.0, True)]
        snap = self._make_snapshot(results)
        current = self._make_current(results)
        report = compare(snap, current)
        assert not report.has_drift

    def test_regression_when_score_drops_below_threshold(self) -> None:
        baseline_results = [self._pr("json_validity", "p1", 1.0, True)]
        current_results = [self._pr("json_validity", "p1", 0.0, False)]
        snap = self._make_snapshot(baseline_results)
        current = self._make_current(current_results)
        report = compare(snap, current, regression_threshold=0.05)
        assert report.has_drift
        assert len(report.regressions) == 1

    def test_improvement_detected(self) -> None:
        baseline_results = [self._pr("json_validity", "p1", 0.0, False)]
        current_results = [self._pr("json_validity", "p1", 1.0, True)]
        snap = self._make_snapshot(baseline_results)
        current = self._make_current(current_results)
        report = compare(snap, current)
        assert not report.has_drift
        assert len(report.improvements) == 1

    def test_suite_name_mismatch_raises(self) -> None:
        results = [self._pr("json_validity", "p1", 1.0, True)]
        snap = self._make_snapshot(results)
        current = CanaryRunResult(suite_name="different-suite", provider=PROVIDER_CFG)
        current.probe_results.extend(results)
        with pytest.raises(ValueError, match="Suite name mismatch"):
            compare(snap, current)

    def test_multiple_probes_multiple_prompts(self) -> None:
        baseline = [
            self._pr("json_validity", "p1", 1.0, True),
            self._pr("json_validity", "p2", 1.0, True),
            self._pr("keyword_presence", "p1", 1.0, True),
        ]
        current = [
            self._pr("json_validity", "p1", 1.0, True),  # stable
            self._pr("json_validity", "p2", 0.0, False),  # regression
            self._pr("keyword_presence", "p1", 0.5, True),  # minor drop, still passes
        ]
        snap = self._make_snapshot(baseline)
        curr = self._make_current(current)
        report = compare(snap, curr, regression_threshold=0.05)
        assert len(report.comparisons) == 3
        assert len(report.regressions) == 1


# ─────────────────────────────────────────────────────────────────────────────
# FileBaselineStore
# ─────────────────────────────────────────────────────────────────────────────


class TestFileBaselineStore:
    def test_save_and_load_by_id(
        self, clean_run_result: CanaryRunResult, tmp_baselines: Path
    ) -> None:
        store = FileBaselineStore(tmp_baselines)
        snap = store.save(clean_run_result)
        loaded = store.load(snap.snapshot_id)
        assert loaded.snapshot_id == snap.snapshot_id
        assert loaded.suite_name == clean_run_result.suite_name

    def test_save_creates_json_file(
        self, clean_run_result: CanaryRunResult, tmp_baselines: Path
    ) -> None:
        store = FileBaselineStore(tmp_baselines)
        store.save(clean_run_result)
        files = list(tmp_baselines.glob("*.json"))
        assert len(files) == 1

    def test_load_latest(self, clean_run_result: CanaryRunResult, tmp_baselines: Path) -> None:
        store = FileBaselineStore(tmp_baselines)
        store.save(clean_run_result)
        loaded = store.load_latest(suite_name="test-suite")
        assert loaded.suite_name == "test-suite"

    def test_load_from_path(self, clean_run_result: CanaryRunResult, tmp_baselines: Path) -> None:
        store = FileBaselineStore(tmp_baselines)
        snap = store.save(clean_run_result)
        files = list(tmp_baselines.glob("*.json"))
        loaded = store.load_from_path(files[0])
        assert loaded.snapshot_id == snap.snapshot_id

    def test_list_baselines(self, clean_run_result: CanaryRunResult, tmp_baselines: Path) -> None:
        store = FileBaselineStore(tmp_baselines)
        store.save(clean_run_result)
        items = store.list_baselines()
        assert len(items) == 1
        assert items[0]["suite_name"] == "test-suite"

    def test_delete_baseline(self, clean_run_result: CanaryRunResult, tmp_baselines: Path) -> None:
        store = FileBaselineStore(tmp_baselines)
        snap = store.save(clean_run_result)
        deleted = store.delete(snap.snapshot_id)
        assert deleted
        assert list(tmp_baselines.glob("*.json")) == []

    def test_load_nonexistent_raises(self, tmp_baselines: Path) -> None:
        store = FileBaselineStore(tmp_baselines)
        with pytest.raises(FileNotFoundError):
            store.load("nonexistent-id-abc")

    def test_load_latest_no_baselines_raises(self, tmp_baselines: Path) -> None:
        store = FileBaselineStore(tmp_baselines)
        with pytest.raises(FileNotFoundError):
            store.load_latest("test-suite")

    def test_save_with_note(self, clean_run_result: CanaryRunResult, tmp_baselines: Path) -> None:
        store = FileBaselineStore(tmp_baselines)
        store.save(clean_run_result, note="Pre-release baseline v1")
        items = store.list_baselines()
        assert items[0]["note"] == "Pre-release baseline v1"

    def test_creates_directory_if_not_exists(
        self, tmp_path: Path, clean_run_result: CanaryRunResult
    ) -> None:
        new_dir = tmp_path / "nested" / "baselines"
        _store = FileBaselineStore(new_dir)
        assert new_dir.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Reporter
# ─────────────────────────────────────────────────────────────────────────────


class TestReporter:
    def test_to_markdown_returns_string(self, clean_run_result: CanaryRunResult) -> None:
        reporter = Reporter(clean_run_result)
        md = reporter.to_markdown()
        assert "PromptCanary" in md
        assert clean_run_result.suite_name in md
        assert "PASS" in md or "FAIL" in md

    def test_to_markdown_saves_file(
        self, clean_run_result: CanaryRunResult, tmp_path: Path
    ) -> None:
        reporter = Reporter(clean_run_result)
        out = tmp_path / "report.md"
        reporter.to_markdown(out)
        assert out.exists()
        assert "PromptCanary" in out.read_text()

    def test_to_json_is_valid_json(self, clean_run_result: CanaryRunResult) -> None:
        reporter = Reporter(clean_run_result)
        js = reporter.to_json()
        parsed = json.loads(js)
        assert "run_id" in parsed
        assert "probe_results" in parsed

    def test_to_html_returns_html(self, clean_run_result: CanaryRunResult) -> None:
        reporter = Reporter(clean_run_result)
        html = reporter.to_html()
        assert "<!DOCTYPE html>" in html
        assert "PromptCanary" in html

    def test_print_terminal_no_crash(self, clean_run_result: CanaryRunResult) -> None:
        from io import StringIO

        from rich.console import Console

        buf = StringIO()
        con = Console(file=buf, force_terminal=False)
        Reporter(clean_run_result).print_terminal(con)
        output = buf.getvalue()
        assert len(output) > 0


class TestDriftReporter:
    def _make_drift_report(self, has_regression: bool):
        from datetime import datetime, timezone

        from promptcanary.core.models import DriftReport

        delta = -0.8 if has_regression else 0.0
        comparisons = [
            ProbeComparison(
                probe_id="json_validity",
                probe_name="JSON Validity",
                category=ProbeCategory.FORMAT,
                prompt_id="p1",
                baseline_score=1.0,
                current_score=1.0 + delta,
                score_delta=delta,
                baseline_passed=True,
                current_passed=not has_regression,
                regression=has_regression,
                improvement=False,
                baseline_details="Valid JSON.",
                current_details="Invalid JSON." if has_regression else "Valid JSON.",
            )
        ]
        return DriftReport(
            suite_name="test-suite",
            provider=PROVIDER_CFG,
            baseline_snapshot_id="snap-001",
            baseline_created_at=datetime.now(timezone.utc),
            current_run_id="run-002",
            comparisons=comparisons,
        )

    def test_to_markdown_no_drift(self) -> None:
        report = self._make_drift_report(has_regression=False)
        md = DriftReporter(report).to_markdown()
        assert "No drift" in md or "NONE" in md

    def test_to_markdown_with_drift(self) -> None:
        report = self._make_drift_report(has_regression=True)
        md = DriftReporter(report).to_markdown()
        assert "Regressions" in md

    def test_to_html_returns_html(self) -> None:
        report = self._make_drift_report(has_regression=True)
        html = DriftReporter(report).to_html()
        assert "<!DOCTYPE html>" in html

    def test_to_json_is_valid_json(self) -> None:
        report = self._make_drift_report(has_regression=False)
        js = DriftReporter(report).to_json()
        parsed = json.loads(js)
        assert "report_id" in parsed
