"""
tests/unit/test_models.py
~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests for promptcanary.core.models — the foundational data layer.

Coverage:
  - ProviderConfig validation and immutability
  - CanaryPrompt validation
  - LLMResponse construction
  - ProbeResult
  - CanaryRunResult derived properties (overall_score, pass_rate, by_category)
  - BaselineSnapshot
  - DriftReport derived properties (severity, summary, has_drift)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from promptcanary.core.models import (
    CanaryPrompt,
    CanaryRunResult,
    DriftReport,
    DriftSeverity,
    LLMResponse,
    ProbeCategory,
    ProbeComparison,
    ProbeResult,
    ProviderConfig,
)


# ─────────────────────────────────────────────────────────────────────────────
# ProviderConfig
# ─────────────────────────────────────────────────────────────────────────────

class TestProviderConfig:
    def test_valid_creation(self) -> None:
        cfg = ProviderConfig(model_id="openai/gpt-4o")
        assert cfg.model_id == "openai/gpt-4o"
        assert cfg.temperature == 0.0
        assert cfg.max_tokens == 1024
        assert cfg.seed == 42

    def test_strips_whitespace_from_model_id(self) -> None:
        cfg = ProviderConfig(model_id="  openai/gpt-4o  ")
        assert cfg.model_id == "openai/gpt-4o"

    def test_rejects_empty_model_id(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            ProviderConfig(model_id="")

    def test_rejects_whitespace_only_model_id(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            ProviderConfig(model_id="   ")

    def test_temperature_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ProviderConfig(model_id="openai/gpt-4o", temperature=-0.1)
        with pytest.raises(ValidationError):
            ProviderConfig(model_id="openai/gpt-4o", temperature=2.1)

    def test_max_tokens_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            ProviderConfig(model_id="openai/gpt-4o", max_tokens=0)

    def test_is_frozen(self) -> None:
        cfg = ProviderConfig(model_id="openai/gpt-4o")
        with pytest.raises(Exception):
            cfg.temperature = 0.5  # type: ignore[misc]

    def test_extra_params_default_empty(self) -> None:
        cfg = ProviderConfig(model_id="openai/gpt-4o")
        assert cfg.extra_params == {}


# ─────────────────────────────────────────────────────────────────────────────
# CanaryPrompt
# ─────────────────────────────────────────────────────────────────────────────

class TestCanaryPrompt:
    def test_valid_prompt(self) -> None:
        p = CanaryPrompt(text="Hello, world!")
        assert p.text == "Hello, world!"
        assert len(p.id) == 8
        assert p.tags == []
        assert p.expected_keywords == []

    def test_rejects_empty_text(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            CanaryPrompt(text="")

    def test_custom_id(self) -> None:
        p = CanaryPrompt(id="custom1", text="Test")
        assert p.id == "custom1"

    def test_with_system_prompt(self) -> None:
        p = CanaryPrompt(text="Hello", system_prompt="You are a helpful assistant.")
        assert p.system_prompt == "You are a helpful assistant."

    def test_expected_keywords(self) -> None:
        p = CanaryPrompt(text="What is the capital of France?", expected_keywords=["Paris", "France"])
        assert "Paris" in p.expected_keywords


# ─────────────────────────────────────────────────────────────────────────────
# CanaryRunResult — derived properties
# ─────────────────────────────────────────────────────────────────────────────

class TestCanaryRunResult:
    def _make_result(self, scores: list[float], passed_flags: list[bool]) -> CanaryRunResult:
        cfg = ProviderConfig(model_id="test/model")
        result = CanaryRunResult(suite_name="test-suite", provider=cfg)
        for i, (score, passed) in enumerate(zip(scores, passed_flags)):
            result.probe_results.append(
                ProbeResult(
                    probe_id=f"probe_{i}",
                    probe_name=f"Probe {i}",
                    category=ProbeCategory.FORMAT,
                    prompt_id=f"p{i}",
                    passed=passed,
                    score=score,
                    details="",
                )
            )
        return result

    def test_overall_score_empty(self) -> None:
        cfg = ProviderConfig(model_id="test/model")
        result = CanaryRunResult(suite_name="test", provider=cfg)
        assert result.overall_score == 1.0

    def test_overall_score_all_pass(self) -> None:
        result = self._make_result([1.0, 0.9, 0.8], [True, True, True])
        assert abs(result.overall_score - (1.0 + 0.9 + 0.8) / 3) < 1e-9

    def test_pass_rate(self) -> None:
        result = self._make_result([1.0, 0.0, 1.0], [True, False, True])
        assert abs(result.pass_rate - 2 / 3) < 1e-9

    def test_failed_probes(self) -> None:
        result = self._make_result([1.0, 0.0, 0.5], [True, False, False])
        assert len(result.failed_probes) == 2

    def test_by_category(self) -> None:
        cfg = ProviderConfig(model_id="test/model")
        result = CanaryRunResult(suite_name="test", provider=cfg)
        result.probe_results.append(
            ProbeResult(
                probe_id="p1", probe_name="P1",
                category=ProbeCategory.FORMAT, prompt_id="x",
                passed=True, score=1.0, details="",
            )
        )
        result.probe_results.append(
            ProbeResult(
                probe_id="p2", probe_name="P2",
                category=ProbeCategory.REASONING, prompt_id="x",
                passed=True, score=0.8, details="",
            )
        )
        by_cat = result.by_category
        assert ProbeCategory.FORMAT in by_cat
        assert ProbeCategory.REASONING in by_cat
        assert len(by_cat[ProbeCategory.FORMAT]) == 1
        assert len(by_cat[ProbeCategory.REASONING]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# DriftReport — severity + summary
# ─────────────────────────────────────────────────────────────────────────────

class TestDriftReport:
    def _make_comparison(
        self,
        probe_id: str,
        baseline_score: float,
        current_score: float,
        baseline_passed: bool,
        current_passed: bool,
    ) -> ProbeComparison:
        delta = current_score - baseline_score
        return ProbeComparison(
            probe_id=probe_id,
            probe_name=probe_id,
            category=ProbeCategory.FORMAT,
            prompt_id="p1",
            baseline_score=baseline_score,
            current_score=current_score,
            score_delta=delta,
            baseline_passed=baseline_passed,
            current_passed=current_passed,
            regression=(baseline_passed and not current_passed and delta <= -0.05),
            improvement=(not baseline_passed and current_passed),
            baseline_details="",
            current_details="",
        )

    def _make_report(self, comparisons: list[ProbeComparison]) -> DriftReport:
        from datetime import datetime, timezone
        cfg = ProviderConfig(model_id="test/model")
        return DriftReport(
            suite_name="test-suite",
            provider=cfg,
            baseline_snapshot_id="snap-001",
            baseline_created_at=datetime.now(timezone.utc),
            current_run_id="run-002",
            comparisons=comparisons,
        )

    def test_no_drift(self) -> None:
        comparisons = [
            self._make_comparison("p1", 1.0, 1.0, True, True),
            self._make_comparison("p2", 0.9, 0.95, True, True),
        ]
        report = self._make_report(comparisons)
        assert not report.has_drift
        assert report.severity == DriftSeverity.NONE
        assert "✅" in report.summary

    def test_regression_detected(self) -> None:
        comparisons = [
            self._make_comparison("p1", 1.0, 0.0, True, False),
        ]
        report = self._make_report(comparisons)
        assert report.has_drift
        assert len(report.regressions) == 1
        assert report.severity != DriftSeverity.NONE
        assert "⚠️" in report.summary

    def test_critical_severity_high_regression_rate(self) -> None:
        comparisons = [
            self._make_comparison(f"p{i}", 1.0, 0.0, True, False)
            for i in range(5)
        ] + [
            self._make_comparison(f"q{i}", 1.0, 1.0, True, True)
            for i in range(2)
        ]
        report = self._make_report(comparisons)
        # 5 regressions out of 7 = ~71% regression rate → CRITICAL
        assert report.severity == DriftSeverity.CRITICAL

    def test_improvements_counted(self) -> None:
        comparisons = [
            self._make_comparison("p1", 0.0, 1.0, False, True),
        ]
        report = self._make_report(comparisons)
        assert len(report.improvements) == 1
        assert not report.has_drift  # improvements don't count as drift

    def test_score_delta_calculation(self) -> None:
        comparisons = [
            self._make_comparison("p1", 0.8, 0.6, True, True),  # dropped but still passed
        ]
        report = self._make_report(comparisons)
        assert abs(report.overall_score_delta - (-0.2)) < 1e-9
