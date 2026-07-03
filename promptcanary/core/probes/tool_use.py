"""
promptcanary.core.probes.tool_use
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tool-Use probes — detect behavioral drift in how models call tools/functions.

These are essential for agent workflows where model output drives downstream
function dispatch. Silent changes to function names, argument keys, or call
structure break parsers and pipelines without any exception.

Probes:
  - ToolCallPresenceProbe  — Is a tool/function call present at all?
  - ToolCallNameProbe      — Does the model call the *right* function?
  - ToolCallArgsProbe      — Are required arguments present and well-formed?
  - ToolCallSchemaProbe    — Full structured validation of a tool call JSON blob.
"""

from __future__ import annotations

import json
import re
from typing import Any

from promptcanary.core.models import (
    CanaryPrompt,
    LLMResponse,
    ProbeCategory,
    ProbeResult,
)
from promptcanary.core.probes.base import BaseProbe


class ToolCallPresenceProbe(BaseProbe):
    """Detects whether a tool/function call is present in the response at all.

    Supports multiple detection strategies:
      - ``"json"``    — parse response as JSON and look for ``"function"`` or
                        ``"tool_calls"`` keys (OpenAI-style).
      - ``"text"``    — scan raw text for function-call-like patterns.
      - ``"auto"``    — try JSON first, fall back to text.

    Args:
        expect_tool_call:  True = expect a call to be present; False = expect none.
        strategy:          Detection strategy: ``"auto"``, ``"json"``, or ``"text"``.

    Score: 1.0 when expectation matches, 0.0 when not.

    Example::

        probe = ToolCallPresenceProbe(expect_tool_call=True)
        result = probe(prompt, response)
        # result.passed is True if a function call is detected
    """

    probe_id = "tool_call_presence"
    name = "Tool Call Presence"
    category = ProbeCategory.TOOL_USE
    description = "Detects whether any tool/function call is present in the response."

    _TEXT_PATTERNS = [  # noqa: RUF012
        r'"function"\s*:\s*"',
        r'"tool_calls"\s*:\s*\[',
        r'"name"\s*:\s*"\w+"\s*,\s*"arguments"',
        r"<tool_call>",
        r"<function_calls>",
        r"\bfunctions?\.\w+\(",
    ]

    def __init__(
        self,
        expect_tool_call: bool = True,
        strategy: str = "auto",
    ) -> None:
        if strategy not in {"auto", "json", "text"}:
            raise ValueError(f"strategy must be 'auto', 'json', or 'text'. Got: {strategy!r}")
        self.expect_tool_call = expect_tool_call
        self.strategy = strategy

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        detected = self._detect(response.content)

        if self.expect_tool_call:
            passed = detected
            score = 1.0 if detected else 0.0
            details = (
                "Tool call detected as expected."
                if detected
                else "Expected tool call but none found in response."
            )
        else:
            passed = not detected
            score = 0.0 if detected else 1.0
            details = (
                "No tool call present, as expected."
                if not detected
                else "Unexpected tool call detected in response."
            )

        return self._make_result(
            prompt.id,
            passed=passed,
            score=score,
            details=details,
            metadata={"tool_call_detected": detected, "strategy": self.strategy},
        )

    def _detect(self, content: str) -> bool:
        if self.strategy in {"json", "auto"}:
            try:
                data = json.loads(content.strip())
                if isinstance(data, dict):
                    if "function" in data or "tool_calls" in data or "name" in data:
                        return True
                if isinstance(data, list) and any(
                    isinstance(item, dict) and ("function" in item or "name" in item)
                    for item in data
                ):
                    return True
            except (json.JSONDecodeError, ValueError):
                pass  # fall through to text detection

        if self.strategy in {"text", "auto"}:
            for pattern in self._TEXT_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    return True

        return False


