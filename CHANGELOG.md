# Changelog

All notable changes to **PromptCanary** are documented here.

This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Async parallel prompt execution (`suite.arun()`)
- Export connectors: Langfuse, Phoenix/Arize
- `SemanticSimilarityProbe` — embedding-based semantic drift probe (optional dep)
- S3/GCS baseline storage backend
- Optional web dashboard

---

## [0.2.2] — 2026-07-04

### Fixed

**Another CI-only mypy failure, caught the same way as v0.2.1's fixes: by installing strictly from `pyproject.toml` into a fresh virtualenv rather than trusting an accumulated local dev environment**

- `promptcanary/core/suite.py:190` — `mypy` reported `Returning Any from function declared to return "str"` on `CanarySuite.to_yaml_template()`'s call to `yaml.dump(...)`. Root cause: `types-PyYAML` was present in the local development environment from earlier ad hoc installs but was never declared in `pyproject.toml`'s `[dev]` extras, so a clean `pip install -e ".[dev]"` (exactly what CI runs) left `yaml.dump()` untyped (`Any`), which mypy strict mode correctly flagged against the function's declared `-> str` return type. Fixed by adding `types-PyYAML` to `[dev]`.
- `pyproject.toml` `[project.optional-dependencies.viz]` — removed `pandas`, which was declared but never actually imported or used anywhere in the codebase (only mentioned in a docstring). Its sole effect was pulling in `numpy` as a transitive dependency; `numpy` 2.5 ships type stubs using unconditional Python 3.12-only syntax (PEP 695 `type X = ...` statements), which fails to parse under this project's deliberate `python_version = "3.10"` mypy target — a hard stub-parse error that `ignore_missing_imports`, per-module `ignore_errors`, and `follow_imports = "skip"` overrides all failed to work around, since `pandas`'s own stubs import `numpy` internally regardless of override targeting. Removing the unused dependency fixes the root cause rather than working around the symptom. See `DECISION_LOG.md` ADR-011 for the full investigation and rejected alternatives.

### Process

- Established clean-room verification as standard practice before any release: install *only* what `pyproject.toml` declares into a fresh, empty virtualenv (never trust a long-lived local dev environment that has accumulated packages from earlier work) and run the full `ruff check` → `ruff format --check` → `mypy` → `pytest` loop, for every meaningful combination of optional extras (`[dev]` alone, matching CI exactly; `[dev,viz]` together, matching a full local contributor setup). Both this fix and v0.2.1's `hypothesis`/`typer[all]` fixes were found by this exact process — documented here so it isn't lost as tribal knowledge.

---

## [0.2.1] — 2026-07-03

### Fixed

