# Decision Log — PromptCanary

Architecture Decision Records (ADRs) for PromptCanary v0.1.

Each record documents a significant design decision, the alternatives considered,
and the rationale. This is a living document — update it when decisions change.

---

## ADR-001: Use LiteLLM as the Provider Abstraction Layer

**Date**: 2026-06-29
**Status**: Accepted
**Deciders**: Core team

### Context
PromptCanary needs to support many LLM providers (OpenAI, Anthropic, Google, local models).
We needed to decide whether to write provider-specific adapters or use an abstraction library.

### Options Considered
1. **Write individual adapters** — full control, no external dependency, but high maintenance burden.
2. **LiteLLM** — community-maintained library with 100+ providers behind a unified OpenAI-compatible interface.
3. **Direct OpenAI SDK only** — simpler, but excludes Anthropic, Google, and local models.

### Decision
Use **LiteLLM** as the default and recommended provider layer.

### Rationale
- Single interface covers all major providers and local models (Ollama, vLLM).
- Active maintenance with fast updates when providers change their APIs.
- Users who already use LiteLLM have zero learning curve.
- Our `BaseLLMProvider` ABC means users can bypass LiteLLM entirely for custom backends.

### Consequences
- LiteLLM is a required dependency (not optional).
- Provider-specific edge cases (e.g. streaming, function calling schemas) are abstracted away,
  which is acceptable for canary testing where we care about content, not transport details.
- When LiteLLM is slow to update for a new provider, users can implement `BaseLLMProvider` directly.

---

## ADR-002: Pydantic v2 for All Data Models

**Date**: 2026-06-29
**Status**: Accepted

### Context
All data flowing through PromptCanary needs to be validated, serialisable to JSON,
and typed for excellent IDE support.

### Options Considered
1. **Dataclasses** — stdlib, no validation, manual serialisation.
2. **attrs** — fast, no JSON support built-in.
3. **Pydantic v1** — proven, but being deprecated.
4. **Pydantic v2** — fastest Rust-backed validator, excellent JSON support, modern API.
5. **TypedDict** — typing only, no validation.

### Decision
**Pydantic v2** for all domain models.

### Rationale
- `model_dump(mode="json")` gives free JSON serialisation.
- Field validators and `ConfigDict(frozen=True)` enforce correctness.
- `model_validate()` handles deserialization from stored JSON.
- Best IDE support and type inference of any option.
- The v2 API is stable and the clear long-term choice.

### Consequences
- `pydantic>=2.5.0` is a required dependency.
- Some patterns differ from v1 (e.g. `model_config = ConfigDict(...)` vs `class Config:`).
- Frozen models use `model_copy(update=...)` to "mutate" — slightly verbose but correct.

---

## ADR-003: Sequential Provider Calls (Not Async-Parallel)

**Date**: 2026-06-29
**Status**: Accepted (revisit at v0.2)

### Context
Running N prompts × M probes could be parallelised to reduce wall-clock time.

### Options Considered
1. **Sequential** — simple, predictable, easy to debug, no concurrency bugs.
2. **asyncio parallel** — faster but more complex, requires async provider interface.
3. **ThreadPoolExecutor** — parallel with sync code, but LiteLLM isn't always thread-safe.

### Decision
**Sequential** for v0.1. Add `suite.arun()` (async) post-MVP.

### Rationale
- Most canary suites are small (5–20 prompts). Sequential is fast enough.
- Deterministic run order makes debugging and logging easier.
- No async complexity in the core run loop means simpler onboarding.
- Provider rate limits often make parallelism counterproductive anyway.

### Consequences
- Large suites (100+ prompts) may be slow. Document this and suggest batching.
- `suite.arun()` is reserved for the async interface in v0.2.

---

## ADR-004: Local JSON File Storage for Baselines (MVP)

**Date**: 2026-06-29
**Status**: Accepted

### Context
Baselines need to be stored somewhere accessible. Options range from local files
to cloud object stores to databases.

### Options Considered
1. **Local JSON files** — zero dependencies, git-committable, works offline.
2. **SQLite** — structured queries, local, more complex.
3. **S3/GCS** — cloud-native, requires credentials and network.
4. **PostgreSQL** — powerful but heavy for a CLI tool.

