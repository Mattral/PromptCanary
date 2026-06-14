# Contributing to PromptCanary

Thank you for your interest in contributing! PromptCanary is community-driven
and we deeply value every contribution — whether it's a new probe, a bug fix,
a documentation improvement, or a community canary suite.

---

## Code of Conduct

This project follows the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/),
reproduced in full in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
By participating you agree to uphold these standards. Reports of unacceptable
behaviour can be sent to conduct@promptcanary.dev (placeholder).

---

## Quick Orientation

```
promptcanary/
├── promptcanary/
│   ├── core/
│   │   ├── models.py       ← Pydantic data layer — start here to understand the types
│   │   ├── suite.py        ← CanarySuite orchestrator
│   │   ├── comparator.py   ← Drift comparison engine
│   │   ├── reporter.py     ← Terminal / MD / HTML / JSON output
│   │   └── probes/         ← All built-in probes live here
│   ├── providers/          ← LLM provider adapters
│   ├── storage/            ← Baseline storage backends
│   └── cli.py              ← Typer CLI
├── tests/
│   ├── unit/               ← Fast, no I/O, mocked providers
│   └── integration/        ← Full pipeline tests (still mocked)
├── examples/               ← Reference canary.yaml and scripts
└── docs/                   ← MkDocs documentation source
```

---

## Setting Up Your Environment

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/promptcanary.git
cd promptcanary

# 2. Create a virtual environment (Python 3.10+)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"

# 4. Verify setup
pytest tests/ -v
promptcanary version
```

---

## Making Changes

### Branches

| Type | Branch name |
|------|-------------|
| Feature | `feat/my-feature` |
| Bug fix | `fix/issue-description` |
| Docs | `docs/topic` |
| Refactor | `refactor/scope` |

### Commit Conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(probes): add SemanticSimilarityProbe
fix(comparator): handle empty baseline gracefully
docs(readme): add OpenAI quickstart example
test(storage): cover FileBaselineStore.delete()
refactor(reporter): extract HTML builder to helper module
chore(deps): bump pydantic to 2.7.0
```

**Types**: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`, `ci`

---

## Writing a New Probe

Probes are the heart of PromptCanary. Adding a new probe is the most impactful
contribution you can make.

### Step 1 — Choose the right module

| What you're detecting | Module |
|-----------------------|--------|
| Output format, structure, keys | `promptcanary/core/probes/format.py` |
| Reasoning style, verbosity, preamble | `promptcanary/core/probes/reasoning.py` |
| Refusals, disclaimers, safety behaviour | `promptcanary/core/probes/safety.py` |
| Custom domain (new file) | `promptcanary/core/probes/your_domain.py` |

### Step 2 — Implement the probe

```python
# In the appropriate module:

class MyNewProbe(BaseProbe):
    """One-line summary.

    Longer description of what this probe detects and why.

    Args:
        param: Description of the parameter.

    Score:
        1.0 when condition X is met; 0.0 when not. Partial scores for Y.

    Example::

        probe = MyNewProbe(param="value")
        result = probe(prompt, response)
        print(result.score, result.details)
    """

    probe_id = "my_new_probe"           # unique snake_case ID
    name = "My New Probe"               # human-readable
    category = ProbeCategory.CUSTOM     # or FORMAT, REASONING, SAFETY, FACTUAL
    description = "Detects XYZ."

    def __init__(self, param: str = "default") -> None:
        self.param = param

    def evaluate(self, prompt: CanaryPrompt, response: LLMResponse) -> ProbeResult:
        passed = self.param in response.content
        return self._make_result(
            prompt.id,
            passed=passed,
            score=1.0 if passed else 0.0,
            details=f"Param '{self.param}' {'found' if passed else 'not found'}.",
            metadata={"param": self.param},
        )
