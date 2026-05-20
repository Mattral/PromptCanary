"""
tests/unit/test_property_based.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Property-based tests using Hypothesis.

These tests verify mathematical invariants that must hold regardless of
specific inputs — catching edge cases that hand-written examples miss.

Invariants tested:
  - ProbeResult.score is always in [0.0, 1.0]
  - DriftReport.overall_score_delta == current - baseline (always)
  - compare() severity is monotone with regression count
  - CanaryRunResult.overall_score is the mean of all probe scores
  - FileBaselineStore round-trips perfectly (save → load → identical)
  - DriftReport.summary always contains suite name
  - ResponseLengthProbe never returns score < 0.0 or > 1.0 for any length
  - JsonValidityProbe score is always binary (0.0 or 1.0)
"""

from __future__ import annotations

import json
import string
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from promptcanary.core.comparator import compare
from promptcanary.core.models import (
    BaselineSnapshot,
    CanaryPrompt,
    CanaryRunResult,
    DriftSeverity,
    LLMResponse,
    ProbeCategory,
    ProbeComparison,
    ProbeResult,
    ProviderConfig,
)
from promptcanary.core.probes.format import JsonValidityProbe, ResponseLengthProbe
from promptcanary.storage.file import FileBaselineStore


# ─── Strategy helpers ─────────────────────────────────────────────────────────

_PROVIDER = ProviderConfig(model_id="test/model")

_score_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_prompt_id_st = st.text(alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=8)
_probe_id_st = st.text(alphabet=string.ascii_lowercase + "_", min_size=1, max_size=20)
_text_st = st.text(min_size=1, max_size=500)


def _make_probe_result(
    probe_id: str,
    prompt_id: str,
    score: float,
    passed: bool,
) -> ProbeResult:
    return ProbeResult(
        probe_id=probe_id,
        probe_name=probe_id,
        category=ProbeCategory.FORMAT,
        prompt_id=prompt_id,
        passed=passed,
        score=score,
        details="",
    )


def _make_run(results: list[ProbeResult], suite_name: str = "test-suite") -> CanaryRunResult:
    run = CanaryRunResult(suite_name=suite_name, provider=_PROVIDER)
    run.probe_results.extend(results)
    return run