class ToolCallNameProbe(BaseProbe):
    """Checks that the model calls a specific named function.

    Handles OpenAI tool_calls format, plain JSON with ``"function"`` key,
    and text-embedded function name patterns.

    Args:
        expected_name:   The function name that must be called.
        case_sensitive:  Default False — model output casing is inconsistent.
        allow_aliases:   Additional acceptable function names (e.g. old API names).

    Score:
        1.0 — correct name found.
        0.3 — a different function was called (drift signal, not complete failure).
        0.0 — no function call found at all.

    Example::

        probe = ToolCallNameProbe("search_web", allow_aliases=["web_search"])
        result = probe(prompt, response)
    """

    probe_id = "tool_call_name"
    name = "Tool Call Name"
    category = ProbeCategory.TOOL_USE
    description = "Verifies the model calls the expected function by name."

    def __init__(
        self,
        expected_name: str,
        *,
        case_sensitive: bool = False,
        allow_aliases: list[str] | None = None,
    ) -> None:
        self.expected_name = expected_name
        self.case_sensitive = case_sensitive
        self.allow_aliases = allow_aliases or []

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        content = response.content
        extracted_names = self._extract_function_names(content)

        if not extracted_names:
            return self._make_result(
                prompt.id,
                passed=False,
                score=0.0,
                details="No function call detected in response.",
                metadata={"extracted_names": [], "expected": self.expected_name},
            )

        all_accepted = [self.expected_name, *self.allow_aliases]
        if not self.case_sensitive:
            all_accepted_lower = [n.lower() for n in all_accepted]
            extracted_lower = [n.lower() for n in extracted_names]
            match = any(n in all_accepted_lower for n in extracted_lower)
        else:
            match = any(n in all_accepted for n in extracted_names)

        if match:
            return self._make_result(
                prompt.id,
                passed=True,
                score=1.0,
                details=f"Correct function name found: {extracted_names}.",
                metadata={"extracted_names": extracted_names, "expected": self.expected_name},
            )

        # A function was called, but the wrong one — partial score as drift signal
        return self._make_result(
            prompt.id,
            passed=False,
            score=0.3,
            details=(
                f"Wrong function called: {extracted_names}. Expected: '{self.expected_name}'."
            ),
            metadata={"extracted_names": extracted_names, "expected": self.expected_name},
        )

    def _extract_function_names(self, content: str) -> list[str]:
        """Extract function names from various tool-call formats."""
        names: list[str] = []

        # OpenAI tool_calls format: [{"function": {"name": "search"}, ...}]
        try:
            data = json.loads(content.strip())
            if isinstance(data, dict):
                if "function" in data and isinstance(data["function"], dict):
                    n = data["function"].get("name")
                    if n:
                        names.append(str(n))
                elif "name" in data:
                    names.append(str(data["name"]))
                if "tool_calls" in data:
                    for tc in data.get("tool_calls", []):
                        if isinstance(tc, dict) and "function" in tc:
                            n = tc["function"].get("name")
                            if n:
                                names.append(str(n))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "function" in item:
                        n = item["function"].get("name")
                        if n:
                            names.append(str(n))
        except (json.JSONDecodeError, ValueError, AttributeError):
            pass

        # Text fallback: "function": "search_web" or "name": "search_web"
        if not names:
            for pattern in [
                r'"(?:function|name)"\s*:\s*"([^"]+)"',
                r"<function_calls>\s*<invoke>\s*<tool_name>([^<]+)</tool_name>",
            ]:
                for m in re.finditer(pattern, content, re.IGNORECASE):
                    names.append(m.group(1).strip())

        return list(dict.fromkeys(names))  # dedupe, preserve order


class ToolCallArgsProbe(BaseProbe):
    """Checks that required arguments are present in a tool call.

    Extracts argument keys from the most common tool-call formats and
    verifies all required keys are present.

    Args:
        required_args:   Argument keys that must appear in the call.
        forbidden_args:  Argument keys that must NOT appear.

    Score: Fraction of required_args present (0.0-1.0), penalised for forbidden.

    Example::

        probe = ToolCallArgsProbe(
            required_args=["query", "limit", "language"],
            forbidden_args=["api_key"],   # should never leak into call
        )
    """

    probe_id = "tool_call_args"
    name = "Tool Call Arguments"
    category = ProbeCategory.TOOL_USE
    description = "Verifies required arguments are present in the tool call."

    def __init__(
        self,
        required_args: list[str],
        forbidden_args: list[str] | None = None,
    ) -> None:
        self.required_args = required_args
        self.forbidden_args = forbidden_args or []

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        arg_keys = self._extract_arg_keys(response.content)

        if not arg_keys and not self.required_args:
            return self._make_result(
                prompt.id,
                passed=True,
                score=1.0,
                details="No args required and none found.",
            )

        missing = [k for k in self.required_args if k not in arg_keys]
        forbidden_found = [k for k in self.forbidden_args if k in arg_keys]

        total = len(self.required_args)
        score = ((total - len(missing)) / max(total, 1)) * (0.5 if forbidden_found else 1.0)
        passed = not missing and not forbidden_found

        parts = []
        if missing:
            parts.append(f"Missing args: {missing}")
        if forbidden_found:
            parts.append(f"Forbidden args present: {forbidden_found}")
        if passed:
            parts.append(f"All {total} required arg(s) present.")

        return self._make_result(
            prompt.id,
            passed=passed,
            score=score,
            details=" | ".join(parts),
            metadata={
                "extracted_keys": sorted(arg_keys),
                "missing": missing,
                "forbidden_found": forbidden_found,
            },
        )

    def _extract_arg_keys(self, content: str) -> set[str]:
        """Extract argument keys from various tool-call JSON formats."""
        keys: set[str] = set()

        try:
            data: Any = json.loads(content.strip())

            def _collect(obj: Any) -> None:
                if isinstance(obj, dict):
                    # Arguments are usually under "arguments", "parameters", "args", or "input"
                    for arg_key in ("arguments", "parameters", "args", "input"):
                        if arg_key in obj:
                            val = obj[arg_key]
                            # OpenAI format: arguments is a JSON-encoded string
                            if isinstance(val, str):
                                try:
                                    parsed = json.loads(val)
                                    if isinstance(parsed, dict):
                                        keys.update(parsed.keys())
                                except (json.JSONDecodeError, ValueError):
                                    pass
                            elif isinstance(val, dict):
                                keys.update(val.keys())
                    for v in obj.values():
                        _collect(v)
                elif isinstance(obj, list):
                    for item in obj:
                        _collect(item)

            _collect(data)
        except (json.JSONDecodeError, ValueError):
            pass

        # Text fallback: look for "key": value patterns in argument-like context
        if not keys:
            for m in re.finditer(r'"(\w+)"\s*:\s*(?:"[^"]*"|\d+|true|false|\[|\{)', content):
                candidate = m.group(1)
                # Exclude structural keys
                if candidate not in {
                    "function",
                    "name",
                    "arguments",
                    "tool_calls",
                    "type",
                    "id",
                    "role",
                    "content",
                }:
                    keys.add(candidate)

        return keys


