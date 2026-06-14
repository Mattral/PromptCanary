"""
tests/unit/probes/test_reasoning_safety_probes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests for Reasoning Style and Safety probes.
"""

from __future__ import annotations

import pytest

from promptcanary.core.models import CanaryPrompt, LLMResponse
from promptcanary.core.probes.reasoning import (
    ConfidenceLanguageProbe,
    DirectAnswerProbe,
    StepByStepProbe,
    VerbosityProbe,
)
from promptcanary.core.probes.safety import (
    FactualConsistencyProbe,
    RefusalProbe,
    SafetyLanguageProbe,
    SentimentProbe,
)


def make_prompt(prompt_id: str = "p1", text: str = "test") -> CanaryPrompt:
    return CanaryPrompt(id=prompt_id, text=text)


def make_response(content: str, prompt_id: str = "p1") -> LLMResponse:
    return LLMResponse(prompt_id=prompt_id, provider_model_id="test/m", content=content)


# ─────────────────────────────────────────────────────────────────────────────
# StepByStepProbe
# ─────────────────────────────────────────────────────────────────────────────


class TestStepByStepProbe:
    def test_detects_numbered_steps(self) -> None:
        probe = StepByStepProbe(expect_steps=True, min_step_count=2)
        content = "1. First, do this.\n2. Second, do that.\n3. Finally, done."
        r = probe.evaluate(make_prompt(), make_response(content))
        assert r.passed

    def test_detects_explicit_step_labels(self) -> None:
        probe = StepByStepProbe(expect_steps=True, min_step_count=2)
        content = "Step 1: Open file. Step 2: Edit content. Step 3: Save."
        r = probe.evaluate(make_prompt(), make_response(content))
        assert r.passed

    def test_fails_when_steps_expected_but_absent(self) -> None:
        probe = StepByStepProbe(expect_steps=True, min_step_count=3)
        content = "Just a direct answer with no steps."
        r = probe.evaluate(make_prompt(), make_response(content))
        assert not r.passed

    def test_passes_when_direct_expected_and_direct_given(self) -> None:
        probe = StepByStepProbe(expect_steps=False)
        content = "Paris is the capital of France."
        r = probe.evaluate(make_prompt(), make_response(content))
        assert r.passed

    def test_fails_when_direct_expected_but_steps_given(self) -> None:
        probe = StepByStepProbe(expect_steps=False)
        content = "First, consider the question. Second, formulate an answer. Third, respond."
        r = probe.evaluate(make_prompt(), make_response(content))
        assert not r.passed

    def test_score_proportional_to_step_count(self) -> None:
        probe = StepByStepProbe(expect_steps=True, min_step_count=4)
        content = "Step 1: A. Step 2: B."  # only 2 steps, need 4
        r = probe.evaluate(make_prompt(), make_response(content))
        # Score should be fractional
        assert 0.0 < r.score < 1.0


# ─────────────────────────────────────────────────────────────────────────────
# VerbosityProbe
# ─────────────────────────────────────────────────────────────────────────────


class TestVerbosityProbe:
    def test_within_tolerance(self) -> None:
        probe = VerbosityProbe(expected_words=100, tolerance=0.5)
        # 120 words = 20% above, within 50% tolerance
        content = " ".join(["word"] * 120)
        r = probe.evaluate(make_prompt(), make_response(content))
        assert r.passed

    def test_exceeds_tolerance(self) -> None:
        probe = VerbosityProbe(expected_words=100, tolerance=0.2)
        content = " ".join(["word"] * 200)  # 100% above, > 20% tolerance
        r = probe.evaluate(make_prompt(), make_response(content))
        assert not r.passed

    def test_below_min_words(self) -> None:
        probe = VerbosityProbe(min_words=50)
        r = probe.evaluate(make_prompt(), make_response("Only five words here."))
        assert not r.passed

    def test_above_max_words(self) -> None:
        probe = VerbosityProbe(max_words=5)
        r = probe.evaluate(make_prompt(), make_response("This is more than five words total."))
        assert not r.passed

    def test_no_config_always_passes(self) -> None:
        probe = VerbosityProbe()
        r = probe.evaluate(make_prompt(), make_response("Any content at all."))
        assert r.passed


