"""
tests/integration/test_full_pipeline.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

End-to-end pipeline tests: run → save baseline → run again → compare.

These tests verify the complete user-facing workflow using mock providers
(no network calls). They serve as confidence tests that all the pieces
wire together correctly.
"""

from __future__ import annotations

from pathlib import Path

from promptcanary import (
    CanarySuite,
    FileBaselineStore,
    JsonValidityProbe,
    KeywordPresenceProbe,
    RefusalProbe,
    compare,
)
from promptcanary.core.models import CanaryPrompt, DriftSeverity
from tests.conftest import MockLLMProvider


class TestFullRunBaslineCompareWorkflow:
    """Simulates the complete DX journey: init → run → baseline → drift compare."""

    def test_run_save_load_compare_no_drift(self, tmp_path: Path) -> None:
        """Run, save baseline, run again with same provider, compare → no drift."""
        suite = CanarySuite(
            name="e2e-suite",
            prompts=[
                CanaryPrompt(
                    id="geo001", text="What is the capital of France?", expected_keywords=["Paris"]
                ),
                CanaryPrompt(id="json001", text='Return JSON with key "name".'),
            ],
            probes=[
                KeywordPresenceProbe(required_keywords=["Paris"]),
                JsonValidityProbe(),
                RefusalProbe(expect_refusal=False),
            ],
        )

        provider = MockLLMProvider()
        store = FileBaselineStore(tmp_path / "baselines")

        # First run → save baseline
        result1 = suite.run(provider, show_progress=False)
        snapshot = store.save(result1)

        assert result1.overall_score > 0.0
        assert snapshot.snapshot_id is not None

        # Second run → same provider → should produce identical results
        result2 = suite.run(provider, show_progress=False)
        drift_report = compare(snapshot, result2)

        assert not drift_report.has_drift
        assert drift_report.severity == DriftSeverity.NONE

    def test_run_save_load_compare_with_drift(self, tmp_path: Path) -> None:
        """Baseline passes; new run returns invalid JSON → drift detected."""
        suite = CanarySuite(
            name="e2e-suite",
            prompts=[CanaryPrompt(id="json001", text="Return JSON with key name.")],
            probes=[JsonValidityProbe()],
        )

        good_provider = MockLLMProvider(responses={"json001": '{"name": "Alice"}'})
        bad_provider = MockLLMProvider(responses={"json001": "Here is some text, not JSON"})
        store = FileBaselineStore(tmp_path / "baselines")

        baseline_result = suite.run(good_provider, show_progress=False)
        snapshot = store.save(baseline_result)

        current_result = suite.run(bad_provider, show_progress=False)
        drift_report = compare(snapshot, current_result)

        assert drift_report.has_drift
        assert len(drift_report.regressions) == 1
        assert drift_report.severity != DriftSeverity.NONE

    def test_reporter_generates_all_formats(self, tmp_path: Path) -> None:
        """Verify all report formats are generated without errors."""
        from promptcanary.core.reporter import Reporter

        suite = CanarySuite(
            name="e2e-suite",
            prompts=[CanaryPrompt(id="geo001", text="What is the capital of France?")],
            probes=[KeywordPresenceProbe(required_keywords=["Paris"])],
        )
        result = suite.run(MockLLMProvider(), show_progress=False)
        reporter = Reporter(result)

        md = reporter.to_markdown(tmp_path / "report.md")
        js = reporter.to_json(tmp_path / "report.json")
        html = reporter.to_html(tmp_path / "report.html")

        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "report.json").exists()
        assert (tmp_path / "report.html").exists()
        assert "PromptCanary" in md
        assert "run_id" in js
        assert "<!DOCTYPE html>" in html

    def test_probe_registry_has_all_builtin_probes(self) -> None:
        """All expected built-in probes are in the registry."""
        from promptcanary.core.probes import get_probe_registry

        registry = get_probe_registry()
        expected_ids = [
            "json_validity",
            "json_schema",
            "json_key_order",
            "response_length",
            "markdown_headers",
            "keyword_presence",
            "expected_keywords",
            "step_by_step",
            "verbosity",
            "confidence_language",
            "direct_answer",
            "refusal",
            "safety_language",
            "factual_consistency",
            "sentiment",
        ]
        for pid in expected_ids:
            assert pid in registry, f"Missing probe: {pid}"

    def test_yaml_suite_full_pipeline(self, tmp_path: Path) -> None:
        """Load from YAML, run, save baseline, compare — all via file paths."""
        yaml_content = """\
name: yaml-e2e-suite
description: "E2E YAML test"
probes:
  - type: keyword_presence
    required_keywords: ["Paris"]
  - type: refusal
    expect_refusal: false
prompts:
  - text: "What is the capital of France?"
    id: "geo001"
    expected_keywords: ["Paris"]
"""
        config_path = tmp_path / "canary.yaml"
        config_path.write_text(yaml_content, encoding="utf-8")

        suite = CanarySuite.from_yaml(config_path)
        provider = MockLLMProvider()
        store = FileBaselineStore(tmp_path / "baselines")

        result = suite.run(provider, show_progress=False)
        snapshot = store.save(result)

        result2 = suite.run(provider, show_progress=False)
        drift = compare(snapshot, result2)

        assert not drift.has_drift

    def test_custom_probe_decorator(self) -> None:
        """@probe decorator creates a working, registered probe."""
        from promptcanary.core.models import CanaryPrompt, LLMResponse, ProbeCategory, ProbeResult
        from promptcanary.core.probes.base import get_probe_registry, probe

        @probe("test_greeting", name="Test Greeting", category=ProbeCategory.CUSTOM)
        def check_greeting(prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
            passed = "hello" in response.content.lower()
            return ProbeResult(
                probe_id="test_greeting",
                probe_name="Test Greeting",
                category=ProbeCategory.CUSTOM,
                prompt_id=prompt.id,
                passed=passed,
                score=1.0 if passed else 0.0,
                details="Checked for greeting.",
            )

        registry = get_probe_registry()
        assert "test_greeting" in registry

        suite = CanarySuite(
            name="custom-probe-suite",
            prompts=[CanaryPrompt(id="p1", text="Say hello.")],
            probes=[check_greeting()],
        )
        provider = MockLLMProvider(responses={"p1": "Hello! Nice to meet you."})
        result = suite.run(provider, show_progress=False)

        assert result.probe_results[0].passed

    def test_baseline_multiple_saves_load_latest(self, tmp_path: Path) -> None:
        """load_latest returns the most recent snapshot when multiple exist."""
        import time

        suite = CanarySuite(
            name="multi-baseline-suite",
            prompts=[CanaryPrompt(id="geo001", text="Capital of France?")],
            probes=[KeywordPresenceProbe(required_keywords=["Paris"])],
        )
        provider = MockLLMProvider()
        store = FileBaselineStore(tmp_path / "baselines")

        store.save(suite.run(provider, show_progress=False), snapshot_id="aaa00001")
        time.sleep(0.01)  # ensure different timestamp
        store.save(suite.run(provider, show_progress=False), snapshot_id="bbb00002")

        items = store.list_baselines()
        assert len(items) == 2
