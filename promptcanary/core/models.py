"""
promptcanary.core.models
~~~~~~~~~~~~~~~~~~~~~~~~

All domain-level Pydantic v2 models. These are the canonical data structures
that flow through the entire PromptCanary pipeline. All components speak in
terms of these types — nothing else.

Design Principles:
  - Every model is immutable by default (model_config frozen where practical).
  - Rich __repr__ for easy debugging.
  - JSON-serialisable out of the box (model_dump / model_dump_json).
  - No external I/O — pure data only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────


class ProbeCategory(str, Enum):
    """High-level category for classifying probe types."""

    FORMAT = "format"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    SAFETY = "safety"
    FACTUAL = "factual"
    CUSTOM = "custom"


class DriftSeverity(str, Enum):
    """How serious is the detected drift?"""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReportFormat(str, Enum):
    """Supported output formats for drift reports."""

    TERMINAL = "terminal"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"


# ─────────────────────────────────────────────────────────────────────────────
# Core Data Transfer Objects
# ─────────────────────────────────────────────────────────────────────────────


class ProviderConfig(BaseModel):
    """Identifies and configures an LLM provider + model endpoint."""

    model_config = ConfigDict(frozen=True)

    model_id: str = Field(
        ...,
        description="LiteLLM model string e.g. 'openai/gpt-4o', 'anthropic/claude-3-5-sonnet-20241022'.",
        examples=["openai/gpt-4o", "anthropic/claude-3-5-sonnet-20241022"],
    )
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, gt=0)
    seed: int | None = Field(
        default=42,
        description="Seed for reproducibility. Not all providers support this.",
    )
    extra_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional provider-specific parameters passed through.",
    )

    @field_validator("model_id")
    @classmethod
    def model_id_must_be_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("model_id must not be empty.")
        return v.strip()


class CanaryPrompt(BaseModel):
    """A single prompt entry in a CanarySuite, with optional metadata."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    text: str = Field(..., description="The prompt text sent to the LLM.")
    tags: list[str] = Field(default_factory=list, description="Optional user tags.")
    description: str = Field(
        default="",
        description="Human-readable note about what this prompt tests.",
    )
    system_prompt: str | None = Field(
        default=None,
        description="Optional system-level prompt override for this specific canary.",
    )
    expected_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords that should appear in a healthy response (hint for probes).",
    )

    @field_validator("text")
    @classmethod
    def text_must_be_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Prompt text must not be empty.")
        return v


class LLMResponse(BaseModel):
    """Raw response from an LLM provider, with execution metadata."""

    model_config = ConfigDict(frozen=True)

    prompt_id: str
    provider_model_id: str
    content: str = Field(..., description="The text content of the model response.")
    finish_reason: str | None = None
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProbeResult(BaseModel):
    """Result of running a single Probe against a single LLMResponse."""

    model_config = ConfigDict(frozen=True)

    probe_id: str
    probe_name: str
    category: ProbeCategory
    prompt_id: str
    passed: bool
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalised score: 1.0 = perfect, 0.0 = complete failure.",
    )
    details: str = Field(default="", description="Human-readable description of the result.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Probe-specific detail.")


