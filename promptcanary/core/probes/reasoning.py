"""
promptcanary.core.probes.reasoning
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Reasoning Style probes — detect when a model silently changes how it reasons.

Probes:
  - StepByStepProbe       — Does the model show explicit reasoning steps?
  - VerbosityProbe        — Has the verbosity (word count) drifted?
  - ConfidenceLanguageProbe — Does the model use hedging language as expected?
  - DirectAnswerProbe     — Does the model give a direct answer (vs. preamble)?
  - NumericalReasoningProbe — Checks for consistent numerical format in answers.
"""

from __future__ import annotations

import re
from typing import Any

from promptcanary.core.models import (
    CanaryPrompt,
    LLMResponse,
    ProbeCategory,
    ProbeResult,
)
from promptcanary.core.probes.base import BaseProbe


class StepByStepProbe(BaseProbe):
    """Detects whether a model produces explicit step-by-step reasoning.

    Step-by-step indicators include numbered steps, "Step N:", "First/Second/Finally",
    chain-of-thought markers, etc.

    Args:
        expect_steps:      True = expect reasoning steps; False = expect direct answer.
        min_step_count:    Minimum number of detected step indicators.

    Score: 1.0 when expectation matches; partial for weak signals.
    """

    probe_id = "step_by_step"
    name = "Step-by-Step Reasoning"
    category = ProbeCategory.REASONING
    description = "Detects whether the model produces explicit chain-of-thought steps."

    # Patterns indicating step-by-step reasoning
    _STEP_PATTERNS = [  # noqa: RUF012
        r"\bStep\s+\d+",
        r"^\d+\.\s+\w",  # "1. Do something"
        r"\bFirst(?:ly)?[,:]",
        r"\bSecond(?:ly)?[,:]",
        r"\bThird(?:ly)?[,:]",
        r"\bFinally[,:]",
        r"\bNext[,:]",
        r"\bThen[,:]",
        r"\bLet(?:'s| us) (start|begin|think|consider)",
        r"\bTo (start|begin|solve)",
        r"<thinking>",  # Claude-style thinking tags
        r"\blet me (think|work|break)",
    ]

    def __init__(self, expect_steps: bool = True, min_step_count: int = 2) -> None:
        self.expect_steps = expect_steps
        self.min_step_count = min_step_count

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        content = response.content
        step_count = sum(
            len(re.findall(p, content, re.IGNORECASE | re.MULTILINE)) for p in self._STEP_PATTERNS
        )
        has_steps = step_count >= self.min_step_count

        if self.expect_steps:
            passed = has_steps
            score = min(1.0, step_count / max(self.min_step_count, 1))
            details = (
                f"Found {step_count} step indicator(s) (min: {self.min_step_count})."
                if has_steps
                else f"Expected reasoning steps but found only {step_count} indicator(s)."
            )
        else:
            passed = not has_steps
            score = 1.0 if not has_steps else max(0.0, 1.0 - (step_count / 5.0))
            details = (
                "Response is direct (no excess step-by-step markers)."
                if not has_steps
                else f"Expected direct answer but found {step_count} step indicator(s)."
            )

        return self._make_result(
            prompt.id,
            passed=passed,
            score=score,
            details=details,
            metadata={"step_indicator_count": step_count, "expect_steps": self.expect_steps},
        )


class VerbosityProbe(BaseProbe):
    """Checks whether response verbosity (word count) has drifted.

    Args:
        expected_words:  Approximate expected word count.
        tolerance:       Fractional tolerance (default 0.5 = ±50%).
        min_words:       Hard lower bound on word count.
        max_words:       Hard upper bound on word count.

    Score: 1.0 when within tolerance, degrades linearly outside it.
    """

    probe_id = "verbosity"
    name = "Response Verbosity"
    category = ProbeCategory.REASONING
    description = "Detects significant changes in response word count."

    def __init__(
        self,
        expected_words: int | None = None,
        tolerance: float = 0.5,
        min_words: int = 1,
        max_words: int | None = None,
    ) -> None:
        self.expected_words = expected_words
        self.tolerance = tolerance
        self.min_words = min_words
        self.max_words = max_words

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        word_count = len(response.content.split())
        meta: dict[str, Any] = {"word_count": word_count}

        # Hard bounds
        if word_count < self.min_words:
            return self._make_result(
                prompt.id,
                passed=False,
                score=0.0,
                details=f"Too few words: {word_count} (min: {self.min_words}).",
                metadata=meta,
            )
        if self.max_words and word_count > self.max_words:
            return self._make_result(
                prompt.id,
                passed=False,
                score=0.0,
                details=f"Too many words: {word_count} (max: {self.max_words}).",
                metadata=meta,
            )

        if self.expected_words:
            ratio = word_count / self.expected_words
            deviation = abs(ratio - 1.0)
            score = max(0.0, 1.0 - max(0.0, deviation - self.tolerance) / (1 - self.tolerance))
            passed = deviation <= self.tolerance
            meta["expected_words"] = self.expected_words
            meta["ratio"] = round(ratio, 3)
            return self._make_result(
                prompt.id,
                passed=passed,
                score=score,
                details=(
                    f"{word_count} words vs expected ~{self.expected_words} "
                    f"({ratio:.1%} of baseline, tolerance ±{self.tolerance:.0%})."
                ),
                metadata=meta,
            )

        return self._make_result(
            prompt.id,
            passed=True,
            score=1.0,
            details=f"Word count: {word_count}.",
            metadata=meta,
        )


