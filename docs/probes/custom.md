# Writing Custom Probes

Built-in probes cover the common cases, but most teams eventually need a
probe specific to their domain. PromptCanary makes this fast — most custom
probes take under 20 lines of code.

## Option 1: The `@probe` Decorator

Best for simple, single-purpose, stateless probes.

```python
from promptcanary.core.probes.base import probe
from promptcanary.core.models import CanaryPrompt, LLMResponse, ProbeCategory, ProbeResult

@probe("contains_code_fence", name="Contains Code Fence", category=ProbeCategory.FORMAT)
def check_code_fence(prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
    has_fence = "```" in response.content
    return ProbeResult(
        probe_id="contains_code_fence",
        probe_name="Contains Code Fence",
        category=ProbeCategory.FORMAT,
        prompt_id=prompt.id,
        passed=has_fence,
        score=1.0 if has_fence else 0.0,
        details="Code fence found." if has_fence else "No code fence in response.",
    )

# Use it like any built-in probe:
suite = CanarySuite(name="x", prompts=[...], probes=[check_code_fence()])
```

The decorated function is auto-registered — `"contains_code_fence"` is now
usable in YAML config too.

## Option 2: `BaseProbe` Subclass

Recommended for probes with configuration, state, or complex logic.

```python
from promptcanary.core.probes.base import BaseProbe
from promptcanary.core.models import CanaryPrompt, LLMResponse, ProbeCategory

class SentenceCountProbe(BaseProbe):
    """Checks that the response has approximately the expected sentence count.

    Score: 1.0 within tolerance, degrades linearly outside it.
    """
    probe_id = "sentence_count"
    name = "Sentence Count"
    category = ProbeCategory.REASONING

    def __init__(self, expected: int, tolerance: float = 0.5) -> None:
        self.expected = expected
        self.tolerance = tolerance

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse):
        import re
        sentences = [s for s in re.split(r"[.!?]+", response.content) if s.strip()]
        count = len(sentences)
        ratio = count / max(self.expected, 1)
        deviation = abs(ratio - 1.0)
        score = max(0.0, 1.0 - deviation) if deviation > self.tolerance else 1.0 - deviation * 0.2
        return self._make_result(
            prompt.id,
            passed=deviation <= self.tolerance,
            score=score,
            details=f"{count} sentence(s) vs expected ~{self.expected}.",
            metadata={"sentence_count": count},
        )
```

`self._make_result(...)` is a convenience helper that clamps `score` to
`[0.0, 1.0]` and fills in `probe_id`/`probe_name`/`category` automatically.

## Partial Scoring Patterns

Partial scores (between 0.0 and 1.0) matter for trend tracking — they let
you detect *gradual* drift before it becomes a hard failure. A binary
0/1 probe can't distinguish "slightly off" from "completely broken," which
means small regressions hide until they compound into a visible failure.

Prefer partial scoring whenever the underlying signal is naturally
continuous: word counts, key-match fractions, similarity scores. Reserve
binary 0/1 scoring for genuinely binary properties: JSON validity, exact
factual matches.

## Probe Authoring Checklist

Before relying on a custom probe in production (or contributing it back
upstream):

- [ ] Unique `probe_id` in snake_case
- [ ] Meaningful `name` and `category`
- [ ] Docstring with Args, Score semantics, and an Example
- [ ] Returns partial scores where the signal is naturally continuous
- [ ] Never raises — wrap risky parsing in try/except (the probe should
      fail gracefully with `score=0.0`, not crash the run — though
      `CanarySuite.run()` catches exceptions as a safety net regardless)
- [ ] Populates `metadata` with diagnostic detail useful for debugging
- [ ] Has unit tests covering the happy path, failure path, and at least
      one edge case

## Testing Your Probe

```python
def test_my_probe():
    probe = SentenceCountProbe(expected=2, tolerance=0.5)
    prompt = CanaryPrompt(id="p1", text="test")
    response = LLMResponse(prompt_id="p1", provider_model_id="m", content="One. Two.")
    result = probe(prompt, response)
    assert result.passed
    assert result.score >= 0.8
```

See [`tests/unit/probes/`](https://github.com/Mattral/PromptCanary/tree/main/tests/unit/probes)
in the repository for extensive real examples of this pattern.

## Contributing Your Probe Upstream

If your probe is broadly useful, consider opening a PR — see
[Contributing](../contributing.md) for the process and quality bar.