# ─────────────────────────────────────────────────────────────────────────────
# ConfidenceLanguageProbe
# ─────────────────────────────────────────────────────────────────────────────


class TestConfidenceLanguageProbe:
    def test_detects_hedging_when_expected(self) -> None:
        probe = ConfidenceLanguageProbe(expect_hedging=True, threshold=0.01)
        content = "I think this might be the answer, but I'm not entirely sure."
        r = probe.evaluate(make_prompt(), make_response(content))
        assert r.passed

    def test_no_hedging_when_confident_expected(self) -> None:
        probe = ConfidenceLanguageProbe(expect_hedging=False)
        content = "Paris is the capital of France. The population is 2.1 million."
        r = probe.evaluate(make_prompt(), make_response(content))
        assert r.passed

    def test_unexpected_hedging_detected(self) -> None:
        probe = ConfidenceLanguageProbe(expect_hedging=False, threshold=0.01)
        content = "I think perhaps this might possibly be the answer."
        r = probe.evaluate(make_prompt(), make_response(content))
        assert not r.passed


# ─────────────────────────────────────────────────────────────────────────────
# DirectAnswerProbe
# ─────────────────────────────────────────────────────────────────────────────


class TestDirectAnswerProbe:
    def test_passes_direct_response(self) -> None:
        probe = DirectAnswerProbe(expect_direct=True)
        r = probe.evaluate(make_prompt(), make_response("Paris is the capital of France."))
        assert r.passed
        assert r.score == 1.0

    def test_detects_preamble_sure(self) -> None:
        probe = DirectAnswerProbe(expect_direct=True)
        r = probe.evaluate(make_prompt(), make_response("Sure! I'd be happy to help."))
        assert not r.passed

    def test_detects_preamble_great_question(self) -> None:
        probe = DirectAnswerProbe(expect_direct=True)
        r = probe.evaluate(make_prompt(), make_response("Great question! The answer is..."))
        assert not r.passed

    def test_detects_ai_preamble(self) -> None:
        probe = DirectAnswerProbe(expect_direct=True)
        r = probe.evaluate(make_prompt(), make_response("As an AI, I can tell you..."))
        assert not r.passed

    def test_preamble_expected_passes(self) -> None:
        probe = DirectAnswerProbe(expect_direct=False)
        r = probe.evaluate(make_prompt(), make_response("Certainly! Here is the answer."))
        assert r.passed


# ─────────────────────────────────────────────────────────────────────────────
# RefusalProbe
# ─────────────────────────────────────────────────────────────────────────────


class TestRefusalProbe:
    def test_no_refusal_when_not_expected(self) -> None:
        probe = RefusalProbe(expect_refusal=False)
        r = probe.evaluate(make_prompt(), make_response("Sure, here's how to do it..."))
        assert r.passed

    def test_refusal_detected(self) -> None:
        probe = RefusalProbe(expect_refusal=False)
        r = probe.evaluate(
            make_prompt(), make_response("I'm sorry, I can't help with that request.")
        )
        assert not r.passed

    def test_refusal_expected_and_present(self) -> None:
        probe = RefusalProbe(expect_refusal=True)
        r = probe.evaluate(
            make_prompt(),
            make_response("I cannot assist with this. It goes against my guidelines."),
        )
        assert r.passed

    def test_refusal_expected_but_absent(self) -> None:
        probe = RefusalProbe(expect_refusal=True)
        r = probe.evaluate(make_prompt(), make_response("Here is the answer you requested."))
        assert not r.passed

    def test_score_is_binary(self) -> None:
        probe = RefusalProbe(expect_refusal=False)
        r_pass = probe.evaluate(make_prompt(), make_response("Here is the info."))
        r_fail = probe.evaluate(
            make_prompt(), make_response("I'm unable to provide that information.")
        )
        assert r_pass.score == 1.0
        assert r_fail.score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# SafetyLanguageProbe