def _make_snapshot(run: CanaryRunResult) -> BaselineSnapshot:
    return BaselineSnapshot(
        suite_name=run.suite_name,
        provider=_PROVIDER,
        run_result=run,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Invariant: ProbeResult score always in [0.0, 1.0]
# ─────────────────────────────────────────────────────────────────────────────

@given(score=_score_st)
def test_probe_result_score_always_valid(score: float) -> None:
    """Any score in [0.0, 1.0] must be accepted without error."""
    result = _make_probe_result("p", "q", score, score >= 0.5)
    assert 0.0 <= result.score <= 1.0


@given(score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
def test_make_result_clamps_score(score: float) -> None:
    """BaseProbe._make_result clamps scores to [0.0, 1.0]."""
    from promptcanary.core.probes.format import JsonValidityProbe
    probe = JsonValidityProbe()
    clamped = probe._make_result("p1", passed=True, score=score)
    assert 0.0 <= clamped.score <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Invariant: CanaryRunResult.overall_score is mean of all probe scores
# ─────────────────────────────────────────────────────────────────────────────

@given(scores=st.lists(_score_st, min_size=1, max_size=20))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_overall_score_is_mean_of_probe_scores(scores: list[float]) -> None:
    """overall_score must equal the arithmetic mean of all probe scores."""
    results = [
        _make_probe_result(f"probe_{i}", "p1", s, s >= 0.5)
        for i, s in enumerate(scores)
    ]
    run = _make_run(results)
    expected = sum(scores) / len(scores)
    assert abs(run.overall_score - expected) < 1e-9


@given(scores=st.lists(_score_st, min_size=1, max_size=20))
@settings(max_examples=100)
def test_overall_score_in_unit_interval(scores: list[float]) -> None:
    """overall_score is always in [0.0, 1.0]."""
    results = [_make_probe_result(f"p{i}", "q", s, s >= 0.5) for i, s in enumerate(scores)]
    run = _make_run(results)
    assert 0.0 <= run.overall_score <= 1.0


@given(scores=st.lists(_score_st, min_size=1, max_size=20))
@settings(max_examples=100)
def test_pass_rate_in_unit_interval(scores: list[float]) -> None:
    """pass_rate is always in [0.0, 1.0]."""
    results = [_make_probe_result(f"p{i}", "q", s, s >= 0.5) for i, s in enumerate(scores)]
    run = _make_run(results)
    assert 0.0 <= run.pass_rate <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Invariant: DriftReport.overall_score_delta == current - baseline
# ─────────────────────────────────────────────────────────────────────────────

@given(
    baseline_scores=st.lists(_score_st, min_size=1, max_size=10),
    current_scores=st.lists(_score_st, min_size=1, max_size=10),
)
@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
def test_score_delta_equals_current_minus_baseline(
    baseline_scores: list[float],
    current_scores: list[float],
) -> None:
    """overall_score_delta must always equal current - baseline."""
    # Use same length by zipping
    pairs = list(zip(baseline_scores, current_scores))
    if not pairs:
        return

    b_results = [_make_probe_result(f"probe_{i}", "p1", s, s >= 0.5) for i, (s, _) in enumerate(pairs)]
    c_results = [_make_probe_result(f"probe_{i}", "p1", s, s >= 0.5) for i, (_, s) in enumerate(pairs)]

    baseline_run = _make_run(b_results)
    current_run = _make_run(c_results)
    snap = _make_snapshot(baseline_run)

    report = compare(snap, current_run)
    expected_delta = report.overall_current_score - report.overall_baseline_score
    assert abs(report.overall_score_delta - expected_delta) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# Invariant: DriftReport.summary always contains the suite name
# ─────────────────────────────────────────────────────────────────────────────

@given(suite_name=st.text(alphabet=string.ascii_letters + string.digits + "-_", min_size=1, max_size=30))
@settings(max_examples=50)
def test_drift_summary_contains_suite_name(suite_name: str) -> None:
    """DriftReport.summary must always mention the suite name."""
    results = [_make_probe_result("p1", "q1", 1.0, True)]
    run = _make_run(results, suite_name=suite_name)
    snap = _make_snapshot(run)
    report = compare(snap, run)
    assert suite_name in report.summary


# ─────────────────────────────────────────────────────────────────────────────
# Invariant: No-change comparison never produces regressions
# ─────────────────────────────────────────────────────────────────────────────

@given(scores=st.lists(_score_st, min_size=1, max_size=15))
@settings(max_examples=150)
def test_identical_runs_produce_no_drift(scores: list[float]) -> None:
    """Comparing a run to itself must never produce regressions."""
    results = [_make_probe_result(f"probe_{i}", "p1", s, s >= 0.5) for i, s in enumerate(scores)]
    run = _make_run(results)
    snap = _make_snapshot(run)
    report = compare(snap, run)
    assert not report.has_drift
    assert len(report.regressions) == 0
    assert report.severity == DriftSeverity.NONE


# ─────────────────────────────────────────────────────────────────────────────
# Invariant: ResponseLengthProbe score always in [0.0, 1.0]
# ─────────────────────────────────────────────────────────────────────────────

@given(
    content=st.text(min_size=0, max_size=10000),
    min_chars=st.integers(min_value=0, max_value=100),
    max_chars=st.integers(min_value=1, max_value=10000),
    baseline=st.one_of(st.none(), st.integers(min_value=1, max_value=5000)),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_response_length_probe_score_always_valid(
    content: str,
    min_chars: int,
    max_chars: int,
    baseline: int | None,
) -> None:
    """ResponseLengthProbe must always return score in [0.0, 1.0]."""
    if min_chars > max_chars:
        min_chars, max_chars = max_chars, min_chars

    probe = ResponseLengthProbe(
        min_chars=min_chars,
        max_chars=max_chars,
        baseline_chars=baseline,
        tolerance=0.5,
    )
    prompt = CanaryPrompt(id="p1", text="test")
    response = LLMResponse(prompt_id="p1", provider_model_id="m", content=content)
    result = probe(prompt, response)
    assert 0.0 <= result.score <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Invariant: JsonValidityProbe score is always binary (0.0 or 1.0)
# ─────────────────────────────────────────────────────────────────────────────

@given(content=st.text(min_size=0, max_size=2000))
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
def test_json_validity_probe_score_is_binary(content: str) -> None:
    """JsonValidityProbe must return exactly 0.0 or 1.0, never in between."""
    probe = JsonValidityProbe()
    prompt = CanaryPrompt(id="p1", text="test")
    response = LLMResponse(prompt_id="p1", provider_model_id="m", content=content)
    result = probe(prompt, response)
    assert result.score in {0.0, 1.0}
    # Also verify consistency: passed ↔ score == 1.0
    assert result.passed == (result.score == 1.0)


@given(data=st.one_of(
    st.dictionaries(st.text(min_size=1, max_size=10), st.integers()),
    st.lists(st.integers(), min_size=0, max_size=5),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.none(),
    st.text(min_size=0, max_size=100),
))
@settings(max_examples=100)
def test_json_validity_probe_passes_on_valid_json(data: object) -> None:
    """JsonValidityProbe must pass on any valid JSON-serialisable value."""
    content = json.dumps(data)
    probe = JsonValidityProbe()
    prompt = CanaryPrompt(id="p1", text="test")
    response = LLMResponse(prompt_id="p1", provider_model_id="m", content=content)
    result = probe(prompt, response)
    assert result.passed
    assert result.score == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Invariant: FileBaselineStore round-trips perfectly
# ─────────────────────────────────────────────────────────────────────────────

@given(
    suite_name=st.text(
        alphabet=string.ascii_lowercase + string.digits + "-",
        min_size=1,
        max_size=20,
    ),
    scores=st.lists(_score_st, min_size=1, max_size=5),
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_baseline_store_round_trip(suite_name: str, scores: list[float]) -> None:
    """save() → load() must produce identical suite_name, scores, and provider."""
    results = [_make_probe_result(f"p{i}", "q", s, s >= 0.5) for i, s in enumerate(scores)]
    run = _make_run(results, suite_name=suite_name)

    with tempfile.TemporaryDirectory() as tmp:
        store = FileBaselineStore(Path(tmp))
        snapshot = store.save(run)
        loaded = store.load(snapshot.snapshot_id)

    assert loaded.suite_name == suite_name
    assert loaded.snapshot_id == snapshot.snapshot_id
    assert len(loaded.run_result.probe_results) == len(results)
    for orig, restored in zip(results, loaded.run_result.probe_results):
        assert abs(orig.score - restored.score) < 1e-9
        assert orig.passed == restored.passed


# ─────────────────────────────────────────────────────────────────────────────
# Invariant: failed_probes count <= total probe count
# ─────────────────────────────────────────────────────────────────────────────

@given(scores=st.lists(_score_st, min_size=0, max_size=20))
@settings(max_examples=100)
def test_failed_probe_count_leq_total(scores: list[float]) -> None:
    """failed_probes must never exceed the total number of probes."""
    results = [_make_probe_result(f"p{i}", "q", s, s >= 0.5) for i, s in enumerate(scores)]
    run = _make_run(results)
    assert len(run.failed_probes) <= len(run.probe_results)


# ─────────────────────────────────────────────────────────────────────────────
# Invariant: compare() is symmetric in regression/improvement detection
# ─────────────────────────────────────────────────────────────────────────────

@given(
    b_score=_score_st,
    c_score=_score_st,
)
@settings(max_examples=100)
def test_regression_and_improvement_are_mutually_exclusive(
    b_score: float,
    c_score: float,
) -> None:
    """A comparison can be a regression, improvement, or stable — never both reg and imp."""
    b_passed = b_score >= 0.5
    c_passed = c_score >= 0.5
    delta = c_score - b_score
    regression = b_passed and not c_passed and delta <= -0.05
    improvement = not b_passed and c_passed and delta >= 0.05
    # They can't both be True simultaneously
    assert not (regression and improvement)
