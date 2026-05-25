# Installation

## Requirements

- Python 3.10 or later
- An API key for at least one provider (OpenAI, Anthropic, Gemini, xAI) **or**
  a local installation of [Ollama](https://ollama.ai) for free, offline testing

## Install from PyPI

```bash
pip install promptcanary
```

This installs the core package with the CLI (`promptcanary`), the SDK, and
the LiteLLM provider adapter.

## Optional Extras

### Visualization (`[viz]`)

Adds Plotly and pandas for interactive HTML trend charts. Without this extra,
trend visualization falls back to terminal ASCII sparklines automatically —
no functionality is lost, just the interactive HTML output.

```bash
pip install "promptcanary[viz]"
```

### Development (`[dev]`)

For contributors — adds pytest, ruff, mypy, and hypothesis.

```bash
pip install "promptcanary[dev]"
```

### Everything (`[all]`)

```bash
pip install "promptcanary[all]"
```

## Verify Installation

```bash
promptcanary version
```

```python
import promptcanary
print(promptcanary.__version__)
```

## Set Up a Provider

=== "OpenAI"

    ```bash
    export OPENAI_API_KEY=sk-...
    ```

=== "Anthropic"

    ```bash
    export ANTHROPIC_API_KEY=sk-ant-...
    ```

=== "Google Gemini"

    ```bash
    export GEMINI_API_KEY=...
    ```

=== "Ollama (local, free)"

    ```bash
    # Install Ollama: https://ollama.ai
    ollama pull qwen3.6:27b
    # No API key needed — promptcanary run --provider ollama/qwen3.6:27b
    ```

## Next Steps

Continue to the [Quick Start](quickstart.md) to run your first canary suite.
