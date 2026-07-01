# Reasoning Style Probes

These probes detect changes in *how* a model reasons — chain-of-thought
presence, verbosity, hedging language, and preamble before the actual answer.

## StepByStepProbe

`probe_id: step_by_step`

Detects explicit step-by-step reasoning via numbered steps, "Step N:",
"First/Second/Finally", `<thinking>` tags, and similar markers.

```python
from promptcanary.core.probes import StepByStepProbe

probe = StepByStepProbe(expect_steps=True, min_step_count=2)
```

**Score:** Proportional to step-indicator count relative to `min_step_count`.

!!! tip
    Use `expect_steps=False` for prompts where you want a direct answer
    with no chain-of-thought — useful for catching providers that suddenly
    start "showing their work" on simple factual queries.

---

## VerbosityProbe

`probe_id: verbosity`

Word-count drift detection with a tolerance band.

```python
from promptcanary.core.probes import VerbosityProbe

probe = VerbosityProbe(
    expected_words=150,
    tolerance=0.5,    # ±50%
    min_words=20,
    max_words=500,
)
```

**Score:** `1.0` within tolerance; degrades linearly outside it.

---

## ConfidenceLanguageProbe

`probe_id: confidence_language`

Heuristic hedge-word detection ("I think", "perhaps", "might be") versus
confident, direct language.

```python
from promptcanary.core.probes import ConfidenceLanguageProbe

probe = ConfidenceLanguageProbe(expect_hedging=False, threshold=0.03)
```

**Score:** Reflects how well the observed hedge rate matches expectation.

---

## DirectAnswerProbe

`probe_id: direct_answer`

Detects unnecessary preamble before the actual answer — "Sure!",
"Great question!", "I'd be happy to...", "As an AI...".

```python
from promptcanary.core.probes import DirectAnswerProbe

probe = DirectAnswerProbe(expect_direct=True, max_preamble_chars=80)
```

**Score:** `1.0` if direct, `0.0` if preamble detected (when
`expect_direct=True`).

!!! tip
    This is one of the highest-signal probes for catching subtle
    personality/tone drift in chat-style models — preamble injection is a
    very common silent regression.