### Decision
**Local JSON files** for MVP, with `BaselineStore` ABC enabling future backends.

### Rationale
- Teams can commit baselines to their repo alongside `canary.yaml` — gives version history for free.
- Zero infrastructure required to get started.
- The `BaselineStore` ABC (not yet exposed, but architecturally planned) allows cloud backends later.
- File naming convention (`{suite}__{model}__{timestamp}_{id}.json`) enables `load_latest()` via sorting.

### Consequences
- Large teams sharing baselines need a shared filesystem or to commit to git.
- No query capability (e.g., "all baselines for model X last month") beyond list/filter.
- S3/GCS backends are the obvious post-MVP extension.

---

## ADR-005: Rich + Typer for CLI

**Date**: 2026-06-29
**Status**: Accepted

### Options Considered
1. **argparse (stdlib)** — no external deps, verbose, no colour.
2. **Click** — popular, good, but lower DX than Typer.
3. **Typer + Rich** — type-annotated CLI, automatic help, beautiful terminal output.

### Decision
**Typer** for CLI structure, **Rich** for all terminal rendering.

### Rationale
- Typer's type-annotation-based interface eliminates boilerplate.
- Rich produces world-class terminal output (tables, panels, progress bars) with minimal code.
- The two libraries are designed to work together.
- Both are battle-tested and widely used in the Python ecosystem.

### Consequences
- `typer` and `rich` are required runtime dependencies.
- Typer currently wraps Click, so Click is an indirect dependency.

---

## ADR-006: Score Range 0.0–1.0 with `passed` Boolean

**Date**: 2026-06-29
**Status**: Accepted

### Context
Each `ProbeResult` needs to communicate quality. Should we use pass/fail only,
a numeric score, or a letter grade?

### Decision
**Both**: a normalised float score (0.0–1.0) AND a boolean `passed`.

### Rationale
- `passed` is unambiguous for CI gating (`fail-on-failure`).
- `score` enables partial credit (e.g., 4 of 5 required JSON keys present → 0.8).
- The score enables trend tracking and alerting on gradual degradation.
- `DriftReport.severity` is derived from score deltas, not just pass/fail.

### Consequences
- Probe authors must populate both fields and keep them semantically consistent.
- The comparator's `regression_threshold` prevents noise from triggering false alarms.

---

## ADR-007: Probe Registration via Metaclass-Free Auto-Registry

**Date**: 2026-06-29
**Status**: Accepted

### Context
User-defined probes need to be discoverable by name (for YAML config loading).

### Options Considered
1. **Manual registration** — `register_probe(MyProbe)` call required.
2. **Entry points** — pip plugin system, heavy for an MVP.
3. **`__init_subclass__` auto-registry** — Python 3.6+ feature, zero boilerplate.

### Decision
Use `__init_subclass__` in `BaseProbe` to auto-register any concrete subclass with a non-empty `probe_id`.

### Rationale
- Zero user friction: define the class → it's registered.
- No metaclass magic — plain Python.
- Works for built-ins and user-defined probes equally.
- The `@probe` decorator wraps the same mechanism for functional-style definition.

### Consequences
- Probes are registered at import time. Users must ensure probe modules are imported before calling `get_probe()`.
- For YAML-loaded custom probes, users must import their module before calling `CanarySuite.from_yaml()`.
- Abstract probes (those with `@abc.abstractmethod`) are not registered (correct behaviour via `inspect.isabstract`).

---

## ADR-008: No LLM Calls in the Test Suite

**Date**: 2026-06-29
**Status**: Accepted

### Context
Should tests make real LLM API calls?

### Decision
**No real API calls in any test.** All tests use `MockLLMProvider` with deterministic, pre-defined responses.

### Rationale
- Tests must be reproducible, fast, and free of external dependencies.
- Real API calls would require secrets in CI, add cost, and introduce flakiness.
- Integration tests with real providers should be an opt-in, separate test suite (`tests/live/`).
- The `MockLLMProvider` in `conftest.py` is realistic enough to exercise the full pipeline.

### Consequences
- No test coverage of real provider response parsing subtleties.
- `tests/live/` (not yet created) will contain real-provider smoke tests run manually or with a dedicated secret.

---

*Last updated: 2026-06-29 (v0.1.0)*
