"""
tests/conftest.py
~~~~~~~~~~~~~~~~~

Shared pytest fixtures for all PromptCanary tests.

Fixtures are grouped by scope:
  - session-scoped: expensive objects (suite configs, mock providers)
  - function-scoped: per-test state (run results, baselines)

Design: no real LLM calls in the test suite. Everything is mocked with
realistic, deterministic response data that exercises the full pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from promptcanary.core.models import (
    CanaryPrompt,
    CanaryRunResult,
    LLMResponse,
    ProviderConfig,
)
from promptcanary.core.probes import JsonValidityProbe, KeywordPresenceProbe, StepByStepProbe
from promptcanary.core.suite import CanarySuite
from promptcanary.providers.base import BaseLLMProvider

# ─────────────────────────────────────────────────────────────────────────────
# Canonical test data
# ─────────────────────────────────────────────────────────────────────────────

PROVIDER_CFG = ProviderConfig(model_id="openai/gpt-4o-test", temperature=0.0, seed=42)

PROMPT_GEO = CanaryPrompt(
    id="geo001",
    text="What is the capital of France? Reply in one sentence.",
    expected_keywords=["Paris"],
    description="Basic geography canary",
)
PROMPT_JSON = CanaryPrompt(
    id="json001",
    text='Return a JSON object with keys "name" and "age". Use example values.',
    description="JSON format canary",
)
PROMPT_STEPS = CanaryPrompt(
    id="step001",
    text="Explain step by step how to boil water.",
    description="Reasoning style canary",
)

RESPONSE_GEO = LLMResponse(
    prompt_id="geo001",
    provider_model_id="openai/gpt-4o-test",
    content="The capital of France is Paris.",
    finish_reason="stop",
    latency_ms=120.5,
    prompt_tokens=15,
    completion_tokens=10,
    total_tokens=25,
)
RESPONSE_JSON_VALID = LLMResponse(
    prompt_id="json001",
    provider_model_id="openai/gpt-4o-test",
    content='{"name": "Alice", "age": 30}',
    finish_reason="stop",
    latency_ms=80.0,
)
RESPONSE_JSON_INVALID = LLMResponse(
    prompt_id="json001",
    provider_model_id="openai/gpt-4o-test",
    content="Here is a JSON: {name: Alice, age: 30}",  # invalid JSON
    finish_reason="stop",
    latency_ms=85.0,
)
RESPONSE_STEPS = LLMResponse(
    prompt_id="step001",
    provider_model_id="openai/gpt-4o-test",
    content=(
        "Step 1: Fill a pot with water.\n"
        "Step 2: Place the pot on the stove.\n"
        "Step 3: Turn the burner to high heat.\n"
        "Step 4: Wait until large bubbles form - this means the water is boiling."
    ),
    finish_reason="stop",
    latency_ms=200.0,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock provider
# ─────────────────────────────────────────────────────────────────────────────


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock provider for tests - no network calls."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        super().__init__(PROVIDER_CFG)
        self._responses = responses or {
            "geo001": RESPONSE_GEO.content,
            "json001": RESPONSE_JSON_VALID.content,
            "step001": RESPONSE_STEPS.content,
        }
        self.call_count = 0
        self.calls: list[tuple[CanaryPrompt, str | None]] = []

    def complete(
        self,
        prompt: CanaryPrompt,
        *,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        self.call_count += 1
        self.calls.append((prompt, system_prompt))
        content = self._responses.get(prompt.id, f"Mock response to: {prompt.text[:50]}")
        return LLMResponse(
            prompt_id=prompt.id,
            provider_model_id=self.config.model_id,
            content=content,
            finish_reason="stop",
            latency_ms=50.0,
            prompt_tokens=20,
            completion_tokens=15,
            total_tokens=35,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_provider() -> MockLLMProvider:
    """A fresh mock provider for each test."""
    return MockLLMProvider()


@pytest.fixture
def failing_json_provider() -> MockLLMProvider:
    """Mock provider that returns invalid JSON for json001."""
    return MockLLMProvider(
        responses={
            "geo001": RESPONSE_GEO.content,
            "json001": RESPONSE_JSON_INVALID.content,
            "step001": RESPONSE_STEPS.content,
        }
    )


@pytest.fixture
def basic_suite() -> CanarySuite:
    """A minimal CanarySuite with one prompt and one probe."""
    return CanarySuite(
        name="test-suite",
        prompts=[PROMPT_GEO],
        probes=[KeywordPresenceProbe(required_keywords=["Paris"])],
    )


@pytest.fixture
def full_suite() -> CanarySuite:
    """A CanarySuite with multiple prompts and probe types."""
    return CanarySuite(
        name="test-suite",
        prompts=[PROMPT_GEO, PROMPT_JSON, PROMPT_STEPS],
        probes=[
            KeywordPresenceProbe(required_keywords=["Paris"]),
            JsonValidityProbe(),
            StepByStepProbe(expect_steps=True),
        ],
    )


@pytest.fixture
def clean_run_result(basic_suite: CanarySuite, mock_provider: MockLLMProvider) -> CanaryRunResult:
    """A passing CanaryRunResult from the basic suite."""
    return basic_suite.run(mock_provider, show_progress=False)


@pytest.fixture
def failing_run_result(
    full_suite: CanarySuite, failing_json_provider: MockLLMProvider
) -> CanaryRunResult:
    """A CanaryRunResult with at least one failing probe."""
    return full_suite.run(failing_json_provider, show_progress=False)


@pytest.fixture
def tmp_baselines(tmp_path: Path) -> Path:
    """A temporary directory for baseline storage in tests."""
    baselines = tmp_path / "baselines"
    baselines.mkdir()
    return baselines


@pytest.fixture
def sample_canary_yaml(tmp_path: Path) -> Path:
    """Write a minimal canary.yaml to a temp directory and return its path."""
    yaml_content = """\
name: yaml-test-suite
description: "Test suite from YAML"
probes:
  - type: keyword_presence
    required_keywords:
      - "Paris"
  - type: json_validity
prompts:
  - text: "What is the capital of France?"
    expected_keywords: ["Paris"]
  - text: "Return valid JSON with a name key."
"""
    p = tmp_path / "canary.yaml"
    p.write_text(yaml_content, encoding="utf-8")
    return p
