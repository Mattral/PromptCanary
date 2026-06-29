"""
tests/unit/probes/test_format_probes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests for all Format & Structure probes.

Each probe class has its own test class covering:
  - Happy path (score=1.0, passed=True)
  - Failure cases (score=0.0, passed=False)
  - Edge cases and partial scores
  - Metadata correctness
"""

from __future__ import annotations

import pytest

from promptcanary.core.models import CanaryPrompt, LLMResponse, ProbeCategory
from promptcanary.core.probes.format import (
    ExpectedKeywordsProbe,
    JsonKeyOrderProbe,
    JsonSchemaProbe,
    JsonValidityProbe,
    KeywordPresenceProbe,
    MarkdownHeaderProbe,
    ResponseLengthProbe,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_prompt(prompt_id: str = "p1", text: str = "test", **kwargs) -> CanaryPrompt:
    return CanaryPrompt(id=prompt_id, text=text, **kwargs)


def make_response(content: str, prompt_id: str = "p1") -> LLMResponse:
    return LLMResponse(
        prompt_id=prompt_id,
        provider_model_id="test/model",
        content=content,
    )


# ─── JsonValidityProbe ────────────────────────────────────────────────────────

class TestJsonValidityProbe:
    probe = JsonValidityProbe()

    def test_valid_json_object(self) -> None:
        r = self.probe.evaluate(make_prompt(), make_response('{"key": "value"}'))
        assert r.passed
        assert r.score == 1.0

    def test_valid_json_array(self) -> None:
        r = self.probe.evaluate(make_prompt(), make_response('[1, 2, 3]'))
        assert r.passed

    def test_valid_json_with_code_fence(self) -> None:
        content = '```json\n{"key": "value"}\n```'
        r = self.probe.evaluate(make_prompt(), make_response(content))
        assert r.passed

    def test_invalid_json(self) -> None:
        r = self.probe.evaluate(make_prompt(), make_response("{key: value}"))
        assert not r.passed
        assert r.score == 0.0
        assert "parse error" in r.details.lower()

    def test_empty_string(self) -> None:
        r = self.probe.evaluate(make_prompt(), make_response(""))
        assert not r.passed

    def test_plain_text(self) -> None:
        r = self.probe.evaluate(make_prompt(), make_response("This is just a sentence."))
        assert not r.passed

    def test_probe_metadata(self) -> None:
        assert self.probe.probe_id == "json_validity"
        assert self.probe.category == ProbeCategory.FORMAT


# ─── JsonSchemaProbe ─────────────────────────────────────────────────────────

class TestJsonSchemaProbe:
    def test_all_required_keys_present(self) -> None:
        probe = JsonSchemaProbe(required_keys=["name", "age"])
        r = probe.evaluate(make_prompt(), make_response('{"name": "Alice", "age": 30}'))
        assert r.passed
        assert r.score == 1.0

    def test_missing_required_key(self) -> None:
        probe = JsonSchemaProbe(required_keys=["name", "age", "email"])
        r = probe.evaluate(make_prompt(), make_response('{"name": "Alice", "age": 30}'))
        assert not r.passed
        assert "email" in r.metadata["missing_keys"]
        assert r.score < 1.0

    def test_partial_score_for_partial_matches(self) -> None:
        probe = JsonSchemaProbe(required_keys=["a", "b", "c", "d"], score_per_key=True)
        r = probe.evaluate(make_prompt(), make_response('{"a": 1, "b": 2}'))
        assert abs(r.score - 0.5) < 1e-9  # 2 out of 4

    def test_forbidden_keys_detected(self) -> None:
        probe = JsonSchemaProbe(
            required_keys=["name"],
            forbidden_keys=["password", "secret"],
        )
        r = probe.evaluate(
            make_prompt(),
            make_response('{"name": "Alice", "password": "hunter2"}'),
        )
        assert not r.passed
        assert "password" in r.metadata["forbidden_found"]

    def test_invalid_json_fails_gracefully(self) -> None:
        probe = JsonSchemaProbe(required_keys=["name"])
        r = probe.evaluate(make_prompt(), make_response("not json"))
        assert not r.passed
        assert r.score == 0.0

    def test_non_dict_json_fails(self) -> None:
        probe = JsonSchemaProbe(required_keys=["name"])
        r = probe.evaluate(make_prompt(), make_response("[1, 2, 3]"))
        assert not r.passed


# ─── JsonKeyOrderProbe ────────────────────────────────────────────────────────

class TestJsonKeyOrderProbe:
    def test_correct_order(self) -> None:
        probe = JsonKeyOrderProbe(expected_order=["name", "age", "email"])
        r = probe.evaluate(
            make_prompt(),
            make_response('{"name": "Alice", "age": 30, "email": "a@b.com"}'),
        )
        assert r.passed
        assert r.score >= 0.9

    def test_wrong_order(self) -> None:
        probe = JsonKeyOrderProbe(expected_order=["name", "age", "email"])
        r = probe.evaluate(
            make_prompt(),
            make_response('{"email": "a@b.com", "age": 30, "name": "Alice"}'),
        )
        assert not r.passed
        assert r.score < 0.9

    def test_invalid_json(self) -> None:
        probe = JsonKeyOrderProbe(expected_order=["name"])
        r = probe.evaluate(make_prompt(), make_response("not json"))
        assert not r.passed


# ─── ResponseLengthProbe ─────────────────────────────────────────────────────

class TestResponseLengthProbe:
    def test_within_bounds(self) -> None:
        probe = ResponseLengthProbe(min_chars=10, max_chars=100)
        r = probe.evaluate(make_prompt(), make_response("A" * 50))
        assert r.passed
        assert r.score == 1.0

    def test_too_short(self) -> None:
        probe = ResponseLengthProbe(min_chars=100)
        r = probe.evaluate(make_prompt(), make_response("Short"))
        assert not r.passed

    def test_too_long(self) -> None:
        probe = ResponseLengthProbe(max_chars=10)
        r = probe.evaluate(make_prompt(), make_response("A" * 100))
        assert not r.passed

    def test_drift_within_tolerance(self) -> None:
        probe = ResponseLengthProbe(baseline_chars=100, tolerance=0.5)
        r = probe.evaluate(make_prompt(), make_response("A" * 130))  # 30% above
        assert r.passed

    def test_drift_exceeds_tolerance(self) -> None:
        probe = ResponseLengthProbe(baseline_chars=100, tolerance=0.3)
        r = probe.evaluate(make_prompt(), make_response("A" * 200))  # 100% above
        assert not r.passed

    def test_metadata_includes_char_count(self) -> None:
        probe = ResponseLengthProbe(min_chars=1)
        r = probe.evaluate(make_prompt(), make_response("Hello World"))
        assert r.metadata["char_count"] == 11


# ─── MarkdownHeaderProbe ─────────────────────────────────────────────────────

class TestMarkdownHeaderProbe:
    def test_all_headers_present(self) -> None:
        probe = MarkdownHeaderProbe(expected_headers=["Introduction", "Conclusion"])
        content = "## Introduction\nSome text.\n## Conclusion\nFinal words."
        r = probe.evaluate(make_prompt(), make_response(content))
        assert r.passed
        assert r.score == 1.0

    def test_case_insensitive_match(self) -> None:
        probe = MarkdownHeaderProbe(expected_headers=["Introduction"], case_sensitive=False)
        r = probe.evaluate(make_prompt(), make_response("## INTRODUCTION\nText."))
        assert r.passed

    def test_missing_header(self) -> None:
        probe = MarkdownHeaderProbe(expected_headers=["Introduction", "Conclusion"])
        r = probe.evaluate(make_prompt(), make_response("## Introduction\nOnly one header."))
        assert not r.passed
        assert r.score == 0.5

    def test_no_headers_in_response(self) -> None:
        probe = MarkdownHeaderProbe(expected_headers=["Summary"])
        r = probe.evaluate(make_prompt(), make_response("Plain text, no headers at all."))
        assert not r.passed


# ─── KeywordPresenceProbe ─────────────────────────────────────────────────────

class TestKeywordPresenceProbe:
    def test_required_keyword_found(self) -> None:
        probe = KeywordPresenceProbe(required_keywords=["Paris"])
        r = probe.evaluate(make_prompt(), make_response("The capital of France is Paris."))
        assert r.passed
        assert r.score == 1.0

    def test_required_keyword_missing(self) -> None:
        probe = KeywordPresenceProbe(required_keywords=["Paris"])
        r = probe.evaluate(make_prompt(), make_response("The capital of France is a beautiful city."))
        assert not r.passed

    def test_forbidden_keyword_present(self) -> None:
        probe = KeywordPresenceProbe(forbidden_keywords=["I cannot", "I'm sorry"])
        r = probe.evaluate(make_prompt(), make_response("I cannot help with that."))
        assert not r.passed

    def test_case_insensitive_by_default(self) -> None:
        probe = KeywordPresenceProbe(required_keywords=["PARIS"])
        r = probe.evaluate(make_prompt(), make_response("The capital is paris."))
        assert r.passed

    def test_case_sensitive_fails(self) -> None:
        probe = KeywordPresenceProbe(required_keywords=["PARIS"], case_sensitive=True)
        r = probe.evaluate(make_prompt(), make_response("The capital is paris."))
        assert not r.passed

    def test_partial_score(self) -> None:
        probe = KeywordPresenceProbe(required_keywords=["Paris", "France", "Europe"])
        r = probe.evaluate(make_prompt(), make_response("Paris is in France."))
        # 2 out of 3 required = 0.67 (no forbidden checks)
        assert abs(r.score - 2 / 3) < 1e-9

    def test_empty_lists_always_pass(self) -> None:
        probe = KeywordPresenceProbe()
        r = probe.evaluate(make_prompt(), make_response("Anything at all."))
        assert r.passed


# ─── ExpectedKeywordsProbe ───────────────────────────────────────────────────

class TestExpectedKeywordsProbe:
    probe = ExpectedKeywordsProbe()

    def test_uses_prompt_keywords(self) -> None:
        prompt = make_prompt(expected_keywords=["Paris", "France"])
        r = self.probe.evaluate(prompt, make_response("Paris is in France."))
        assert r.passed

    def test_passes_if_no_keywords_set(self) -> None:
        prompt = make_prompt()  # no expected_keywords
        r = self.probe.evaluate(prompt, make_response("Anything."))
        assert r.passed
        assert "skipped" in r.details.lower()

    def test_fails_if_keyword_missing(self) -> None:
        prompt = make_prompt(expected_keywords=["Python"])
        r = self.probe.evaluate(prompt, make_response("I love JavaScript."))
        assert not r.passed
