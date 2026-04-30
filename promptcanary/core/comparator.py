"""
promptcanary.core.comparator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Baseline comparison engine.

Takes a :class:`BaselineSnapshot` (saved known-good state) and a fresh
:class:`CanaryRunResult`, and produces a fully-structured :class:`DriftReport`
that captures every change, regression, and improvement.

Design:
  - Matching is by (probe_id, prompt_id) pair — order-independent.
  - Unmatched probes (new or removed) are reported in metadata.
  - All comparison logic is pure / side-effect-free.
"""

from __future__ import annotations

from promptcanary.core.models import (
    BaselineSnapshot,
    CanaryRunResult,
    DriftReport,
    ProbeCategory,
    ProbeComparison,
    ProbeResult,
)


def compare(
    baseline: BaselineSnapshot,
    current: CanaryRunResult,
    *,
    regression_threshold: float = 0.05,
    improvement_threshold: float = 0.05,
) -> DriftReport:
    """Compare a current run against a saved baseline snapshot.

    Args:
        baseline:               Saved :class:`BaselineSnapshot`.
        current:                Fresh :class:`CanaryRunResult` from the same suite.
        regression_threshold:   Minimum score drop (Δ) to declare a regression.
        improvement_threshold:  Minimum score gain (Δ) to declare an improvement.

    Returns:
        A :class:`DriftReport` with full comparison data.

    Raises:
        ValueError: If suite names do not match (guards against comparing incompatible suites).
    """
    if baseline.suite_name != current.suite_name:
        raise ValueError(
            f"Suite name mismatch: baseline is for '{baseline.suite_name}' "
            f"but current run is for '{current.suite_name}'. "
            "Cannot compare results from different suites."
        )

    # Index baseline probe results by (probe_id, prompt_id)
    baseline_index: dict[tuple[str, str], ProbeResult] = {
        (r.probe_id, r.prompt_id): r
        for r in baseline.run_result.probe_results
    }
    current_index: dict[tuple[str, str], ProbeResult] = {
        (r.probe_id, r.prompt_id): r
        for r in current.probe_results
    }

    # All keys in both baseline and current
    all_keys = set(baseline_index) | set(current_index)
    comparisons: list[ProbeComparison] = []

    for key in sorted(all_keys, key=lambda k: (k[0], k[1])):
        probe_id, prompt_id = key
        b_result = baseline_index.get(key)
        c_result = current_index.get(key)

        if b_result is None or c_result is None:
            # One side is missing — treat missing as score 0.0 / failed
            b_score = b_result.score if b_result else 0.0
            b_passed = b_result.passed if b_result else False
            b_details = b_result.details if b_result else "Not present in baseline."
            c_score = c_result.score if c_result else 0.0
            c_passed = c_result.passed if c_result else False
            c_details = c_result.details if c_result else "Not present in current run."
            category = (b_result or c_result).category  # type: ignore[union-attr]
            probe_name = (b_result or c_result).probe_name  # type: ignore[union-attr]
        else:
            b_score, b_passed, b_details = b_result.score, b_result.passed, b_result.details
            c_score, c_passed, c_details = c_result.score, c_result.passed, c_result.details
            category = c_result.category
            probe_name = c_result.probe_name

        delta = c_score - b_score
        regression = (
            b_passed
            and not c_passed
            and delta <= -regression_threshold
        ) or (
            not b_passed
            and not c_passed
            and delta <= -regression_threshold
        )
        improvement = (
            not b_passed
            and c_passed
            and delta >= improvement_threshold
        ) or (
            b_passed
            and c_passed
            and delta >= improvement_threshold
        )

        comparisons.append(
            ProbeComparison(
                probe_id=probe_id,
                probe_name=probe_name,
                category=category,
                prompt_id=prompt_id,
                baseline_score=b_score,
                current_score=c_score,
                score_delta=delta,
                baseline_passed=b_passed,
                current_passed=c_passed,
                regression=regression,
                improvement=improvement,
                baseline_details=b_details,
                current_details=c_details,
            )
        )

    return DriftReport(
        suite_name=current.suite_name,
        provider=current.provider,
        baseline_snapshot_id=baseline.snapshot_id,
        baseline_created_at=baseline.created_at,
        current_run_id=current.run_id,
        comparisons=comparisons,
    )


def _score_to_grade(score: float) -> str:
    """Convert a 0–1 score to a letter grade string."""
    if score >= 0.95:
        return "A"
    if score >= 0.85:
        return "B"
    if score >= 0.70:
        return "C"
    if score >= 0.50:
        return "D"
    return "F"


def score_to_emoji(score: float) -> str:
    """Convert a 0–1 score to a colour-coded emoji for reports."""
    if score >= 0.95:
        return "🟢"
    if score >= 0.80:
        return "🟡"
    if score >= 0.60:
        return "🟠"
    return "🔴"