class CanaryRunResult(BaseModel):
    """Aggregated results for one full run of a CanarySuite against one provider."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    suite_name: str
    provider: ProviderConfig
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    probe_results: list[ProbeResult] = Field(default_factory=list)
    llm_responses: list[LLMResponse] = Field(default_factory=list)

    # ── Derived properties ────────────────────────────────────────────────────

    @property
    def overall_score(self) -> float:
        """Mean score across all probe results. Returns 1.0 if no probes ran."""
        if not self.probe_results:
            return 1.0
        return sum(r.score for r in self.probe_results) / len(self.probe_results)

    @property
    def pass_rate(self) -> float:
        """Fraction of probes that passed. Returns 1.0 if no probes ran."""
        if not self.probe_results:
            return 1.0
        return sum(1 for r in self.probe_results if r.passed) / len(self.probe_results)

    @property
    def failed_probes(self) -> list[ProbeResult]:
        """Convenience: all probe results that did not pass."""
        return [r for r in self.probe_results if not r.passed]

    @property
    def by_category(self) -> dict[ProbeCategory, list[ProbeResult]]:
        """Group probe results by category."""
        grouped: dict[ProbeCategory, list[ProbeResult]] = {}
        for r in self.probe_results:
            grouped.setdefault(r.category, []).append(r)
        return grouped

    @property
    def duration_ms(self) -> float | None:
        """Total wall-clock duration of the run in milliseconds."""
        if self.finished_at is None:
            return None
        delta = self.finished_at - self.started_at
        return delta.total_seconds() * 1000


# ─────────────────────────────────────────────────────────────────────────────
# Baseline Snapshot
# ─────────────────────────────────────────────────────────────────────────────


class BaselineSnapshot(BaseModel):
    """A saved baseline — the "known-good" state a future run is compared against."""

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    suite_name: str
    provider: ProviderConfig
    schema_version: str = Field(
        default="0.1",
        description="Snapshot schema version, for forward-compatibility.",
    )
    run_result: CanaryRunResult


# ─────────────────────────────────────────────────────────────────────────────
# Drift Report
# ─────────────────────────────────────────────────────────────────────────────


class ProbeComparison(BaseModel):
    """Side-by-side comparison of a single probe between baseline and current run."""

    model_config = ConfigDict(frozen=True)

    probe_id: str
    probe_name: str
    category: ProbeCategory
    prompt_id: str

    baseline_score: float
    current_score: float
    score_delta: float  # current - baseline (negative = regression)

    baseline_passed: bool
    current_passed: bool

    regression: bool  # True when a previously-passing probe now fails
    improvement: bool  # True when a previously-failing probe now passes

    baseline_details: str
    current_details: str

    @property
    def absolute_delta(self) -> float:
        return abs(self.score_delta)


class DriftReport(BaseModel):
    """The authoritative, fully-structured output of a drift comparison."""

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    suite_name: str
    provider: ProviderConfig
    baseline_snapshot_id: str
    baseline_created_at: datetime
    current_run_id: str

    comparisons: list[ProbeComparison] = Field(default_factory=list)

    # ── Derived summary ───────────────────────────────────────────────────────

    @property
    def has_drift(self) -> bool:
        return bool(self.regressions)

    @property
    def regressions(self) -> list[ProbeComparison]:
        return [c for c in self.comparisons if c.regression]

    @property
    def improvements(self) -> list[ProbeComparison]:
        return [c for c in self.comparisons if c.improvement]

    @property
    def stable(self) -> list[ProbeComparison]:
        return [c for c in self.comparisons if not c.regression and not c.improvement]

    @property
    def overall_baseline_score(self) -> float:
        if not self.comparisons:
            return 1.0
        return sum(c.baseline_score for c in self.comparisons) / len(self.comparisons)

    @property
    def overall_current_score(self) -> float:
        if not self.comparisons:
            return 1.0
        return sum(c.current_score for c in self.comparisons) / len(self.comparisons)

    @property
    def overall_score_delta(self) -> float:
        return self.overall_current_score - self.overall_baseline_score

    @property
    def severity(self) -> DriftSeverity:
        """Heuristic severity rating based on regression count and magnitude."""
        if not self.has_drift:
            return DriftSeverity.NONE
        n = len(self.regressions)
        total = len(self.comparisons) or 1
        worst_delta = max(abs(c.score_delta) for c in self.regressions)
        regression_rate = n / total

        if regression_rate >= 0.5 or worst_delta >= 0.6:
            return DriftSeverity.CRITICAL
        if regression_rate >= 0.3 or worst_delta >= 0.4:
            return DriftSeverity.HIGH
        if regression_rate >= 0.15 or worst_delta >= 0.2:
            return DriftSeverity.MEDIUM
        return DriftSeverity.LOW

    @property
    def summary(self) -> str:
        """Single-sentence human-readable summary suitable for notifications."""
        if not self.has_drift:
            return (
                f"✅ No drift detected in '{self.suite_name}' "
                f"(score: {self.overall_current_score:.2%})."
            )
        return (
            f"⚠️  {self.severity.value.upper()} drift in '{self.suite_name}': "
            f"{len(self.regressions)} regression(s) detected "
            f"(score: {self.overall_baseline_score:.2%} → {self.overall_current_score:.2%}, "
            f"Δ {self.overall_score_delta:+.2%})."
        )
