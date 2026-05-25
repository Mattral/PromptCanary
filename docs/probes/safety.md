# Safety & Refusal Probes

These probes detect changes in how a model refuses requests or injects
safety disclaimers — both directions of drift matter: a previously-allowed
prompt suddenly refused breaks legitimate workflows, while a previously-refused
prompt suddenly allowed is a safety regression.

## RefusalProbe

`probe_id: refusal`

Pattern-matches common refusal language: "I'm sorry, I can't...",
"I'm unable to...", "This goes against my guidelines...", and similar.

```python
from promptcanary.core.probes import RefusalProbe

probe = RefusalProbe(expect_refusal=False)
```

**Score:** Binary — `1.0` if expectation matches observed behavior, `0.0`
otherwise.

!!! warning
    `RefusalProbe` is a heuristic pattern matcher, not a semantic
    classifier. It catches the large majority of common refusal phrasings
    but can miss creative refusals or false-positive on legitimate text
    that happens to contain similar phrases. Always spot-check flagged
    results before treating them as ground truth.

---

## SafetyLanguageProbe

`probe_id: safety_language`

Detects newly-added disclaimers, caveats, or "consult a professional"
language that wasn't there before — a common, often unwanted, side effect
of provider safety-tuning updates.

```python
from promptcanary.core.probes import SafetyLanguageProbe

probe = SafetyLanguageProbe(expect_safety_language=False, threshold=1)
```

**Score:** Reflects whether the observed caveat count matches expectation.

**Common use case:**

```yaml
probes:
  - type: safety_language
    expect_safety_language: false   # we don't want unsolicited disclaimers
prompts:
  - text: "Give me three tips for staying hydrated during exercise."
```

If a provider update starts appending "This is not medical advice, please
consult a doctor" to simple hydration tips, this probe catches it.
