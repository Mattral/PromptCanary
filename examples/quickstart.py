"""
examples/quickstart.py
~~~~~~~~~~~~~~~~~~~~~~

PromptCanary — Standalone Quickstart Example
============================================

This script demonstrates the complete PromptCanary workflow without any
external configuration files. Run it directly to see a full run + baseline
save + drift comparison cycle, using a lightweight mock provider so you can
explore the output without any API keys.

To run against a real provider, swap MockProvider for LiteLLMProvider
and set your API key in the environment.

Usage:
    # Mock (no API key needed):
    python examples/quickstart.py

    # Real provider:
    OPENAI_API_KEY=sk-... python examples/quickstart.py --real openai/gpt-5.4
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Ensure the local development version is importable when running from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from promptcanary import (
    CanaryPrompt,
    CanaryRunResult,
    CanarySuite,
    FileBaselineStore,
    JsonValidityProbe,
    KeywordPresenceProbe,
    LiteLLMProvider,
    RefusalProbe,
    StepByStepProbe,
    compare,
)
from promptcanary.core.models import LLMResponse, ProviderConfig
from promptcanary.core.reporter import DriftReporter, Reporter
from promptcanary.providers.base import BaseLLMProvider
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Mock provider — deterministic responses for demonstration
# ─────────────────────────────────────────────────────────────────────────────

class MockProvider(BaseLLMProvider):
    """Realistic mock responses that make every probe pass on the first run."""

    _RESPONSES: dict[str, str] = {
        "geo_france": "The capital of France is Paris, a city renowned for art and culture.",
        "json_person": '{"name": "Alice Dupont", "age": 29, "city": "Paris"}',
        "code_python": (
            "Step 1: Define a function with `def`.\n"
            "Step 2: Write the function body.\n"
            "Step 3: Call the function to execute it."
        ),
        "support_query": "I understand your frustration. Please contact our support team at support@example.com for immediate assistance.",
    }

    _DRIFTED_RESPONSES: dict[str, str] = {
        # Simulates a provider update that breaks things:
        "geo_france": "Sure! Great question! The capital of France is Paris.",     # preamble added
        "json_person": '{"city": "Paris", "name": "Alice Dupont", "age": 29}',    # key order changed
        "code_python": "Just define a function and call it.",                       # steps gone
        "support_query": (
            "I understand your frustration. Please consult a professional. "
            "This is for informational purposes only. "  # disclaimer injected
            "Contact our support team at support@example.com."
        ),
    }

    def __init__(self, drift: bool = False) -> None:
        super().__init__(ProviderConfig(model_id="mock/provider-v1"))
        self._drift = drift

    def complete(self, prompt: CanaryPrompt, *, system_prompt: str | None = None) -> LLMResponse:
        responses = self._DRIFTED_RESPONSES if self._drift else self._RESPONSES
        content = responses.get(prompt.id, f"This is a mock response to: {prompt.text[:80]}")
        return LLMResponse(
            prompt_id=prompt.id,
            provider_model_id=self.config.model_id,
            content=content,
            finish_reason="stop",
            latency_ms=42.0,
            prompt_tokens=20,
            completion_tokens=len(content.split()),
            total_tokens=20 + len(content.split()),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Suite definition
# ─────────────────────────────────────────────────────────────────────────────

def build_suite() -> CanarySuite:
    return CanarySuite(
        name="quickstart-suite",
        description="Demonstrates the PromptCanary workflow end-to-end.",
        prompts=[
            CanaryPrompt(
                id="geo_france",
                text="What is the capital of France? Answer in one sentence.",
                description="Factual geography anchor",
                expected_keywords=["Paris"],
            ),
            CanaryPrompt(
                id="json_person",
                text='Return a JSON object for a fictional person with keys: name, age, city. JSON only, no markdown.',
                description="JSON format canary",
            ),
            CanaryPrompt(
                id="code_python",
                text="Explain step by step how to write a Python function.",
                description="Step-by-step reasoning canary",
            ),
            CanaryPrompt(
                id="support_query",
                text="A customer says: 'My order hasn't arrived.' Write a one-sentence empathetic reply.",
                description="Customer support tone canary",
            ),
        ],
        probes=[
            KeywordPresenceProbe(required_keywords=["Paris"]),
            JsonValidityProbe(),
            StepByStepProbe(expect_steps=True, min_step_count=2),
            RefusalProbe(expect_refusal=False),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main demo
# ─────────────────────────────────────────────────────────────────────────────

def run_demo(real_provider: str | None = None) -> None:
    console.print()
    console.print(Panel(
        "[bold blue]🐦 PromptCanary — Quickstart Demo[/bold blue]\n\n"
        "This demo runs a full cycle:\n"
        "  1. Build a canary suite with 4 prompts and 4 probes\n"
        "  2. Run against the [green]clean[/green] provider → save baseline\n"
        "  3. Run against the [red]drifted[/red] provider → compare to baseline\n"
        "  4. Show the full drift report",
        border_style="blue",
    ))

    suite = build_suite()

    with tempfile.TemporaryDirectory() as tmp:
        store = FileBaselineStore(Path(tmp) / "baselines")

        # ── Step 1: First run (clean) ─────────────────────────────────────────
        console.print()
        console.print(Rule("[bold green]Step 1 — Baseline Run (Clean Provider)[/bold green]"))
        console.print()

        if real_provider:
            provider_clean = LiteLLMProvider(real_provider, temperature=0.0)
        else:
            provider_clean = MockProvider(drift=False)

        result_clean = suite.run(provider_clean, show_progress=True)
        Reporter(result_clean).print_terminal(console)

        snapshot = store.save(result_clean, note="quickstart-demo-baseline")
        console.print(f"\n[green]✅ Baseline saved[/green] (id: [cyan]{snapshot.snapshot_id[:12]}…[/cyan])\n")

        # ── Step 2: Second run (drifted) ──────────────────────────────────────
        console.print(Rule("[bold red]Step 2 — Current Run (Drifted Provider)[/bold red]"))
        console.print(
            "\n[dim]Simulating a silent provider update that:\n"
            "  • Adds preamble ('Sure! Great question!')\n"
            "  • Reorders JSON keys\n"
            "  • Removes step-by-step reasoning\n"
            "  • Injects safety disclaimers[/dim]\n"
        )

        if real_provider:
            # For real providers, just re-run — no simulated drift
            provider_drifted = LiteLLMProvider(real_provider, temperature=0.0)
        else:
            provider_drifted = MockProvider(drift=True)

        result_drifted = suite.run(provider_drifted, show_progress=True)
        Reporter(result_drifted).print_terminal(console)

        # ── Step 3: Compare ───────────────────────────────────────────────────
        console.print(Rule("[bold yellow]Step 3 — Drift Analysis[/bold yellow]"))
        console.print()

        drift_report = compare(snapshot, result_drifted)
        DriftReporter(drift_report).print_terminal(console)

        # ── Step 4: Generate outputs ─────────────────────────────────────────
        console.print(Rule("[bold blue]Step 4 — Report Outputs[/bold blue]"))
        console.print()

        reporter = DriftReporter(drift_report)
        md = reporter.to_markdown()
        html = reporter.to_html()

        # Show the markdown summary
        console.print("[bold]Markdown report (excerpt):[/bold]")
        console.print("[dim]" + "\n".join(md.split("\n")[:20]) + "\n…[/dim]")

        console.print()
        console.print(Panel(
            "[bold]What to do next:[/bold]\n\n"
            "  1. Edit [cyan]examples/canary.yaml[/cyan] with your own prompts\n"
            "  2. Run: [cyan]promptcanary init my-suite[/cyan]\n"
            "  3. Run: [cyan]promptcanary run --provider openai/gpt-5.4 --save-baseline[/cyan]\n"
            "  4. Add [cyan].github/workflows/promptcanary.yml[/cyan] to your repo\n"
            "  5. Get notified when your provider silently drifts 🐦\n\n"
            "  [dim]Docs: https://github.com/Mattral/PromptCanary[/dim]",
            title="[bold blue]🐦 You're ready![/bold blue]",
            border_style="green",
        ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PromptCanary quickstart demo")
    parser.add_argument(
        "--real",
        metavar="MODEL",
        help='Use a real LiteLLM provider (e.g. "openai/gpt-5.4"). Requires API key in env.',
        default=None,
    )
    args = parser.parse_args()
    run_demo(real_provider=args.real)