class ConfidenceLanguageProbe(BaseProbe):
    """Detects how much hedging/confidence language the model uses.

    Args:
        expect_hedging:    True = expect uncertain/hedging language;
                           False = expect confident/direct language.
        threshold:         Hedge-word rate above which hedging is detected.

    Score: Reflects whether the observed hedging matches expectation.
    """

    probe_id = "confidence_language"
    name = "Confidence Language"
    category = ProbeCategory.REASONING
    description = "Detects changes in how confidently or tentatively the model responds."

    _HEDGE_WORDS = [  # noqa: RUF012
        r"\bI think\b",
        r"\bI believe\b",
        r"\bI'm not sure\b",
        r"\bperhaps\b",
        r"\bmaybe\b",
        r"\bmight\b",
        r"\bcould be\b",
        r"\bpossibly\b",
        r"\bprobably\b",
        r"\blikely\b",
        r"\bseems?\b",
        r"\bappears?\b",
        r"\bsuggest[s]?\b",
        r"\bit's possible\b",
        r"\buncertain\b",
        r"\bunsure\b",
        r"\bnot entirely\b",
        r"\btend[s]? to\b",
        r"\bgenerally\b",
    ]
    _CONFIDENCE_WORDS = [  # noqa: RUF012
        r"\bcertainly\b",
        r"\bdefinitely\b",
        r"\babsolutely\b",
        r"\bwithout doubt\b",
        r"\bclearly\b",
        r"\bobviously\b",
        r"\bis\b",
        r"\bare\b",  # weak signal but volume helps
    ]

    def __init__(self, expect_hedging: bool = False, threshold: float = 0.03) -> None:
        self.expect_hedging = expect_hedging
        self.threshold = threshold

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        content = response.content
        word_count = max(len(content.split()), 1)

        hedge_matches = sum(len(re.findall(p, content, re.IGNORECASE)) for p in self._HEDGE_WORDS)
        hedge_rate = hedge_matches / word_count

        has_hedging = hedge_rate >= self.threshold

        if self.expect_hedging:
            passed = has_hedging
            score = min(1.0, hedge_rate / self.threshold)
            details = (
                f"Hedging detected (rate: {hedge_rate:.3f}, {hedge_matches} markers)."
                if has_hedging
                else f"Expected hedging but rate is low ({hedge_rate:.3f})."
            )
        else:
            passed = not has_hedging
            score = max(0.0, 1.0 - (hedge_rate / max(self.threshold * 2, 0.01)))
            details = (
                f"Response sounds confident (hedge rate: {hedge_rate:.3f})."
                if not has_hedging
                else f"Unexpected hedging detected (rate: {hedge_rate:.3f}, {hedge_matches} markers)."
            )

        return self._make_result(
            prompt.id,
            passed=passed,
            score=score,
            details=details,
            metadata={"hedge_rate": round(hedge_rate, 4), "hedge_matches": hedge_matches},
        )


class DirectAnswerProbe(BaseProbe):
    """Checks whether the model starts with the answer directly vs. with preamble.

    Preamble patterns: "Sure!", "Of course!", "Great question!", "Certainly!",
    "I'd be happy to...", "As an AI...", etc.

    Args:
        expect_direct:   True = expect direct answer, False = allow preamble.
        max_preamble_chars: Characters before which the 'real' answer should start.

    Score: 1.0 if direct, partial or 0.0 if preamble detected.
    """

    probe_id = "direct_answer"
    name = "Direct Answer (No Preamble)"
    category = ProbeCategory.REASONING
    description = "Detects unnecessary preamble before the actual answer."

    _PREAMBLE_PATTERNS = [  # noqa: RUF012
        r"^Sure[!,]",
        r"^Of course[!,]",
        r"^Certainly[!,]",
        r"^Great question[!,]",
        r"^Absolutely[!,]",
        r"^I'd be happy to",
        r"^I would be happy to",
        r"^As an AI",
        r"^As a language model",
        r"^I'm glad you asked",
        r"^Thanks? for (asking|your question)",
        r"^Happy to help",
    ]

    def __init__(self, expect_direct: bool = True, max_preamble_chars: int = 80) -> None:
        self.expect_direct = expect_direct
        self.max_preamble_chars = max_preamble_chars

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        opening = response.content[: self.max_preamble_chars].strip()
        preamble_found = any(re.search(p, opening, re.IGNORECASE) for p in self._PREAMBLE_PATTERNS)

        if self.expect_direct:
            passed = not preamble_found
            score = 0.0 if preamble_found else 1.0
            details = (
                "Response starts directly without preamble."
                if not preamble_found
                else f"Preamble detected in first {self.max_preamble_chars} chars: {opening!r}"
            )
        else:
            passed = preamble_found
            score = 1.0 if preamble_found else 0.5
            details = (
                "Preamble present as expected."
                if preamble_found
                else "Expected preamble but response is direct."
            )

        return self._make_result(
            prompt.id,
            passed=passed,
            score=score,
            details=details,
            metadata={"opening_preview": opening[:100], "preamble_found": preamble_found},
        )
