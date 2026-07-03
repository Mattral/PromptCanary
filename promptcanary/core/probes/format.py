"""
promptcanary.core.probes.format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Format & Structure probes — detect changes in how an LLM formats its output.

Probes:
  - JsonValidityProbe      — Is the response valid JSON?
  - JsonSchemaProbe        — Does the JSON match required keys?
  - JsonKeyOrderProbe      — Are top-level JSON keys in the expected order?
  - ResponseLengthProbe    — Has response length drifted significantly?
  - MarkdownHeaderProbe    — Are expected markdown headers present?
  - BulletListProbe        — Does the response use bullet lists as expected?
"""

from __future__ import annotations

import json
import re
from typing import Any

from promptcanary.core.models import (
    CanaryPrompt,
    LLMResponse,
    ProbeCategory,
    ProbeResult,
)
from promptcanary.core.probes.base import BaseProbe


class JsonValidityProbe(BaseProbe):
    """Checks whether the model's entire response is valid JSON.

    Score: 1.0 if valid JSON, 0.0 otherwise.
    """

    probe_id = "json_validity"
    name = "JSON Validity"
    category = ProbeCategory.FORMAT
    description = "Verifies the response can be parsed as valid JSON."

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        content = response.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            json.loads(content)
            return self._make_result(
                prompt.id,
                passed=True,
                score=1.0,
                details="Response is valid JSON.",
            )
        except json.JSONDecodeError as e:
            return self._make_result(
                prompt.id,
                passed=False,
                score=0.0,
                details=f"JSON parse error at position {e.pos}: {e.msg}",
                metadata={"error": str(e), "raw_content_preview": content[:200]},
            )


class JsonSchemaProbe(BaseProbe):
    """Checks that a JSON response contains required and optional keys.

    Args:
        required_keys:  Keys that MUST be present (fail if any missing).
        forbidden_keys: Keys that MUST NOT be present.
        score_per_key:  Whether to give partial credit for partial matches.

    Score: Fraction of required_keys present (0.0-1.0).
    """

    probe_id = "json_schema"
    name = "JSON Schema"
    category = ProbeCategory.FORMAT
    description = "Checks that JSON response contains expected keys."

    def __init__(
        self,
        required_keys: list[str],
        forbidden_keys: list[str] | None = None,
        *,
        score_per_key: bool = True,
    ) -> None:
        self.required_keys = required_keys
        self.forbidden_keys = forbidden_keys or []
        self.score_per_key = score_per_key

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data: dict[str, Any] = json.loads(content)
        except json.JSONDecodeError:
            return self._make_result(
                prompt.id,
                passed=False,
                score=0.0,
                details="Response is not valid JSON; cannot check schema.",
            )

        if not isinstance(data, dict):
            return self._make_result(
                prompt.id,
                passed=False,
                score=0.0,
                details=f"Expected JSON object, got {type(data).__name__}.",
            )

        present = set(data.keys())
        required = set(self.required_keys)
        missing = required - present
        forbidden_found = set(self.forbidden_keys) & present

        if self.score_per_key:
            score = (len(required) - len(missing)) / max(len(required), 1)
        else:
            score = 1.0 if not missing else 0.0

        # Penalise forbidden keys
        if forbidden_found:
            score *= 0.5

        passed = not missing and not forbidden_found
        details_parts = []
        if missing:
            details_parts.append(f"Missing keys: {sorted(missing)}")
        if forbidden_found:
            details_parts.append(f"Forbidden keys present: {sorted(forbidden_found)}")
        if passed:
            details_parts.append("All required keys present.")

        return self._make_result(
            prompt.id,
            passed=passed,
            score=score,
            details=" | ".join(details_parts),
            metadata={
                "missing_keys": sorted(missing),
                "forbidden_found": sorted(forbidden_found),
                "present_keys": sorted(present),
            },
        )


