# We Built a Tool to Catch Silent LLM Drift. Building It Taught Us Something We Didn't Expect.

There's a specific kind of bug that doesn't show up in your error logs.

Your app calls an LLM API. The call succeeds. Status 200. No exception. The
response even looks fine at a glance. And then, three days later, someone on
your team notices the JSON parser has been silently dropping a field, or the
support bot started prefacing every answer with "Great question!", or an
agent stopped calling the search tool it used to call reliably. Nobody
changed your code. Nobody changed your prompt. The provider changed the
model behind the API, and nothing about the interface told you.

We built [PromptCanary](https://github.com/Mattral/PromptCanary) to catch
that specific problem: save what a good response looks like, and tell us
the moment that stops being true. It's a small, open-source Python library
— apply the old "golden master" testing idea from regular software to LLM
outputs, with a scoring layer instead of an equality check, because "did
the output change" isn't the right question when the output is natural
language.

This post isn't the pitch. It's the story of what actually happened while
building it — including the part where our own demo notebooks taught us
something about our own tool that we hadn't noticed at design time.

## The 30-second version

```bash
pip install promptcanary
promptcanary init my-suite
promptcanary run --provider openai/gpt-5.4 --save-baseline

# a week later...
promptcanary compare --provider openai/gpt-5.4 --fail-on-drift
```

You write some prompts that matter to your app. You attach some scoring
functions ("probes") — is it valid JSON, does it call the right function,
does it suddenly refuse something it used to answer. You run it, save the
result as a baseline, and run it again later. If anything regressed, you
get a report telling you exactly which probe failed, on which prompt, and
by how much. That's the whole idea.

Nineteen probes ship out of the box, across five categories — format,
reasoning style, safety/refusal, tool use, and factual consistency — and
you can write your own in about fifteen lines of Python.

Now here's what broke.

## Bug #1: it worked on our machine, and only our machine

We had a CI pipeline running lint, type-checks, and tests on every change.
It failed. The error:

```
ModuleNotFoundError: No module named 'hypothesis'
```

`hypothesis` is a property-based testing library we use to check invariants
like "every probe score is between 0 and 1, no matter what garbage input
you throw at it." Our test suite imports it. Our `pyproject.toml`,
supposedly, declares it as a dependency.

Except it didn't. We'd installed it by hand on our own dev machine weeks
earlier while experimenting, and it had just... stayed there. Every local
test run worked. Every CI run, which installs from a clean slate, failed.

We fixed the dependency list and moved on. Then, days later, a different
mypy error showed up — this time about a `yaml.dump()` call returning the
wrong type. Same root cause: `types-PyYAML` was sitting in our local
environment from some earlier `pip install`, silently making local checks
pass while the declared dependency list stayed incomplete.

Twice was enough to make it a pattern. We now install into a genuinely
empty, disposable virtual environment before every release — not our
regular dev environment, which by definition has "stuff installed for
reasons nobody remembers" — specifically to catch this. It's not a clever
fix. It's just refusing to trust an environment that's been accumulating
side effects for months.

The best part of this saga, though, was a third bug that same investigation
surfaced. We had an optional `pandas` dependency for a visualization
feature. Nobody actually imported it anywhere — it was declared but dead
weight. Its only real effect was pulling in `numpy`, and it turned out
`numpy`'s latest type stubs use Python syntax that's only valid on 3.12+,
which broke mypy under our (correct, deliberate) "we support 3.10 and up"
configuration. We spent a good while trying clever mypy overrides to work
around it before realizing the actual fix was: delete the unused
dependency. `numpy` came along for a ride nobody asked for. Sometimes the
sophisticated fix is the wrong fix, and the boring one — stop depending on
something you don't use — is correct.

## Bug #2: a stray six characters broke a notebook

We ship example Jupyter notebooks alongside the library. One of them,
walking through how to write custom probes, opened fine locally and then
completely failed to load in Google Colab with this:

```
SyntaxError: Expected double-quoted property name in JSON
at position 15924 (line 403 column 87)
```

A notebook file is JSON under the hood. Somewhere in that file, six stray
characters — a leftover `\n",` fragment, almost certainly from copying a
line pattern used elsewhere in the file and not fully cleaning it up — had
turned valid JSON into garbage. Every other tool that had touched the file
along the way apparently tolerated or ignored it. Colab's parser, correctly,
did not.

The fix was a one-line deletion. The lesson was smaller but still real: if
you're generating structured file formats programmatically, validate them
the way the strictest real consumer will, not the way your own tooling
happens to be lenient. We now run every notebook through a proper
JSON-schema validator before considering it shippable, not just "does it
open in the one environment I tested."

## Bug #3 (which isn't really a bug — it's the interesting one)

This is the one we didn't expect, and it came from doing the most obvious,
least glamorous thing possible: actually running our own demo material
start to finish, for real, and reading the output instead of assuming it
would say what we expected.

We wrote a notebook simulating a week of gradual model drift — a suite with
four prompts and six probes, where a mock provider's odds of returning a
"drifted" response climbed a little more each simulated day. We expected
the score to start at 100% on day zero and slide downward as drift
increased. Instead:

```
Day 0 (drift=0%):  score=66.7%
Day 1 (drift=0%):  score=66.7%
Day 2 (drift=10%): score=66.7%
Day 3 (drift=20%): score=66.7%
```

66.7%. On the *clean* day. With *zero* injected drift.

Our first reaction was "that's a bug." It wasn't — not in the sense of
producing a wrong answer. Here's what was actually happening: we'd applied
all six probes to all four prompts, uniformly. One prompt asked for JSON.
One asked for a step-by-step explanation. One had a specific expected
keyword. But every probe ran against every prompt regardless of whether it
made sense to. The JSON-validity probe dutifully, correctly, permanently
failed against the three prompts that were never JSON in the first place.
Same for the step-by-step probe against prompts that were never asking for
steps. We hadn't given the tool a bad suite; we'd given it a suite where
three-sixths of the scoring made no sense for most of the content, and it
scored exactly what we told it to score.

We'd built the demo to *show off* the tool. Instead, running it revealed
that PromptCanary currently applies every probe in a suite to every prompt
in that suite — there's no way yet to say "only run this specific check
against that specific prompt." That's a real, immediate gap, and it's now
at the top of our list to fix, precisely because we found it by using the
thing, not by reviewing a design doc.

Here's the part that actually made us feel better about the core design,
though. Despite that noisy 66.7% baseline, when we compared each
subsequent day *against* that baseline — not against some ideal
100%, against the actual, imperfect, 66.7% starting point — the tool
correctly reported zero regressions for days one through three, and
correctly flagged its first `CRITICAL` alert exactly on day four, the
first day the simulated drift got bad enough to newly break three probes
that had been passing the whole time. No false alarms on the noisy-but-
stable days. A precise alert exactly when something new actually broke.

The comparison logic cares about *change*, not absolute score. A
persistently imperfect baseline turned out to degrade the tool's headline
number without degrading its actual job. We hadn't designed that
robustness property on purpose. We found it by accident, in our own demo,
because the demo was a little bit broken in a different way than we
thought.

## What we're taking from this

If you write software that touches LLMs, you already know outputs aren't
deterministic and providers don't announce changes. What surprised us
wasn't the concept — it's that building the *detector* for this problem ran
into a miniature version of the same problem: things that look fine in
isolation (a passing local check, a notebook that opens where you tested
it, a demo suite that seems reasonable) can hide an issue that only shows
up when something genuinely independent exercises the whole path — a clean
CI environment, a stricter parser, an actual multi-day execution instead of
a single hand-checked example.

The fix in every case was the same shape: stop trusting the convenient
assumption (my dev environment is representative, my test case is
representative, my demo is representative), and go verify against
something less forgiving. A disposable virtual environment. A real JSON
validator. A notebook that actually runs for eight simulated days instead
of one.

None of this is exotic. It's just easy to skip, right up until it isn't.

## Try it

```bash
pip install promptcanary
```

- **Docs:** [github.com/Mattral/PromptCanary](https://github.com/Mattral/PromptCanary)
- **Notebooks (open directly in Colab):** [github.com/Mattral/PromptCanary/tree/main/notebooks](https://github.com/Mattral/PromptCanary/tree/main/notebooks)
- **License:** MIT

If per-prompt probe scoping (the gap we found above) would unblock a real
use case for you, that's exactly the kind of issue we'd like to hear about.
