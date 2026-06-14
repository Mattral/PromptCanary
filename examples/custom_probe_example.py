"""
examples/custom_probe_example.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

PromptCanary -- Custom Probe Authoring Example
==============================================

Demonstrates three patterns for writing custom probes:

  1. @probe decorator     -- simplest, for one-off stateless probes
  2. BaseProbe subclass   -- recommended for configurable, reusable probes
  3. Domain-specific probe -- full example: a JSON-API contract probe that
                             validates a specific schema expected by a
                             production downstream service

All examples run against a deterministic mock provider -- no API key needed.

Usage:
    python examples/custom_probe_example.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptcanary import (
    CanaryPrompt,
    CanarySuite,
)
from promptcanary.core.models import (
    LLMResponse,
    ProbeCategory,
    ProbeResult,
    ProviderConfig,
)
from promptcanary.core.probes.base import BaseProbe, probe
from promptcanary.core.reporter import Reporter
from promptcanary.providers.base import BaseLLMProvider

from rich.console import Console
from rich.rule import Rule

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Mock provider
# ─────────────────────────────────────────────────────────────────────────────

class MockProvider(BaseLLMProvider):
    def __init__(self, responses: dict[str, str]) -> None:
        super().__init__(ProviderConfig(model_id="mock/v1"))
        self._responses = responses

    def complete(self, prompt, *, system_prompt=None) -> LLMResponse:
        return LLMResponse(
            prompt_id=prompt.id,
            provider_model_id="mock/v1",
            content=self._responses.get(prompt.id, "Default response."),
            finish_reason="stop",
            latency_ms=10.0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pattern 1: @probe decorator
# ─────────────────────────────────────────────────────────────────────────────

console.print()
console.print(Rule("[bold green]Pattern 1: @probe Decorator[/bold green]"))
console.print(
    "[dim]Best for simple, single-purpose probes that don't need configuration.[/dim]\n"
)


@probe("has_code_fence", name="Has Code Fence", category=ProbeCategory.FORMAT)
def check_code_fence(prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
    """Checks that the model wraps code in a markdown code fence."""
    has_fence = "```" in response.content
    return ProbeResult(
        probe_id="has_code_fence",
        probe_name="Has Code Fence",
        category=ProbeCategory.FORMAT,
        prompt_id=prompt.id,
        passed=has_fence,
        score=1.0 if has_fence else 0.0,
        details="Code fence found." if has_fence else "Expected ``` but not found.",
    )


suite_1 = CanarySuite(
    name="pattern-1-suite",
    prompts=[
        CanaryPrompt(id="p1", text="Show me Python code to print 'hello world'."),
    ],
    probes=[check_code_fence()],
)

result_1 = suite_1.run(
    MockProvider({"p1": '```python\nprint("hello world")\n```'}),
    show_progress=False,
)
Reporter(result_1).print_terminal(console)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern 2: BaseProbe subclass
# ─────────────────────────────────────────────────────────────────────────────

console.print(Rule("[bold green]Pattern 2: BaseProbe Subclass[/bold green]"))
console.print(
    "[dim]Recommended for probes with configuration, partial scoring, or complex logic.[/dim]\n"
)


class SentenceCountProbe(BaseProbe):
    """Checks the response has approximately the expected number of sentences.

    Uses partial scoring so gradual verbosity drift is detectable before
    it becomes a hard failure.

    Args:
        expected:  Expected sentence count.
        tolerance: Fractional tolerance (default 0.5 = +-50%).

    Score: 1.0 within tolerance, degrades linearly outside it.
    """

    probe_id = "sentence_count"
    name = "Sentence Count"
    category = ProbeCategory.REASONING

    def __init__(self, expected: int, tolerance: float = 0.5) -> None:
        self.expected = expected
        self.tolerance = tolerance

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        import re
        sentences = [s.strip() for s in re.split(r"[.!?]+", response.content) if s.strip()]
        count = len(sentences)
        ratio = count / max(self.expected, 1)
        deviation = abs(ratio - 1.0)

        # Partial scoring: smooth decay outside tolerance band
        if deviation <= self.tolerance:
            score = 1.0 - (deviation / self.tolerance) * 0.2
        else:
            score = max(0.0, 1.0 - deviation)

        return self._make_result(
            prompt.id,
            passed=deviation <= self.tolerance,
            score=score,
            details=(
                f"{count} sentence(s) vs expected ~{self.expected} "
                f"({ratio:.0%} of expected, tolerance +-{self.tolerance:.0%})."
            ),
            metadata={"sentence_count": count, "expected": self.expected},
        )


suite_2 = CanarySuite(
    name="pattern-2-suite",
    prompts=[
        CanaryPrompt(id="p1", text="Explain what photosynthesis is in 2-3 sentences."),
    ],
    probes=[SentenceCountProbe(expected=2, tolerance=0.5)],
)

result_2 = suite_2.run(
    MockProvider({
        "p1": (
            "Photosynthesis is the process plants use to convert sunlight into energy. "
            "Using chlorophyll in their leaves, plants absorb light, water, and CO2 to "
            "produce glucose and oxygen."
        )
    }),
    show_progress=False,
)
Reporter(result_2).print_terminal(console)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern 3: Domain-specific production probe
# ─────────────────────────────────────────────────────────────────────────────

console.print(Rule("[bold green]Pattern 3: Domain-Specific Production Probe[/bold green]"))
console.print(
    "[dim]A JSON API contract probe that validates a specific schema expected by\n"
    "a downstream service -- catches schema drift before the parser breaks.[/dim]\n"
)


class SupportTicketSchemaProbe(BaseProbe):
    """Validates the exact JSON schema our support-ticket parser expects.

    Ensures the LLM returns a well-formed ticket object that our downstream
    service can consume without a parsing error.

    Expected schema:
        {
            "intent":    str   -- one of REFUND | SHIPPING | ACCOUNT | OTHER
            "priority":  str   -- one of HIGH | MEDIUM | LOW
            "summary":   str   -- concise summary, 10-200 chars
            "escalate":  bool  -- whether to route to senior agent
        }

    Score:
        1.0  All fields present and valid types
        0.75 All required fields but invalid enum value(s)
        0.5  Some fields missing
        0.0  Not valid JSON or completely wrong schema
    """

    probe_id = "support_ticket_schema"
    name = "Support Ticket Schema"
    category = ProbeCategory.FORMAT

    VALID_INTENTS = {"REFUND", "SHIPPING", "ACCOUNT", "OTHER"}
    VALID_PRIORITIES = {"HIGH", "MEDIUM", "LOW"}
    REQUIRED_FIELDS = {"intent", "priority", "summary", "escalate"}

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        # Strip code fences
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        # Parse JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return self._make_result(
                prompt.id, passed=False, score=0.0,
                details=f"Invalid JSON: {e}",
            )

        if not isinstance(data, dict):
            return self._make_result(
                prompt.id, passed=False, score=0.0,
                details=f"Expected JSON object, got {type(data).__name__}.",
            )

        # Field presence
        missing = self.REQUIRED_FIELDS - set(data.keys())
        if missing:
            score = (len(self.REQUIRED_FIELDS) - len(missing)) / len(self.REQUIRED_FIELDS)
            return self._make_result(
                prompt.id, passed=False, score=score,
                details=f"Missing required fields: {sorted(missing)}.",
                metadata={"missing_fields": sorted(missing)},
            )

        # Type + enum validation
        violations = []
        if not isinstance(data.get("intent"), str) or data["intent"] not in self.VALID_INTENTS:
            violations.append(f"intent={data.get('intent')!r} (must be one of {self.VALID_INTENTS})")
        if not isinstance(data.get("priority"), str) or data["priority"] not in self.VALID_PRIORITIES:
            violations.append(f"priority={data.get('priority')!r} (must be one of {self.VALID_PRIORITIES})")
        if not isinstance(data.get("summary"), str) or not 10 <= len(data["summary"]) <= 200:
            violations.append(f"summary length={len(str(data.get('summary', '')))} (must be 10-200 chars)")
        if not isinstance(data.get("escalate"), bool):
            violations.append(f"escalate={data.get('escalate')!r} (must be boolean)")

        if violations:
            return self._make_result(
                prompt.id, passed=False, score=0.75,
                details="Schema valid but enum/type violations: " + "; ".join(violations),
                metadata={"violations": violations},
            )

        return self._make_result(
            prompt.id, passed=True, score=1.0,
            details="Schema fully valid.",
            metadata={"parsed": data},
        )


suite_3 = CanarySuite(
    name="support-agent-suite",
    prompts=[
        CanaryPrompt(
            id="ticket",
            text=(
                "Classify this support message as a JSON ticket.\n"
                "Fields: intent (REFUND|SHIPPING|ACCOUNT|OTHER), "
                "priority (HIGH|MEDIUM|LOW), summary (string), escalate (boolean).\n"
                "Respond with only the JSON object.\n\n"
                "Message: 'I've been waiting 3 weeks for my order and nobody is responding!'"
            ),
            description="Support ticket classification -- validates exact parser contract",
        ),
    ],
    probes=[SupportTicketSchemaProbe()],
)

# Test with a valid response
provider_good = MockProvider({
    "ticket": json.dumps({
        "intent": "SHIPPING",
        "priority": "HIGH",
        "summary": "Customer waiting 3 weeks for order with no response from support team.",
        "escalate": True,
    })
})

# Test with a drifted response (invalid enum value)
provider_drifted = MockProvider({
    "ticket": json.dumps({
        "intent": "delivery_issue",  # wrong: not in VALID_INTENTS
        "priority": "urgent",        # wrong: not in VALID_PRIORITIES
        "summary": "Order delay.",
        "escalate": "yes",           # wrong: string instead of bool
    })
})

console.print("[bold]Valid response:[/bold]")
result_good = suite_3.run(provider_good, show_progress=False)
Reporter(result_good).print_terminal(console)

console.print("[bold]Drifted response (wrong enum values):[/bold]")
result_drifted = suite_3.run(provider_drifted, show_progress=False)
Reporter(result_drifted).print_terminal(console)

# Show the partial score difference
good_score = result_good.overall_score
drift_score = result_drifted.overall_score
console.print(
    f"\n[dim]Score comparison: {good_score:.1%} (valid) vs {drift_score:.1%} (drifted). "
    f"The partial score (0.75) shows the structure is right but the values are wrong --\n"
    f"much more informative than a binary pass/fail.[/dim]\n"
)
