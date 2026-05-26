"""
promptcanary.core.probes.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Base class and registry for all Probes.

A Probe is a callable that takes a (CanaryPrompt, LLMResponse) pair and
returns a ProbeResult. Every built-in and user-defined probe must inherit
from BaseProbe (or use the @probe decorator which builds a thin wrapper).

Extension Contract:
  - Override `evaluate()` — it receives the prompt and response and must
    return a ProbeResult.
  - Set `probe_id`, `name`, `category` as class attributes or pass to __init__.
  - Probes must be stateless: the same instance should be safe to call
    concurrently from multiple threads.
"""

from __future__ import annotations

import abc
import inspect
from collections.abc import Callable
from typing import Any

from promptcanary.core.models import (
    CanaryPrompt,
    LLMResponse,
    ProbeCategory,
    ProbeResult,
)


class BaseProbe(abc.ABC):
    """Abstract base class for all PromptCanary probes.

    Subclasses must implement :meth:`evaluate`.

    Attributes:
        probe_id:  Stable machine-readable identifier (snake_case).
        name:      Human-readable display name.
        category:  High-level :class:`ProbeCategory`.
        description: One-sentence description shown in reports.
    """

    probe_id: str = ""
    name: str = ""
    category: ProbeCategory = ProbeCategory.CUSTOM
    description: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Auto-register in the global probe registry when a concrete subclass
        # is defined (i.e., it's not abstract itself).
        if not inspect.isabstract(cls) and cls.probe_id:
            _PROBE_REGISTRY[cls.probe_id] = cls

    @abc.abstractmethod
    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        """Run this probe and return a structured result.

        Args:
            prompt:   The :class:`CanaryPrompt` that was sent.
            response: The :class:`LLMResponse` received.

        Returns:
            A :class:`ProbeResult` with score, pass/fail, and details.
        """
        ...

    def __call__(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        """Make probes callable directly: ``probe(prompt, response)``."""
        return self.evaluate(prompt, response)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(probe_id={self.probe_id!r})"

    # ── Helpers for subclasses ────────────────────────────────────────────────

    def _make_result(
        self,
        prompt_id: str,
        *,
        passed: bool,
        score: float,
        details: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ProbeResult:
        """Convenience factory so subclasses don't repeat boilerplate."""
        return ProbeResult(
            probe_id=self.probe_id,
            probe_name=self.name,
            category=self.category,
            prompt_id=prompt_id,
            passed=passed,
            score=max(0.0, min(1.0, score)),
            details=details,
            metadata=metadata or {},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Global probe registry
# ─────────────────────────────────────────────────────────────────────────────

_PROBE_REGISTRY: dict[str, type[BaseProbe]] = {}


def get_probe_registry() -> dict[str, type[BaseProbe]]:
    """Return a copy of the global probe registry."""
    return dict(_PROBE_REGISTRY)


def get_probe(probe_id: str) -> type[BaseProbe]:
    """Retrieve a registered probe class by ID.

    Raises:
        KeyError: If no probe with the given ID is registered.
    """
    try:
        return _PROBE_REGISTRY[probe_id]
    except KeyError:
        available = ", ".join(sorted(_PROBE_REGISTRY))
        raise KeyError(
            f"No probe registered with id={probe_id!r}. Available probes: {available}"
        ) from None


# ─────────────────────────────────────────────────────────────────────────────
# @probe decorator — quick functional API for custom probes
# ─────────────────────────────────────────────────────────────────────────────


def probe(
    probe_id: str,
    *,
    name: str = "",
    category: ProbeCategory = ProbeCategory.CUSTOM,
    description: str = "",
) -> Callable[[Callable[[CanaryPrompt, LLMResponse], ProbeResult]], type[BaseProbe]]:
    """Decorator that turns a plain function into a registered ``BaseProbe``.

    Usage::

        @probe("my_probe", name="My Custom Probe", category=ProbeCategory.CUSTOM)
        def evaluate(prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
            passed = "hello" in response.content.lower()
            return ProbeResult(
                probe_id="my_probe",
                probe_name="My Custom Probe",
                category=ProbeCategory.CUSTOM,
                prompt_id=prompt.id,
                passed=passed,
                score=1.0 if passed else 0.0,
                details="Checked for greeting.",
            )
    """

    def decorator(fn: Callable[[CanaryPrompt, LLMResponse], ProbeResult]) -> type[BaseProbe]:
        _name = name or fn.__name__.replace("_", " ").title()
        _captured_fn = fn

        # Build the class dynamically with evaluate already defined so ABC is satisfied
        def _evaluate(self: BaseProbe, p: CanaryPrompt, r: LLMResponse) -> ProbeResult:
            return _captured_fn(p, r)

        _FunctionalProbe = type(  # noqa: N806  (dynamic class creation — uppercase is intentional)
            _name,
            (BaseProbe,),
            {
                "probe_id": probe_id,
                "name": _name,
                "category": category,
                "description": description,
                "evaluate": _evaluate,
            },
        )

        _PROBE_REGISTRY[probe_id] = _FunctionalProbe
        return _FunctionalProbe

    return decorator
