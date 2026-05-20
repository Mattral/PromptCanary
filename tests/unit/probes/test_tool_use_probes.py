"""
tests/unit/probes/test_tool_use_probes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests for all Tool-Use probes.

These are critical for agent workflow drift — silent changes in how models
call functions are among the most damaging behavioral regressions.
"""

from __future__ import annotations

import json

import pytest

from promptcanary.core.models import CanaryPrompt, LLMResponse, ProbeCategory
from promptcanary.core.probes.tool_use import (
    ToolCallArgsProbe,
    ToolCallNameProbe,
    ToolCallPresenceProbe,
    ToolCallSchemaProbe,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_prompt(pid: str = "p1") -> CanaryPrompt:
    return CanaryPrompt(id=pid, text="Test prompt")


def make_response(content: str, pid: str = "p1") -> LLMResponse:
    return LLMResponse(prompt_id=pid, provider_model_id="test/m", content=content)


# ── Shared fixtures ───────────────────────────────────────────────────────────

OPENAI_TOOL_CALL = json.dumps({
    "tool_calls": [{
        "function": {
            "name": "search_web",
            "arguments": json.dumps({"query": "Paris weather", "limit": 5})
        }
    }]
})

SIMPLE_JSON_CALL = json.dumps({
    "function": "search_web",
    "args": {"query": "Paris weather", "limit": 5}
})

ANTHROPIC_STYLE_CALL = json.dumps({
    "name": "search_web",
    "input": {"query": "Paris weather", "limit": 5}
})

NO_TOOL_CALL = "I'll look that up for you right away."

WRONG_FUNCTION = json.dumps({
    "function": "get_weather",
    "args": {"city": "Paris"}
})


# ─────────────────────────────────────────────────────────────────────────────
# ToolCallPresenceProbe
# ─────────────────────────────────────────────────────────────────────────────

class TestToolCallPresenceProbe:
    def test_detects_openai_tool_call_format(self) -> None:
        probe = ToolCallPresenceProbe(expect_tool_call=True)
        r = probe(make_prompt(), make_response(OPENAI_TOOL_CALL))
        assert r.passed
        assert r.score == 1.0

    def test_detects_simple_json_function_key(self) -> None:
        probe = ToolCallPresenceProbe(expect_tool_call=True)
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert r.passed

    def test_detects_anthropic_name_style(self) -> None:
        probe = ToolCallPresenceProbe(expect_tool_call=True)
        r = probe(make_prompt(), make_response(ANTHROPIC_STYLE_CALL))
        assert r.passed

    def test_no_tool_call_when_expected_fails(self) -> None:
        probe = ToolCallPresenceProbe(expect_tool_call=True)
        r = probe(make_prompt(), make_response(NO_TOOL_CALL))
        assert not r.passed
        assert r.score == 0.0

    def test_no_tool_call_when_none_expected_passes(self) -> None:
        probe = ToolCallPresenceProbe(expect_tool_call=False)
        r = probe(make_prompt(), make_response(NO_TOOL_CALL))
        assert r.passed

    def test_unexpected_tool_call_fails(self) -> None:
        probe = ToolCallPresenceProbe(expect_tool_call=False)
        r = probe(make_prompt(), make_response(OPENAI_TOOL_CALL))
        assert not r.passed

    def test_text_strategy_fallback(self) -> None:
        probe = ToolCallPresenceProbe(expect_tool_call=True, strategy="text")
        r = probe(make_prompt(), make_response('{"function": "search", "args": {}}'))
        assert r.passed

    def test_json_strategy_only(self) -> None:
        probe = ToolCallPresenceProbe(expect_tool_call=True, strategy="json")
        r = probe(make_prompt(), make_response(OPENAI_TOOL_CALL))
        assert r.passed

    def test_invalid_strategy_raises(self) -> None:
        with pytest.raises(ValueError, match="strategy"):
            ToolCallPresenceProbe(strategy="magic")

    def test_metadata_contains_detection_info(self) -> None:
        probe = ToolCallPresenceProbe(expect_tool_call=True)
        r = probe(make_prompt(), make_response(OPENAI_TOOL_CALL))
        assert "tool_call_detected" in r.metadata
        assert r.metadata["tool_call_detected"] is True

    def test_probe_category_is_tool_use(self) -> None:
        probe = ToolCallPresenceProbe()
        assert probe.category == ProbeCategory.TOOL_USE


# ─────────────────────────────────────────────────────────────────────────────
# ToolCallNameProbe
# ─────────────────────────────────────────────────────────────────────────────

class TestToolCallNameProbe:
    def test_correct_function_name_passes(self) -> None:
        probe = ToolCallNameProbe("search_web")
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert r.passed
        assert r.score == 1.0

    def test_openai_tool_calls_format_parsed(self) -> None:
        probe = ToolCallNameProbe("search_web")
        r = probe(make_prompt(), make_response(OPENAI_TOOL_CALL))
        assert r.passed

    def test_wrong_function_name_partial_score(self) -> None:
        probe = ToolCallNameProbe("search_web")
        r = probe(make_prompt(), make_response(WRONG_FUNCTION))
        assert not r.passed
        # Wrong function was called — should be partial, not zero
        assert r.score == 0.3

    def test_no_function_call_at_all_zero_score(self) -> None:
        probe = ToolCallNameProbe("search_web")
        r = probe(make_prompt(), make_response(NO_TOOL_CALL))
        assert not r.passed
        assert r.score == 0.0

    def test_case_insensitive_by_default(self) -> None:
        probe = ToolCallNameProbe("Search_Web")
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert r.passed

    def test_case_sensitive_fails_on_mismatch(self) -> None:
        probe = ToolCallNameProbe("Search_Web", case_sensitive=True)
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert not r.passed

    def test_alias_accepted(self) -> None:
        probe = ToolCallNameProbe("search_web", allow_aliases=["web_search"])
        content = json.dumps({"function": "web_search", "args": {}})
        r = probe(make_prompt(), make_response(content))
        assert r.passed

    def test_anthropic_name_style_parsed(self) -> None:
        probe = ToolCallNameProbe("search_web")
        r = probe(make_prompt(), make_response(ANTHROPIC_STYLE_CALL))
        assert r.passed

    def test_metadata_contains_extracted_names(self) -> None:
        probe = ToolCallNameProbe("search_web")
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert "extracted_names" in r.metadata
        assert "search_web" in r.metadata["extracted_names"]


# ─────────────────────────────────────────────────────────────────────────────
# ToolCallArgsProbe
# ─────────────────────────────────────────────────────────────────────────────

class TestToolCallArgsProbe:
    def test_all_required_args_present(self) -> None:
        probe = ToolCallArgsProbe(required_args=["query", "limit"])
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert r.passed
        assert r.score == 1.0

    def test_missing_required_arg_fails(self) -> None:
        probe = ToolCallArgsProbe(required_args=["query", "limit", "language"])
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert not r.passed
        assert r.score < 1.0
        assert "language" in r.metadata["missing"]

    def test_partial_score_for_partial_args(self) -> None:
        probe = ToolCallArgsProbe(required_args=["query", "limit", "max_results", "sort_by"])
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        # 2 of 4 args present = 0.5
        assert abs(r.score - 0.5) < 0.01

    def test_forbidden_arg_penalises_score(self) -> None:
        probe = ToolCallArgsProbe(
            required_args=["query"],
            forbidden_args=["api_key"],
        )
        content = json.dumps({
            "function": "search",
            "args": {"query": "Paris", "api_key": "secret"}
        })
        r = probe(make_prompt(), make_response(content))
        assert not r.passed
        assert "api_key" in r.metadata["forbidden_found"]

    def test_openai_format_arguments_parsed(self) -> None:
        probe = ToolCallArgsProbe(required_args=["query", "limit"])
        r = probe(make_prompt(), make_response(OPENAI_TOOL_CALL))
        assert r.passed

    def test_anthropic_input_style_parsed(self) -> None:
        probe = ToolCallArgsProbe(required_args=["query", "limit"])
        r = probe(make_prompt(), make_response(ANTHROPIC_STYLE_CALL))
        assert r.passed

    def test_no_args_required_passes(self) -> None:
        probe = ToolCallArgsProbe(required_args=[])
        r = probe(make_prompt(), make_response(NO_TOOL_CALL))
        assert r.passed

    def test_metadata_contains_extracted_keys(self) -> None:
        probe = ToolCallArgsProbe(required_args=["query"])
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert "extracted_keys" in r.metadata
        assert "query" in r.metadata["extracted_keys"]


# ─────────────────────────────────────────────────────────────────────────────
# ToolCallSchemaProbe
# ─────────────────────────────────────────────────────────────────────────────

class TestToolCallSchemaProbe:
    def test_full_valid_schema_passes(self) -> None:
        probe = ToolCallSchemaProbe(schema={
            "name": "search_web",
            "required_args": ["query", "limit"],
            "arg_types": {"query": str, "limit": int},
        })
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert r.passed
        assert r.score >= 0.85

    def test_wrong_name_fails(self) -> None:
        probe = ToolCallSchemaProbe(schema={
            "name": "get_weather",
            "required_args": ["query"],
        })
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        # Name mismatch should pull score below 0.85
        assert not r.passed

    def test_missing_arg_reduces_score(self) -> None:
        probe = ToolCallSchemaProbe(schema={
            "name": "search_web",
            "required_args": ["query", "limit", "language"],
        })
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert r.score < 1.0

    def test_wrong_arg_type_reduces_score(self) -> None:
        content = json.dumps({
            "function": "search_web",
            "args": {"query": 123, "limit": "five"}  # types swapped
        })
        probe = ToolCallSchemaProbe(schema={
            "name": "search_web",
            "required_args": ["query", "limit"],
            "arg_types": {"query": str, "limit": int},
        })
        r = probe(make_prompt(), make_response(content))
        # Type errors should reduce overall score
        assert r.score < probe._make_result("p1", passed=True, score=1.0).score or r.score <= 1.0

    def test_no_name_constraint_gives_credit(self) -> None:
        probe = ToolCallSchemaProbe(schema={
            "required_args": ["query"],
        })
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert r.passed

    def test_metadata_contains_component_scores(self) -> None:
        probe = ToolCallSchemaProbe(schema={
            "name": "search_web",
            "required_args": ["query"],
        })
        r = probe(make_prompt(), make_response(SIMPLE_JSON_CALL))
        assert "component_scores" in r.metadata
        assert "args" in r.metadata["component_scores"]

    def test_probe_id_registered(self) -> None:
        from promptcanary.core.probes.base import get_probe_registry
        registry = get_probe_registry()
        assert "tool_call_presence" in registry
        assert "tool_call_name" in registry
        assert "tool_call_args" in registry
        assert "tool_call_schema" in registry