class ToolCallSchemaProbe(BaseProbe):
    """Full structural validation of a tool call JSON blob against a schema.

    Combines name, presence, and argument checking into one probe using an
    expected schema dict. Designed for tightly-specified agent pipelines.

    Args:
        schema: Dict describing the expected call::

            {
                "name": "search_web",            # required function name
                "required_args": ["query"],       # args that must be present
                "optional_args": ["limit"],       # args that may be present
                "forbidden_args": ["api_key"],    # args that must NOT be present
                "arg_types": {                    # optional type validation
                    "query": str,
                    "limit": int,
                }
            }

    Score: Weighted average of name (40%), arg presence (40%), type correctness (20%).
    """

    probe_id = "tool_call_schema"
    name = "Tool Call Schema"
    category = ProbeCategory.TOOL_USE
    description = "Full structural validation of a tool call against an expected schema."

    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self._name_probe = (
            ToolCallNameProbe(
                schema.get("name", ""),
            )
            if schema.get("name")
            else None
        )
        self._args_probe = ToolCallArgsProbe(
            required_args=schema.get("required_args", []),
            forbidden_args=schema.get("forbidden_args", []),
        )

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        scores: list[float] = []
        details_parts: list[str] = []

        # Name check (40% weight)
        if self._name_probe:
            name_result = self._name_probe.evaluate(prompt, response)
            scores.append(name_result.score * 0.4)
            details_parts.append(f"name: {name_result.details}")
        else:
            scores.append(0.4)  # no name constraint = full credit

        # Args check (40% weight)
        args_result = self._args_probe.evaluate(prompt, response)
        scores.append(args_result.score * 0.4)
        details_parts.append(f"args: {args_result.details}")

        # Type check (20% weight)
        type_score = self._check_arg_types(response.content)
        scores.append(type_score * 0.2)
        if type_score < 1.0:
            details_parts.append(f"types: partial ({type_score:.0%})")

        total_score = sum(scores)
        passed = total_score >= 0.85  # Require 85%+ for structural validity

        return self._make_result(
            prompt.id,
            passed=passed,
            score=total_score,
            details=" | ".join(details_parts),
            metadata={
                "schema": self.schema,
                "component_scores": {
                    "name": scores[0] / 0.4 if self._name_probe else None,
                    "args": args_result.score,
                    "types": type_score,
                },
            },
        )

    def _check_arg_types(self, content: str) -> float:
        """Type-check extracted arg values against schema.arg_types."""
        arg_types = self.schema.get("arg_types", {})
        if not arg_types:
            return 1.0

        try:
            data = json.loads(content.strip())
        except (json.JSONDecodeError, ValueError):
            return 0.0

        def _find_args(obj: Any) -> dict[str, Any]:
            if isinstance(obj, dict):
                for k in ("arguments", "parameters", "args", "input"):
                    val = obj.get(k)
                    if isinstance(val, dict):
                        return val
                for v in obj.values():
                    result = _find_args(v)
                    if result:
                        return result
            elif isinstance(obj, list):
                for item in obj:
                    result = _find_args(item)
                    if result:
                        return result
            return {}

        args = _find_args(data)
        if not args:
            return 0.5  # Can't verify, partial credit

        correct = 0
        for key, expected_type in arg_types.items():
            if key in args:
                val = args[key]
                # JSON booleans: bool is subclass of int in Python, handle explicitly
                if expected_type is bool:
                    correct += 1 if isinstance(val, bool) else 0
                elif expected_type is int:
                    correct += 1 if isinstance(val, int) and not isinstance(val, bool) else 0
                else:
                    correct += 1 if isinstance(val, expected_type) else 0

        return correct / len(arg_types)