# ─────────────────────────────────────────────────────────────────────────────


class TestSafetyLanguageProbe:
    def test_no_disclaimer_when_not_expected(self) -> None:
        probe = SafetyLanguageProbe(expect_safety_language=False)
        r = probe.evaluate(make_prompt(), make_response("Here is the information you need."))
        assert r.passed

    def test_unexpected_disclaimer_detected(self) -> None:
        probe = SafetyLanguageProbe(expect_safety_language=False)
        r = probe.evaluate(
            make_prompt(),
            make_response("Please consult a professional before acting on this advice."),
        )
        assert not r.passed

    def test_expected_disclaimer_present(self) -> None:
        probe = SafetyLanguageProbe(expect_safety_language=True)
        r = probe.evaluate(
            make_prompt(),
            make_response("This is for informational purposes only. Please consult a doctor."),
        )
        assert r.passed


# ─────────────────────────────────────────────────────────────────────────────
# FactualConsistencyProbe
# ─────────────────────────────────────────────────────────────────────────────


class TestFactualConsistencyProbe:
    def test_contains_match(self) -> None:
        probe = FactualConsistencyProbe("Paris", match_mode="contains")
        r = probe.evaluate(make_prompt(), make_response("The capital of France is Paris."))
        assert r.passed

    def test_contains_miss(self) -> None:
        probe = FactualConsistencyProbe("Paris", match_mode="contains")
        r = probe.evaluate(make_prompt(), make_response("The capital of France is a big city."))
        assert not r.passed

    def test_exact_match(self) -> None:
        probe = FactualConsistencyProbe("Paris", match_mode="exact")
        r = probe.evaluate(make_prompt(), make_response("Paris"))
        assert r.passed

    def test_exact_miss(self) -> None:
        probe = FactualConsistencyProbe("Paris", match_mode="exact")
        r = probe.evaluate(make_prompt(), make_response("The capital is Paris."))
        assert not r.passed

    def test_startswith_match(self) -> None:
        probe = FactualConsistencyProbe("Paris", match_mode="startswith")
        r = probe.evaluate(make_prompt(), make_response("Paris is the capital of France."))
        assert r.passed

    def test_case_insensitive_by_default(self) -> None:
        probe = FactualConsistencyProbe("paris")
        r = probe.evaluate(make_prompt(), make_response("The capital is PARIS."))
        assert r.passed

    def test_invalid_match_mode(self) -> None:
        with pytest.raises(ValueError, match="match_mode"):
            FactualConsistencyProbe("Paris", match_mode="fuzzy")

    def test_score_binary(self) -> None:
        probe = FactualConsistencyProbe("Paris")
        r_pass = probe.evaluate(make_prompt(), make_response("Paris is great."))
        r_fail = probe.evaluate(make_prompt(), make_response("Berlin is great."))
        assert r_pass.score == 1.0
        assert r_fail.score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# SentimentProbe
# ─────────────────────────────────────────────────────────────────────────────


class TestSentimentProbe:
    def test_no_expectation_always_passes(self) -> None:
        probe = SentimentProbe(expect_positive=None)
        r = probe.evaluate(make_prompt(), make_response("This is a terrible outcome."))
        assert r.passed

    def test_positive_detected_when_expected(self) -> None:
        probe = SentimentProbe(expect_positive=True, threshold=0.01)
        content = "This is an excellent and wonderful outcome. Fantastic results!"
        r = probe.evaluate(make_prompt(), make_response(content))
        assert r.passed

    def test_negative_when_positive_expected(self) -> None:
        probe = SentimentProbe(expect_positive=True, threshold=0.02)
        content = "This is terrible and bad and wrong and awful."
        r = probe.evaluate(make_prompt(), make_response(content))
        assert not r.passed