```

### Step 3 — Export it

Add to `promptcanary/core/probes/__init__.py`:
```python
from promptcanary.core.probes.your_module import MyNewProbe
__all__ = [..., "MyNewProbe"]
```

And to `promptcanary/__init__.py` if it's a core probe.

### Step 4 — Write tests

```python
# tests/unit/probes/test_your_probe.py

class TestMyNewProbe:
    def test_passes_when_param_found(self) -> None: ...
    def test_fails_when_param_missing(self) -> None: ...
    def test_score_is_1_on_pass(self) -> None: ...
    def test_metadata_contains_param(self) -> None: ...
    def test_probe_id_and_category(self) -> None: ...
```

Tests must:
- Cover happy path, failure path, and at least one edge case
- Use `MockLLMProvider` or pre-built `LLMResponse` objects — **no real API calls**
- Assert both `passed` and `score`

### Step 5 — Update `CHANGELOG.md`

Add to `[Unreleased]` → `Added`.

---

## PR Checklist

Before opening a PR, please ensure:

- [ ] All existing tests pass: `pytest tests/`
- [ ] New tests added (aim for ≥80% coverage on new code)
- [ ] Lint passes: `ruff check promptcanary/ tests/`
- [ ] Format passes: `ruff format --check promptcanary/ tests/`
- [ ] Type check passes: `mypy promptcanary/ --ignore-missing-imports`
- [ ] Docstrings on all public classes/methods
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] PR description explains the **what** and the **why**

These are exactly the checks `.github/workflows/ci.yml` runs — if they pass
locally, CI will pass too, **provided you installed dependencies the same
way CI does** (see Release Checklist below for why this matters).

---

## Release Checklist

Before tagging a release, verify in a **completely clean environment** —
not your regular development virtualenv, which accumulates packages from
unrelated `pip install` commands over time and can mask a missing
dependency declaration in `pyproject.toml`. This exact failure mode has
bitten this project twice (see `CHANGELOG.md` v0.2.1 and v0.2.2): a check
passed locally only because a package happened to already be installed,
then failed in CI's genuinely clean environment.

```bash
# 1. Create a throwaway virtualenv — do NOT reuse your dev environment
python3 -m venv /tmp/release_check
source /tmp/release_check/bin/activate

# 2. Install ONLY what pyproject.toml declares — mirrors CI exactly
pip install -e ".[dev]"

# 3. Run every check CI runs, in order
ruff check promptcanary/ tests/
ruff format --check promptcanary/ tests/
mypy promptcanary/ --ignore-missing-imports
pytest tests/

# 4. Also verify the full extras combination a contributor might install
pip install -e ".[dev,viz]"
mypy promptcanary/ --ignore-missing-imports
pytest tests/

# 5. Verify the package builds and imports cleanly
python -m build
pip install dist/*.whl --force-reinstall
python -c "import promptcanary; print(promptcanary.__version__)"

deactivate
rm -rf /tmp/release_check
```

If all of these pass in the throwaway environment, CI will pass on the
same commit — with no surprises from packages that were only ever
installed by accident during earlier development.

---

## What We're Looking For

### High-value contributions

- **New probes** — especially for specific domains (legal, medical, coding agents, tool use)
- **Community canary suites** — example `canary.yaml` files for specific use cases
- **Bug fixes** with reproduction test cases
- **Documentation** — especially tutorials and integration guides
- **Storage backends** — S3, GCS, database adapters

### Good First Issues

Look for issues tagged `good-first-issue` on GitHub. These are scoped,
well-described, and have guidance on where to start.

---

## Probe Quality Bar

A probe accepted into the core library must:
1. Have a clear, unique `probe_id` (snake_case)
2. Have a meaningful docstring with Args, Score, and Example sections
3. Return partial scores (not just binary) where semantically meaningful
4. Never raise exceptions — wrap risky logic in try/except
5. Pass all CI checks

---

## Questions?

Open a [GitHub Discussion](https://github.com/promptcanary/promptcanary/discussions)
or drop into the issues. We aim to respond within 48 hours.

---

*Thank you for making PromptCanary better for everyone.* 🐦
