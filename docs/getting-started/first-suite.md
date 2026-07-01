# Your First Canary Suite

A canary suite is only as useful as the prompts and probes you choose. This
guide covers how to design a suite that actually catches the regressions
that matter to your production system.

## Principle 1: Use Real Production Patterns

Don't invent generic test prompts — mine your logs (or your memory) for
prompts that:

- Have caused problems before
- Represent your most common user intents
- Exercise edge cases in formatting or tool use

```yaml
prompts:
  - id: real_support_query
    text: |
      A customer says: "I've been waiting 3 weeks and still haven't
      received my order." Respond empathetically in one sentence.
    description: "Mirrors our top support ticket category."
```

## Principle 2: Pin Down What 'Correct' Means

Every prompt should have at least one probe that defines success precisely.
Vague prompts with no probes are not canaries — they're just API calls.

```yaml
prompts:
  - text: "Return a JSON object with keys: name, age, city."
probes:
  - type: json_validity
  - type: json_schema
    required_keys: ["name", "age", "city"]
```

## Principle 3: Cover Multiple Drift Dimensions

A single suite should test format, reasoning style, and safety behavior —
because providers can silently change any of these independently.

```yaml
probes:
  # Format
  - type: json_validity
  - type: response_length
    min_chars: 10
    max_chars: 2000

  # Reasoning style
  - type: direct_answer
    expect_direct: true
  - type: step_by_step
    expect_steps: false

  # Safety
  - type: refusal
    expect_refusal: false
  - type: safety_language
    expect_safety_language: false
```

## Principle 4: Use Factual Anchors

Include a couple of prompts with answers that should *never* change
("What is the capital of France?"). If these start failing, the problem
is likely your harness, not the model — a useful sanity check.

```yaml
prompts:
  - id: anchor_geography
    text: "What is the capital of France? One sentence."
    expected_keywords: ["Paris"]
```

## Principle 5: Set `temperature=0.0`

Deterministic settings reduce noise in your drift signal. PromptCanary
defaults to `temperature=0.0` and `seed=42` for this reason — keep them
unless you have a specific reason to introduce randomness.

## A Complete, Production-Minded Example

```yaml
name: customer-support-agent
description: "Canary suite for our production support agent."

probes:
  - type: json_validity
  - type: json_schema
    required_keys: ["intent", "response"]
  - type: refusal
    expect_refusal: false
  - type: direct_answer
    expect_direct: true
  - type: safety_language
    expect_safety_language: false

prompts:
  - id: anchor
    text: "What is the capital of Japan? One sentence."
    expected_keywords: ["Tokyo"]

  - id: refund_request
    text: |
      Classify intent and respond. Return JSON: {"intent": str, "response": str}.
      Customer message: "How do I get a refund for my last order?"

  - id: escalation
    text: |
      Classify intent and respond. Return JSON: {"intent": str, "response": str}.
      Customer message: "This is the third time I've contacted support about this!"
```

## What's Next

- [Probe Reference](../probes/index.md) — every built-in probe with examples
- [Writing Custom Probes](../probes/custom.md) — when built-ins aren't enough
- [Baselines & Comparison](../concepts/baselines.md) — how drift detection actually works
