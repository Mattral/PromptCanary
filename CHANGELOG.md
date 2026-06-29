# Changelog

All notable changes to **PromptCanary** are documented here.

This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Async parallel prompt execution (`suite.arun()`)
- Trend visualization: score history charts over time
- Export connectors: Langfuse, Phoenix/Arize
- Web dashboard (lightweight Gradio/Streamlit)
- Multi-model comparison mode (`suite.compare_providers([...])`)
- S3/GCS baseline storage backend
- `ToolCallProbe` — detects changes in tool-calling patterns (function name, arg schema)
- `SemanticSimilarityProbe` — embedding-based semantic drift probe (optional dep)
- Property-based tests for comparator logic
- MkDocs Material documentation site

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

[Unreleased]: https://github.com/promptcanary/promptcanary/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/promptcanary/promptcanary/releases/tag/v0.1.0