class JsonKeyOrderProbe(BaseProbe):
    """Checks that top-level JSON keys appear in the expected order.

    Useful for detecting format drift where models reorder fields.

    Args:
        expected_order: Ordered list of keys.

    Score: Fraction of keys in the correct relative order.
    """

    probe_id = "json_key_order"
    name = "JSON Key Order"
    category = ProbeCategory.FORMAT
    description = "Verifies top-level JSON keys appear in the expected order."

    def __init__(self, expected_order: list[str]) -> None:
        self.expected_order = expected_order

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data: dict[str, Any] = json.loads(content)
        except json.JSONDecodeError:
            return self._make_result(
                prompt.id,
                passed=False,
                score=0.0,
                details="Response is not valid JSON.",
            )

        actual_keys = list(data.keys())
        filtered_expected = [k for k in self.expected_order if k in actual_keys]
        filtered_actual = [k for k in actual_keys if k in self.expected_order]

        if not filtered_expected:
            return self._make_result(
                prompt.id,
                passed=True,
                score=1.0,
                details="No expected keys found in response; order check skipped.",
            )

        # Longest common subsequence to measure order preservation
        score = self._lcs_score(filtered_expected, filtered_actual)
        passed = score >= 0.9  # Allow minor re-ordering

        return self._make_result(
            prompt.id,
            passed=passed,
            score=score,
            details=(
                f"Expected order: {filtered_expected}. "
                f"Actual order: {filtered_actual}. "
                f"Order score: {score:.2f}."
            ),
            metadata={
                "expected_order": filtered_expected,
                "actual_order": filtered_actual,
            },
        )

    @staticmethod
    def _lcs_score(expected: list[str], actual: list[str]) -> float:
        """Compute LCS length / max length as a similarity score."""
        m, n = len(expected), len(actual)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if expected[i - 1] == actual[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        lcs_len = dp[m][n]
        return lcs_len / max(m, n, 1)


class ResponseLengthProbe(BaseProbe):
    """Checks that response length has not drifted outside acceptable bounds.

    Args:
        min_chars:     Minimum acceptable character count (default: 1).
        max_chars:     Maximum acceptable character count (default: no limit).
        baseline_chars: Expected baseline length. If set, triggers drift scoring.
        tolerance:     Fractional tolerance around baseline (default: 0.5 = ±50%).

    Score: 1.0 if within bounds, partial for near-misses, 0.0 for major violations.
    """

    probe_id = "response_length"
    name = "Response Length"
    category = ProbeCategory.FORMAT
    description = "Detects significant changes in response length."

    def __init__(
        self,
        min_chars: int = 1,
        max_chars: int | None = None,
        baseline_chars: int | None = None,
        tolerance: float = 0.5,
    ) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.baseline_chars = baseline_chars
        self.tolerance = tolerance

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        length = len(response.content)
        meta: dict[str, Any] = {"char_count": length}

        # Hard bounds check
        if length < self.min_chars:
            return self._make_result(
                prompt.id,
                passed=False,
                score=0.0,
                details=f"Response too short: {length} chars (min: {self.min_chars}).",
                metadata=meta,
            )
        if self.max_chars and length > self.max_chars:
            return self._make_result(
                prompt.id,
                passed=False,
                score=0.0,
                details=f"Response too long: {length} chars (max: {self.max_chars}).",
                metadata=meta,
            )

        # Drift scoring relative to baseline
        if self.baseline_chars:
            ratio = length / self.baseline_chars
            deviation = abs(ratio - 1.0)
            if deviation <= self.tolerance:
                score = 1.0 - (deviation / self.tolerance) * 0.2  # slight penalty for drift
            else:
                score = max(0.0, 1.0 - deviation)
            passed = deviation <= self.tolerance
            meta["baseline_chars"] = self.baseline_chars
            meta["ratio_to_baseline"] = round(ratio, 3)
            return self._make_result(
                prompt.id,
                passed=passed,
                score=score,
                details=(
                    f"Length {length} chars vs baseline {self.baseline_chars} "
                    f"({ratio:.1%} of baseline, tolerance ±{self.tolerance:.0%})."
                ),
                metadata=meta,
            )

        return self._make_result(
            prompt.id,
            passed=True,
            score=1.0,
            details=f"Response length {length} chars — within bounds.",
            metadata=meta,
        )


class MarkdownHeaderProbe(BaseProbe):
    """Checks that expected markdown headers (## headings) are present.

    Args:
        expected_headers: List of header texts that must appear.
        case_sensitive:   Whether header matching is case-sensitive.

    Score: Fraction of expected headers found.
    """

    probe_id = "markdown_headers"
    name = "Markdown Headers"
    category = ProbeCategory.FORMAT
    description = "Verifies expected markdown section headers are present."

    def __init__(
        self,
        expected_headers: list[str],
        *,
        case_sensitive: bool = False,
    ) -> None:
        self.expected_headers = expected_headers
        self.case_sensitive = case_sensitive

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        content = response.content
        # Extract all markdown headers (any level)
        header_pattern = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
        found_raw = [m.group(1).strip() for m in header_pattern.finditer(content)]

        if not self.case_sensitive:
            found = [h.lower() for h in found_raw]
            expected = [h.lower() for h in self.expected_headers]
        else:
            found = found_raw
            expected = self.expected_headers

        missing = [h for h in expected if h not in found]
        score = (len(expected) - len(missing)) / max(len(expected), 1)
        passed = not missing

        return self._make_result(
            prompt.id,
            passed=passed,
            score=score,
            details=(
                f"Found {len(found_raw)} headers. "
                + (f"Missing: {missing}." if missing else "All expected headers present.")
            ),
            metadata={"found_headers": found_raw, "missing_headers": missing},
        )


class KeywordPresenceProbe(BaseProbe):
    """Checks that specific keywords are (or are not) present in the response.

    Args:
        required_keywords:  Words/phrases that MUST appear.
        forbidden_keywords: Words/phrases that MUST NOT appear.
        case_sensitive:     Default False.

    Score: 1.0 if all required present and none forbidden, else partial.
    """

    probe_id = "keyword_presence"
    name = "Keyword Presence"
    category = ProbeCategory.FORMAT
    description = "Verifies presence/absence of specific keywords in the response."

    def __init__(
        self,
        required_keywords: list[str] | None = None,
        forbidden_keywords: list[str] | None = None,
        *,
        case_sensitive: bool = False,
    ) -> None:
        self.required_keywords = required_keywords or []
        self.forbidden_keywords = forbidden_keywords or []
        self.case_sensitive = case_sensitive

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        content = response.content if self.case_sensitive else response.content.lower()

        def check(kw: str) -> bool:
            k = kw if self.case_sensitive else kw.lower()
            return k in content

        missing_required = [k for k in self.required_keywords if not check(k)]
        found_forbidden = [k for k in self.forbidden_keywords if check(k)]

        total_checks = len(self.required_keywords) + len(self.forbidden_keywords)
        violations = len(missing_required) + len(found_forbidden)
        score = 1.0 - (violations / max(total_checks, 1))
        passed = violations == 0

        details_parts = []
        if missing_required:
            details_parts.append(f"Missing keywords: {missing_required}")
        if found_forbidden:
            details_parts.append(f"Forbidden keywords found: {found_forbidden}")
        if passed:
            details_parts.append("All keyword checks passed.")

        return self._make_result(
            prompt.id,
            passed=passed,
            score=score,
            details=" | ".join(details_parts),
            metadata={
                "missing_required": missing_required,
                "found_forbidden": found_forbidden,
            },
        )


# ── Use prompt.expected_keywords as a convenience auto-probe ─────────────────


class ExpectedKeywordsProbe(BaseProbe):
    """Auto-probe that uses CanaryPrompt.expected_keywords for keyword checking.

    This means no configuration is needed — just set expected_keywords on
    the CanaryPrompt itself.
    """

    probe_id = "expected_keywords"
    name = "Expected Keywords (from prompt)"
    category = ProbeCategory.FORMAT
    description = "Checks keywords declared on the CanaryPrompt object."

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        if not prompt.expected_keywords:
            return self._make_result(
                prompt.id,
                passed=True,
                score=1.0,
                details="No expected_keywords defined on prompt — skipped.",
            )
        content = response.content.lower()
        missing = [k for k in prompt.expected_keywords if k.lower() not in content]
        score = (len(prompt.expected_keywords) - len(missing)) / len(prompt.expected_keywords)
        return self._make_result(
            prompt.id,
            passed=not missing,
            score=score,
            details=(
                f"Missing: {missing}."
                if missing
                else f"All {len(prompt.expected_keywords)} expected keywords found."
            ),
            metadata={"missing": missing},
        )