**CI pipeline (all four checks now pass cleanly: ruff check, ruff format, mypy strict, pytest)**
- `pyproject.toml` — added `hypothesis`, `typer[all]` to `[dev]` extras; these were required by the test suite (`tests/unit/test_property_based.py`, `tests/unit/test_cli.py`) but missing from the dependency declaration, causing `ModuleNotFoundError` in CI
- `.github/workflows/ci.yml` — the `lint` job installed a hand-rolled dependency list instead of `pip install -e ".[dev]"`; this duplicated `pyproject.toml`'s dependencies by hand and had already drifted out of sync (missing `hypothesis`, `PyYAML` version pin, etc.). Now uses the single source of truth. Also extended lint/format checks to cover `tests/`, not just `promptcanary/`.
- `pyproject.toml` — removed redundant `typer[all]` from `[dev]` extras (triggered a deprecation warning on install: newer `typer` releases folded the `[all]` extra's contents — `rich`, `shellingham` — into core dependencies, and `rich` was already declared separately in the base `dependencies` list)
- **35 files reformatted** with `ruff format` — the formatter had never actually been run against the codebase; `ruff format --check` was failing on 22 of 35 source/test files despite `ruff check` (linting) passing
- **15 mypy strict-mode errors resolved** across 7 files:
  - Removed 8 redundant `# type: ignore[import-untyped]` comments — `pyproject.toml` already sets `ignore_missing_imports = true` project-wide, making per-line ignores dead code that mypy strict mode correctly flags as unused
  - `core/suite.py` — `_NoopContext` (the progress-bar no-op fallback) now implements `add_task()`/`update()` matching Rich's `Progress` API, returning a proper `TaskID`; this removes two `union-attr` errors and lets the `if show_progress:` guards around progress calls be deleted entirely, since both branches now share an interface
  - `core/probes/tool_use.py` — `_find_args()` now narrows through a local variable before returning, fixing a `no-any-return` error where `obj[k]` on an `Any`-typed dict couldn't be verified as `dict[str, Any]` despite the preceding `isinstance` check
  - `core/probes/reasoning.py` — `VerbosityProbe.evaluate()`'s `meta` dict is now explicitly typed `dict[str, Any]`; it holds both `int` (word counts) and `float` (ratio) values across branches, which mypy's inferred `dict[str, int]` from the first assignment couldn't accommodate
  - `cli.py` — the `report` command's format-detection branch (`DriftReport` vs `CanaryRunResult`) now declares explicit `obj: CanaryRunResult | DriftReport` and `reporter_obj: Reporter | DriftReporter` union types, since the two branches assign genuinely different, unrelated types to the same variable names

**Test coverage**
- `promptcanary/providers/litellm.py`: **21% → 100% coverage.** Added `tests/unit/test_litellm_provider.py` (29 tests) covering `LiteLLMProvider.complete()`'s full request-building and response-parsing logic — message construction (system prompt included/excluded), parameter forwarding (temperature, max_tokens, seed, extra_params), token usage extraction, `raw_response` capture, and all three error paths (missing `litellm` package, API call failure with status-code preservation, malformed response structure). Mocks `litellm.completion()` directly per ADR-008 — zero real network calls.
- Overall coverage: **89% → 92%** (264 tests, up from 235)

### Added

- `CODE_OF_CONDUCT.md` — full Contributor Covenant v2.1 text; previously referenced by `CONTRIBUTING.md` but the file itself didn't exist
- `.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/ISSUE_TEMPLATE/feature_request.yml`, `.github/ISSUE_TEMPLATE/config.yml` — structured issue forms, blank issues disabled, links to Discussions and the security policy
- `.github/PULL_REQUEST_TEMPLATE.md` — PR checklist matching `CONTRIBUTING.md`'s stated requirements
- `docs/integrations/llamaindex.md` — LlamaIndex integration guide (direct-LLM and query-engine-wrapping patterns, retrieval-drift-specific custom probe example); explicitly named in the original project guideline's integration list but was missing
- `docs/sync_root_docs.py` — now rewrites cross-references between mirrored root docs (e.g. a link to `CODE_OF_CONDUCT.md` inside `CONTRIBUTING.md` resolves to `code-of-conduct.md` in the mirrored copy) so `mkdocs build --strict` stays clean without touching the root source files' correct GitHub-relative links
- `examples/multi_provider.py` — runs the same suite across OpenAI, Anthropic, and Ollama simultaneously (with a `--mock` flag for no-API-key exploration), with a cross-provider comparison table and an interpretation guide for distinguishing provider-specific drift from harness-level regressions
- `examples/custom_probe_example.py` — three complete custom-probe patterns (`@probe` decorator, `BaseProbe` subclass, and a full production-grade JSON-API-contract probe with partial scoring) runnable end-to-end with no API key

### Changed

- `docs.yml` — added `CODE_OF_CONDUCT.md` to the docs-rebuild trigger paths
- `mkdocs.yml` — added Code of Conduct and LlamaIndex pages to nav

---

## [0.2.0] — 2026-06-30

### Added

**Tool Use probes** (new category, 4 probes)
- `ToolCallPresenceProbe` — detects presence/absence of any function call, with `auto`/`json`/`text` detection strategies
- `ToolCallNameProbe` — verifies the correct function is called, with alias support and partial credit (0.3) when the *wrong* function is called vs. none at all
- `ToolCallArgsProbe` — required/forbidden argument key validation, handles OpenAI's JSON-encoded `arguments` string format
- `ToolCallSchemaProbe` — full structural validation combining name (40%) + args (40%) + arg types (20%) into one weighted score

**Trend visualization** (`promptcanary.utils.visualization`)
- `plot_score_history()` — overall score and pass rate over time
- `plot_probe_heatmap()` — per-probe score grid across snapshots, reveals which probe regresses first
- `plot_drift_timeline()` — regression count and severity over a series of `compare()` calls
- Zero-dependency ASCII fallback (sparklines, tables) always available; optional Plotly HTML rendering via `pip install promptcanary[viz]`
- Graceful degradation: `mode="auto"` tries Plotly, falls back to ASCII with no functionality lost

**Property-based testing** (Hypothesis)
- Score invariants: all probe scores remain in `[0.0, 1.0]` under arbitrary input
- `CanaryRunResult.overall_score` proven to equal the mean of all probe scores
- `DriftReport.overall_score_delta` proven to equal `current − baseline` exactly
- Identical-run comparisons proven to never produce false-positive regressions
- `JsonValidityProbe` proven binary (never partial) across arbitrary text and arbitrary valid JSON
- `FileBaselineStore` round-trip (`save` → `load`) proven lossless for suite name, scores, and pass/fail state
- Regression and improvement flags proven mutually exclusive

**CLI test coverage**
- Full `typer.testing.CliRunner` coverage for `init`, `run`, `compare`, `baselines`, `report`, `version`
- Stub provider pattern for testing without real network calls

**Documentation site** (MkDocs Material)
- 23-page documentation site: getting started, core concepts, full probe reference, per-provider guides, CI/CD guides, integration guides (LangChain, FastAPI), visualization guide, CLI reference, auto-generated API reference via `mkdocstrings`
- `docs/sync_root_docs.py` — keeps `docs/decision-log.md`, `docs/contributing.md`, `docs/changelog.md` in sync with their root-level sources of truth
- `.github/workflows/docs.yml` — auto-deploys to GitHub Pages on changes to docs or docstrings
- Strict-mode build verified (zero broken links, zero missing nav references)

**Notebooks**
- `notebooks/analyzing_drift_trends.ipynb` — simulates 7 days of gradual provider drift, identifies the first-failing probe, demonstrates all three visualization types
- `notebooks/ci_integration.ipynb` — GitHub Actions patterns, multi-provider matrix, cost-aware scheduling strategy, baseline promotion workflow, current provider reference table

### Changed

- **Updated all model references to current generation** (per community feedback): `openai/gpt-5.4`/`gpt-5.5` replace `gpt-4o`; `anthropic/claude-sonnet-4-6`/`claude-opus-4-8` replace `claude-3-5-sonnet-20241022`; `gemini/gemini-3.5-flash`/`gemini-3.1-pro` replace `gemini-1.5-pro`; `xai/grok-4` replaces `grok-beta`. Applied across README, CLI help text, `examples/`, notebooks, and GitHub Actions workflows.
- **README — Supported Providers section rewritten** with a comparison table covering cost tier and API key requirements per provider, explicit free/local Ollama models (`qwen3.6:27b`, `deepseek-r1:14b`, `gpt-oss:20b`) presented as first-class options rather than an afterthought, and a rationale section on why free local models are valuable as zero-cost canaries
- **README — Python SDK section** now shows Gemini and Ollama usage alongside OpenAI, not just a single-provider example
- Probe count updated throughout docs: 15 → 19 (addition of the Tool Use category)

### Fixed

- `@probe` decorator now correctly satisfies the `BaseProbe` ABC contract (previously relied on a post-hoc method assignment that worked but was fragile under `abc.ABCMeta`'s abstract-method check in edge cases); rewritten using `type()` to construct the class with `evaluate` already bound
- `ToolCallArgsProbe._extract_arg_keys()` now correctly parses OpenAI's `tool_calls[].function.arguments` format, where `arguments` is a JSON-*encoded string* rather than a nested object

---

## [0.1.0] — 2026-06-29

### Added

**Core pipeline**
- `CanarySuite` — orchestrates prompts, probes, and provider calls with progress display
- `CanarySuite.from_yaml()` — load a full suite from a `canary.yaml` config file
- `CanarySuite.to_yaml_template()` — serialise back to YAML for inspection
- `compare()` — compare a `CanaryRunResult` against a `BaselineSnapshot` to produce a `DriftReport`
- `FileBaselineStore` — local JSON baseline storage with save, load, load_latest, list, delete

**Pydantic v2 models** (fully typed, frozen where appropriate)
- `CanaryPrompt` — prompt with id, text, tags, expected_keywords, system_prompt override
- `ProviderConfig` — provider + temperature + seed + extra_params
- `LLMResponse` — raw provider response with token counts, latency, finish_reason
- `ProbeResult` — structured result with score, pass/fail, details, metadata
- `CanaryRunResult` — aggregated run with derived properties (overall_score, pass_rate, by_category)
- `BaselineSnapshot` — versioned snapshot with schema_version field
- `ProbeComparison` — side-by-side comparison for one probe × one prompt
- `DriftReport` — full drift analysis with severity heuristic and human-readable summary

**Built-in probes (15 probes across 4 categories)**

*Format & Structure*
- `JsonValidityProbe` — is the response valid JSON?
- `JsonSchemaProbe` — required/forbidden JSON keys, partial scoring
- `JsonKeyOrderProbe` — LCS-based key order comparison
- `ResponseLengthProbe` — char-count bounds + drift scoring vs baseline
- `MarkdownHeaderProbe` — expected markdown section headers
- `KeywordPresenceProbe` — required/forbidden keyword matching
- `ExpectedKeywordsProbe` — uses keywords declared on `CanaryPrompt`

*Reasoning Style*
- `StepByStepProbe` — detects step-by-step reasoning signals
- `VerbosityProbe` — word-count drift with tolerance band
- `ConfidenceLanguageProbe` — hedging vs. confident language heuristic
- `DirectAnswerProbe` — preamble detection ("Sure!", "Great question!", "As an AI…")

*Safety & Refusal*
- `RefusalProbe` — detects LLM refusals vs compliance
- `SafetyLanguageProbe` — detects disclaimer/caveat injection

*Factual*
- `FactualConsistencyProbe` — exact/contains/startswith match against known value
- `SentimentProbe` — lightweight keyword-based tone probe

**Probe extension API**
- `BaseProbe` ABC — `evaluate(prompt, response) → ProbeResult`
- `@probe` decorator — turn any function into a registered, nameable probe
- Global probe registry with `get_probe()` and `get_probe_registry()`

**Provider layer**
- `BaseLLMProvider` ABC — implement `complete()` for any backend
- `LiteLLMProvider` — unified adapter for OpenAI, Anthropic, Google, Ollama, vLLM, and 100+ more
- `ProviderError` — normalised error type with model_id, status_code, raw_error

**CLI (`promptcanary`)**
- `promptcanary init <name>` — scaffold suite directory with `canary.yaml`, `.env.example`, `README.md`
- `promptcanary run` — run suite, print Rich terminal report, optionally save baseline and emit JSON/MD/HTML
- `promptcanary compare` — compare to saved baseline, detect drift, CI exit code support
- `promptcanary baselines` — list saved baselines in a rich table
- `promptcanary report` — offline report generation from saved JSON
- `promptcanary version` — print installed version

**Reporting**
- Terminal (Rich): colour-coded table, per-category scores, duration, run ID
- Markdown: GitHub-flavoured, PR-comment-ready, per-probe table + category stats
- HTML: self-contained dark-theme report with score bars
- JSON: fully serialisable via Pydantic `model_dump(mode="json")`

**Drift reporting**
- Terminal: severity-coloured panel, regressions table with delta
- Markdown: structured with metrics table, regressions, improvements sections
- HTML: interactive comparison table
- Severity heuristic: NONE / LOW / MEDIUM / HIGH / CRITICAL based on regression rate and delta

**GitHub Actions**
- `ci.yml` — lint (ruff), type-check (mypy), test matrix (Python 3.10/3.11/3.12 × ubuntu/macos/windows), build + PyPI release via Trusted Publishing
- `promptcanary.yml` — weekly scheduled drift check, PR comment integration, GitHub issue on drift, artifact upload

**Testing**
- `tests/conftest.py` — shared fixtures: MockLLMProvider, canonical prompts/responses, temp dirs
- `tests/unit/test_models.py` — comprehensive Pydantic model tests
- `tests/unit/probes/test_format_probes.py` — all format probes, happy + failure + edge cases
- `tests/unit/probes/test_reasoning_safety_probes.py` — reasoning and safety probe coverage
- `tests/unit/test_suite_comparator_storage.py` — suite, comparator, FileBaselineStore, Reporter
- `tests/integration/test_full_pipeline.py` — end-to-end run→baseline→compare workflow

**Packaging**
- `pyproject.toml` with Hatchling build backend, optional extras `[viz]`, `[dev]`, `[all]`
- `py.typed` marker (PEP 561)
- `promptcanary` console script entry point
- ruff + mypy strict configuration

**Documentation & examples**
- `README.md` — full DX-first documentation with quickstart, API reference, CI setup
- `CHANGELOG.md` — this file
- `DECISION_LOG.md` — architecture decision records
- `CONTRIBUTING.md` — contribution guide with commit conventions
- `examples/canary.yaml` — production-grade example suite (8 prompts, 7 probes)
- `examples/quickstart.py` — standalone runnable example

---

## Versioning Policy

- **MAJOR** (1.x.x): breaking changes to the public API (models, probe interface, CLI)
- **MINOR** (0.x.0): new features, new probes, new providers — backward compatible
- **PATCH** (0.1.x): bug fixes, documentation improvements, test additions

---

[Unreleased]: https://github.com/promptcanary/promptcanary/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/promptcanary/promptcanary/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/promptcanary/promptcanary/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/promptcanary/promptcanary/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/promptcanary/promptcanary/releases/tag/v0.1.0
