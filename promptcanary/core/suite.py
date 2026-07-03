"""
promptcanary.core.suite
~~~~~~~~~~~~~~~~~~~~~~~

CanarySuite — the central orchestrator.

A CanarySuite holds a collection of :class:`CanaryPrompt` objects and
:class:`BaseProbe` instances. It drives the run loop, calls the provider,
applies probes, and returns a rich :class:`CanaryRunResult`.

Key design choices:
  - Provider calls are made sequentially to be predictable and easy to debug.
    (Async parallel support is post-MVP.)
  - All state for a single run is encapsulated in CanaryRunResult.
  - CanarySuite is reusable across providers and runs.
  - YAML loading provides the DX-first path; SDK construction is for power users.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from rich.progress import TaskID

from promptcanary.core.models import (
    CanaryPrompt,
    CanaryRunResult,
    ProviderConfig,
)
from promptcanary.core.probes.base import BaseProbe

if TYPE_CHECKING:
    from promptcanary.providers.base import BaseLLMProvider


class CanarySuite:
    """Holds a collection of prompts and probes, and drives the canary run.

    Args:
        name:         Human-readable name for this suite.
        prompts:      List of :class:`CanaryPrompt` objects.
        probes:       List of :class:`BaseProbe` instances to run on every response.
        description:  Optional description shown in reports.
        tags:         Optional tags for categorisation.

    Example::

        from promptcanary import CanarySuite, LiteLLMProvider
        from promptcanary.core.probes import JsonValidityProbe, StepByStepProbe

        suite = CanarySuite(
            name="production-agent",
            prompts=[CanaryPrompt(text="Return JSON: {name: 'Alice', age: 30}")],
            probes=[JsonValidityProbe(), StepByStepProbe(expect_steps=False)],
        )
        provider = LiteLLMProvider("openai/gpt-4o-mini")
        result = suite.run(provider)
        print(result.overall_score)
    """

    def __init__(
        self,
        name: str,
        prompts: list[CanaryPrompt],
        probes: list[BaseProbe],
        *,
        description: str = "",
        tags: list[str] | None = None,
        default_system_prompt: str | None = None,
    ) -> None:
        if not prompts:
            raise ValueError("CanarySuite requires at least one prompt.")
        if not probes:
            raise ValueError("CanarySuite requires at least one probe.")

        self.name = name
        self.prompts = prompts
        self.probes = probes
        self.description = description
        self.tags = tags or []
        self.default_system_prompt = default_system_prompt

    # ── Construction helpers ─────────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, path: str | Path) -> CanarySuite:
        """Load a CanarySuite from a YAML configuration file.

        Expected YAML structure::

            name: my-suite
            description: Tests production agent behaviour.
            probes:
              - type: json_validity
              - type: step_by_step
                expect_steps: false
              - type: keyword_presence
                required_keywords: ["Paris"]
            prompts:
              - text: "What is the capital of France?"
                expected_keywords: ["Paris"]
                description: "Basic geography canary"

        Args:
            path: Path to the ``canary.yaml`` file.

        Returns:
            A fully configured :class:`CanarySuite`.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Canary config not found: {p}")

        with p.open("r", encoding="utf-8") as f:
            config: dict[str, Any] = yaml.safe_load(f)

        return cls._from_dict(config)

    @classmethod
    def _from_dict(cls, config: dict[str, Any]) -> CanarySuite:
        """Build a CanarySuite from a parsed dict (internal)."""
        from promptcanary.core.probes.base import get_probe

        name = config.get("name", "unnamed-suite")
        description = config.get("description", "")
        default_system_prompt = config.get("default_system_prompt")
        tags = config.get("tags", [])

        # ── Build prompts ─────────────────────────────────────────────────────
        raw_prompts = config.get("prompts", [])
        if not raw_prompts:
            raise ValueError("canary.yaml must contain at least one prompt.")

        prompts = []
        for rp in raw_prompts:
            if isinstance(rp, str):
                prompts.append(CanaryPrompt(text=rp))
            else:
                prompts.append(CanaryPrompt(**rp))

        # ── Build probes ──────────────────────────────────────────────────────
        raw_probes = config.get("probes", [])
        if not raw_probes:
            raise ValueError("canary.yaml must contain at least one probe.")

        probes: list[BaseProbe] = []
        for rp in raw_probes:
            if isinstance(rp, str):
                # Just a probe_id string
                probe_cls = get_probe(rp)
                probes.append(probe_cls())
            else:
                probe_type = rp.pop("type") if "type" in rp else rp.pop("probe_id", None)
                if not probe_type:
                    raise ValueError(f"Probe config missing 'type': {rp}")
                probe_cls = get_probe(probe_type)
                probes.append(probe_cls(**rp))

        return cls(
            name=name,
            prompts=prompts,
            probes=probes,
            description=description,
            tags=tags,
            default_system_prompt=default_system_prompt,
        )

    def to_yaml_template(self) -> str:
        """Render this suite back to a YAML config string (useful for init)."""
        import yaml as _yaml

        data: dict[str, Any] = {
            "name": self.name,
            "description": self.description or "",
            "tags": self.tags,
            "probes": [{"type": p.probe_id} for p in self.probes],
            "prompts": [
                {
                    "text": cp.text,
                    "description": cp.description,
                    "tags": cp.tags,
                }
                for cp in self.prompts
            ],
        }
        return _yaml.dump(data, default_flow_style=False, allow_unicode=True)

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(
        self,
        provider: BaseLLMProvider,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        seed: int | None = None,
        show_progress: bool = True,
    ) -> CanaryRunResult:
        """Run all prompts against the provider, apply all probes, return results.

        Args:
            provider:      The LLM provider to query.
            temperature:   Override default temperature (0.0 recommended).
            max_tokens:    Override max_tokens.
            seed:          Override seed for reproducibility.
            show_progress: Whether to show a Rich progress bar.

        Returns:
            A fully-populated :class:`CanaryRunResult`.
        """
        from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

        # Build a ProviderConfig for this run
        provider_cfg = provider.config
        if temperature is not None or max_tokens is not None or seed is not None:
            provider_cfg = ProviderConfig(
                model_id=provider_cfg.model_id,
                temperature=temperature if temperature is not None else provider_cfg.temperature,
                max_tokens=max_tokens if max_tokens is not None else provider_cfg.max_tokens,
                seed=seed if seed is not None else provider_cfg.seed,
                extra_params=provider_cfg.extra_params,
            )

        result = CanaryRunResult(
            suite_name=self.name,
            provider=provider_cfg,
        )

        total = len(self.prompts)
        all_responses = []
        all_probe_results = []

        progress_ctx = (
            Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
            )
            if show_progress
            else _NoopContext()
        )

        with progress_ctx as progress:
            task = progress.add_task(
                f"[cyan]Running {total} prompt(s) x {len(self.probes)} probe(s)…",
                total=total,
            )

            for i, prompt in enumerate(self.prompts, 1):
                # ── Call provider ─────────────────────────────────────────────
                system = prompt.system_prompt or self.default_system_prompt
                t0 = time.perf_counter()
                llm_response = provider.complete(prompt, system_prompt=system)
                latency_ms = (time.perf_counter() - t0) * 1000

                # Patch latency if provider didn't set it
                if llm_response.latency_ms is None:
                    # Rebuild with latency (frozen model)
                    llm_response = llm_response.model_copy(
                        update={"latency_ms": round(latency_ms, 2)}
                    )

                all_responses.append(llm_response)

                # ── Apply probes ──────────────────────────────────────────────
                for probe in self.probes:
                    try:
                        probe_result = probe.evaluate(prompt, llm_response)
                    except Exception as exc:
                        # Probe errors become scored failures, never crashes
                        from promptcanary.core.models import ProbeResult

                        probe_result = ProbeResult(
                            probe_id=probe.probe_id,
                            probe_name=probe.name,
                            category=probe.category,
                            prompt_id=prompt.id,
                            passed=False,
                            score=0.0,
                            details=f"Probe raised an exception: {type(exc).__name__}: {exc}",
                        )
                    all_probe_results.append(probe_result)

                progress.update(task, advance=1, description=f"[cyan]Prompt {i}/{total}…")

        # Populate result (Pydantic frozen workaround: reassign)
        result.probe_results.extend(all_probe_results)
        result.llm_responses.extend(all_responses)
        result.finished_at = datetime.now(timezone.utc)

        return result

    # ── Repr ─────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"CanarySuite(name={self.name!r}, "
            f"prompts={len(self.prompts)}, "
            f"probes={len(self.probes)})"
        )


class _NoopContext:
    """Context manager no-op for when progress display is disabled.

    Mirrors the subset of Rich's ``Progress`` API used by ``CanarySuite.run()``
    (``add_task`` / ``update``) as no-ops, so the caller can use the same
    code path regardless of whether progress display is enabled — no
    ``if show_progress:`` branching needed around each call.
    """

    def __enter__(self) -> _NoopContext:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def add_task(self, *_args: object, **_kwargs: object) -> TaskID:
        return TaskID(-1)

    def update(self, *_args: object, **_kwargs: object) -> None:
        pass
