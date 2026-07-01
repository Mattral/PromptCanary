# Factual Probes

## FactualConsistencyProbe

`probe_id: factual_consistency`

Checks a fixed-prompt response against a known-correct expected value.
Ideal for "anchor" prompts whose answer is unlikely to ever legitimately
change — if these start failing, suspect the harness before the model.

```python
from promptcanary.core.probes import FactualConsistencyProbe

probe = FactualConsistencyProbe(
    "Paris",
    match_mode="contains",   # "contains" | "exact" | "startswith"
    case_sensitive=False,
)
```

**Score:** Binary — `1.0` if the expected value matches, `0.0` otherwise.

```yaml
prompts:
  - id: anchor_geography
    text: "What is the capital of France? One sentence."
probes:
  - type: factual_consistency
    expected_value: "Paris"
    match_mode: contains
```

---

## SentimentProbe

`probe_id: sentiment`

Lightweight keyword-based tone detection — no embedding model required,
zero extra dependencies.

```python
from promptcanary.core.probes import SentimentProbe

probe = SentimentProbe(expect_positive=False, threshold=0.02)
```

Pass `expect_positive=None` (the default) to simply *report* observed
sentiment without asserting an expectation — useful for exploratory runs
before you've decided what the "correct" tone should be.

**Score:** Reflects how well observed sentiment matches expectation. When
`expect_positive=None`, always passes and reports the detected tone in
`details`.

!!! note
    `SentimentProbe` is a heuristic, not a calibrated sentiment classifier.
    For high-stakes tone monitoring, consider pairing it with a custom
    probe backed by a dedicated sentiment model — see
    [Writing Custom Probes](custom.md).
