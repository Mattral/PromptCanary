# CLI Reference

```bash
promptcanary [COMMAND] [OPTIONS]
```

Run `promptcanary --help` or `promptcanary COMMAND --help` for the
authoritative, always-current option list.

## `promptcanary init`

Scaffold a new canary suite directory.

```bash
promptcanary init [NAME] [--force]
```

| Option | Default | Description |
|--------|---------|--------------|
| `NAME` | `my-canary-suite` | Directory and suite name. |
| `--force, -f` | off | Overwrite an existing directory. |

Creates `canary.yaml`, `baselines/`, `.env.example`, and `README.md`.

## `promptcanary run`

Run a canary suite against an LLM provider.

```bash
promptcanary run --provider PROVIDER [OPTIONS]
```

| Option | Default | Description |
|--------|---------|--------------|
| `--config, -c` | `canary.yaml` | Path to the suite config. |
| `--provider, -p` | *(required)* | LiteLLM model string. |
| `--temperature, -t` | `0.0` | Sampling temperature. |
| `--max-tokens` | `1024` | Max tokens per response. |
| `--seed` | `42` | Reproducibility seed. |
| `--save-baseline, -s` | off | Save this run as a new baseline. |
| `--baseline-dir` | `baselines` | Baseline storage directory. |
| `--output-json, -o` | -- | Save raw JSON results. |
| `--output-md` | -- | Save a Markdown report. |
| `--output-html` | -- | Save an HTML report. |
| `--fail-on-failure` | off | Exit 1 if any probe fails. |
| `--no-progress` | off | Disable the Rich progress bar. |

## `promptcanary compare`

Compare a current run against a saved baseline.

```bash
promptcanary compare [OPTIONS]
```

| Option | Default | Description |
|--------|---------|--------------|
| `--config, -c` | `canary.yaml` | Suite config (for fresh runs). |
| `--provider, -p` | -- | Run a fresh query against this provider. |
| `--baseline, -b` | *(latest)* | Path to a specific baseline JSON file. |
| `--current` | -- | Path to a saved current-run JSON file. |
| `--baseline-dir` | `baselines` | Baseline storage directory. |
| `--output-md` | -- | Save a Markdown drift report. |
| `--output-html` | -- | Save an HTML drift report. |
| `--fail-on-drift` | off | Exit 1 if drift is detected. |
| `--no-progress` | off | Disable progress display. |

Provide either `--provider` (runs fresh) or `--current` (uses a saved
file) -- at least one is required.

## `promptcanary baselines`

List saved baseline snapshots.

```bash
promptcanary baselines [--dir DIR] [--suite SUITE]
```

## `promptcanary report`

Generate a report from a saved JSON file -- works offline, no provider call.

```bash
promptcanary report INPUT [OPTIONS]
```

| Option | Default | Description |
|--------|---------|--------------|
| `--format, -f` | `terminal` | `terminal` \| `markdown` \| `html` \| `json`. |
| `--output, -o` | -- | Save to this path instead of printing. |
| `--open` | off | Open HTML output in your default browser. |

Auto-detects whether the input JSON is a `CanaryRunResult` or a
`DriftReport`.

## `promptcanary version`

```bash
promptcanary version
```

Prints the installed PromptCanary version.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success -- no failures or drift detected (or flags not set). |
| `1` | Probe failure (`--fail-on-failure`), drift detected (`--fail-on-drift`), or a configuration/runtime error. |
