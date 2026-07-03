"""
examples/multi_provider.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~

PromptCanary -- Multi-Provider Comparison Example
=================================================

Run the same canary suite against multiple LLM providers simultaneously
and compare their behavior against a single shared baseline.

This demonstrates a key pattern for production monitoring: if only one
provider regresses, the issue is provider-specific drift. If all providers
regress on the same prompts, suspect your own harness or prompt changes.

Usage:
    # Requires real API keys + Ollama running locally (or comment out Ollama)
    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...
    GEMINI_API_KEY=...
    ollama pull qwen3.6:27b

    python examples/multi_provider.py

    # Or use the --mock flag to run with simulated providers (no keys needed):
    python examples/multi_provider.py --mock
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptcanary import (
    CanaryPrompt,
    CanarySuite,
    FileBaselineStore,
    JsonValidityProbe,
    KeywordPresenceProbe,
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
from rich.table import Table

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Mock providers for --mock mode (no API keys required)
# ─────────────────────────────────────────────────────────────────────────────

class _MockProvider(BaseLLMProvider):
    """Simulates a real provider with deterministic responses."""

    _RESPONSES = {
        "anchor": "The capital of France is Paris.",
        "json":   '{"name": "Alice", "age": 30, "city": "Paris"}',
        "steps":  "Step 1: Open a pot.\nStep 2: Add water.\nStep 3: Heat until boiling.",
        "direct": "Your order will arrive within 3-5 business days.",
    }
    # Provider B simulates mild drift (preamble added)
    _DRIFTED = {
        "anchor": "Sure! The capital of France is Paris, a wonderful city.",
        "json":   '{"city": "Paris", "name": "Alice", "age": 30}',
        "steps":  "Just heat water in a pot until it boils.",
        "direct": "I would be happy to help! Your order will arrive within 3-5 business days.",
    }

    def __init__(self, model_id: str, drift: bool = False) -> None:
        super().__init__(ProviderConfig(model_id=model_id))
        self._drift = drift

    def complete(self, prompt, *, system_prompt=None) -> LLMResponse:
        r = self._DRIFTED if self._drift else self._RESPONSES
        return LLMResponse(
            prompt_id=prompt.id,
            provider_model_id=self.config.model_id,
            content=r.get(prompt.id, "Mock response."),
            finish_reason="stop",
            latency_ms=42.0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Suite definition
# ─────────────────────────────────────────────────────────────────────────────

def build_suite() -> CanarySuite:
    return CanarySuite(
        name="multi-provider-suite",
        description="Tests cross-provider behavioral consistency.",
        prompts=[
            CanaryPrompt(
                id="anchor",
                text="What is the capital of France? Answer in one sentence.",
                expected_keywords=["Paris"],
                description="Factual anchor - should be stable across all providers",
            ),
            CanaryPrompt(
                id="json",
                text="Return a JSON object with keys: name (string), age (integer), city (string). "
                     "Respond with only the JSON, no markdown.",
                description="JSON format consistency probe",
            ),
            CanaryPrompt(
                id="steps",
                text="Explain step by step how to boil water. Keep it concise.",
                description="Reasoning style: expects step-by-step structure",
            ),
            CanaryPrompt(
                id="direct",
                text="A customer asks: 'When will my order arrive?' Reply in one sentence.",
                description="Direct answer check: no preamble expected",
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
# Multi-provider run
# ─────────────────────────────────────────────────────────────────────────────

def run_multi_provider(mock: bool = False) -> None:
    """Run the suite against multiple providers, compare to a shared baseline."""
    suite = build_suite()

    # ── Provider definitions ──────────────────────────────────────────────────
    if mock:
        console.print(
            Panel(
                "[yellow]Running in --mock mode[/yellow]: simulated providers, no API keys needed.\n"
                "Provider A (OpenAI) = clean baseline.\n"
                "Provider B (Anthropic) = mild drift (preamble added, JSON keys reordered).\n"
                "Provider C (Ollama) = clean (same as A).",
                title="[bold blue]PromptCanary - Multi-Provider Example[/bold blue]",
                border_style="blue",
            )
        )
        providers = [
            _MockProvider("openai/gpt-5.4",        drift=False),
            _MockProvider("anthropic/claude-sonnet-4-6", drift=True),
            _MockProvider("ollama/qwen3.6:27b",    drift=False),
        ]
    else:
        from promptcanary import LiteLLMProvider
        console.print(
            Panel(
                "Running against real providers.\n"
                "Ensure API keys are set in your environment:\n"
                "  OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY\n"
                "And Ollama is running: ollama pull qwen3.6:27b",
                title="[bold blue]PromptCanary - Multi-Provider Example[/bold blue]",
                border_style="blue",
            )
        )
        providers = [
            LiteLLMProvider("openai/gpt-5.4",             temperature=0.0),
            LiteLLMProvider("anthropic/claude-sonnet-4-6", temperature=0.0),
            LiteLLMProvider("gemini/gemini-3.5-flash",     temperature=0.0),
            LiteLLMProvider("ollama/qwen3.6:27b",          temperature=0.0),
        ]

    with tempfile.TemporaryDirectory() as tmp:
        store = FileBaselineStore(Path(tmp) / "baselines")
        results = {}

        # ── Run all providers ─────────────────────────────────────────────────
        console.print()
        console.print(Rule("[bold]Step 1 - Running suite against all providers[/bold]"))

        for provider in providers:
            console.print(f"\n[dim]Provider:[/dim] [cyan]{provider.config.model_id}[/cyan]")
            result = suite.run(provider, show_progress=True)
            results[provider.config.model_id] = result

            # Save a per-provider baseline (first run is the reference)
            store.save(result)

        # ── Summary comparison table ──────────────────────────────────────────
        console.print()
        console.print(Rule("[bold]Step 2 - Cross-Provider Comparison[/bold]"))
        console.print()

        table = Table(
            title="Provider Comparison Summary",
            show_header=True,
            header_style="bold blue",
        )
        table.add_column("Provider", style="cyan", min_width=35)
        table.add_column("Score", justify="right", min_width=8)
        table.add_column("Pass Rate", justify="right", min_width=10)
        table.add_column("Failed Probes", justify="right", min_width=13)
        table.add_column("Status")

        for model_id, result in results.items():
            score = result.overall_score
            pass_rate = result.pass_rate
            failed = len(result.failed_probes)
            score_colour = "green" if score >= 0.9 else "yellow" if score >= 0.7 else "red"
            status = (
                "[green]OK[/green]" if failed == 0
                else f"[red]{failed} probe(s) failed[/red]"
            )
            table.add_row(
                model_id,
                f"[{score_colour}]{score:.1%}[/{score_colour}]",
                f"{pass_rate:.1%}",
                str(failed),
                status,
            )

        console.print(table)

        # ── Per-provider detailed reports ─────────────────────────────────────
        console.print()
        console.print(Rule("[bold]Step 3 - Per-Provider Terminal Reports[/bold]"))

        for model_id, result in results.items():
            console.print(f"\n[bold cyan]{model_id}[/bold cyan]")
            Reporter(result).print_terminal(console)

        # ── Drift comparison: compare each provider against the first (baseline) ──
        baseline_model_id = list(results.keys())[0]
        baseline_result = results[baseline_model_id]
        baseline_snap = store.load_latest(suite_name=suite.name)

        if len(results) > 1:
            console.print()
            console.print(
                Rule(
                    f"[bold]Step 4 - Drift vs '{baseline_model_id}' Baseline[/bold]"
                )
            )
            console.print()

            for model_id, result in list(results.items())[1:]:
                console.print(
                    f"\n[bold]{model_id}[/bold] vs [dim]{baseline_model_id}[/dim]"
                )
                # Compare against baseline
                try:
                    drift = compare(baseline_snap, result)
                    DriftReporter(drift).print_terminal(console)
                except ValueError as e:
                    console.print(f"[yellow]Could not compare: {e}[/yellow]")

        # ── Interpretation guide ──────────────────────────────────────────────
        console.print()
        console.print(Panel(
            "[bold]How to interpret these results:[/bold]\n\n"
            "  [green]All providers score similarly[/green] → No drift; "
            "any failures are in your suite or harness, not a specific provider.\n\n"
            "  [yellow]Only one provider regresses[/yellow] → Provider-specific drift. "
            "Check that vendor's release notes or pin an older model version.\n\n"
            "  [red]All providers regress on the same probe[/red] → Your prompt or "
            "probe config may have changed. Check your canary.yaml.\n\n"
            "[dim]Run with --save-baseline to persist these results and compare next week.[/dim]",
            title="[bold]Interpretation Guide[/bold]",
            border_style="dim",
        ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-provider PromptCanary example")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use simulated providers (no API keys required)",
    )
    args = parser.parse_args()
    run_multi_provider(mock=args.mock)
