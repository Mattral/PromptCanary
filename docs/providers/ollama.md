# Local Models via Ollama

Running canaries against a local, open-weight model costs nothing and
requires no API key — ideal for high-frequency, zero-cost drift detection
as the first layer of a multi-provider strategy.

## Setup

```bash
# Install Ollama: https://ollama.ai
ollama pull qwen3.6:27b
```

```python
from promptcanary import LiteLLMProvider

provider = LiteLLMProvider("ollama/qwen3.6:27b", temperature=0.0)
```

No environment variable is required — LiteLLM talks to your local Ollama
server (default `http://localhost:11434`) automatically.

## Recommended Models

| Use case | Model string | Notes |
|----------|---------------|-------|
| Best overall | `ollama/qwen3.6:27b` | Strong general-purpose, Apache 2.0 license. |
| Best coding | `ollama/qwen3-coder:30b` | 256K context, optimised for code tasks. |
| Best reasoning | `ollama/deepseek-r1:14b` | Chain-of-thought focused, MIT licensed. |
| Smallest footprint | `ollama/gpt-oss:20b` | OpenAI's open-weight release, ~16GB RAM. |
| Fastest / lightest | `ollama/llama3.3:8b` | Runs comfortably on 8GB RAM. |

Hardware requirements scale with parameter count — check each model's
page on [ollama.com/library](https://ollama.com/library) for exact RAM
requirements before pulling.

## CLI Usage

```bash
promptcanary run --provider ollama/qwen3.6:27b --save-baseline
promptcanary compare --provider ollama/qwen3.6:27b --fail-on-drift
```

## CI Usage (GitHub Actions)

```yaml
- name: Set up Ollama
  run: |
    curl -fsSL https://ollama.ai/install.sh | sh
    ollama pull qwen3.6:27b
    ollama serve &
    sleep 5

- run: pip install promptcanary

- name: Run canary
  run: |
    promptcanary run --provider ollama/qwen3.6:27b --output-json results.json
    promptcanary compare --current results.json --baseline baselines/qwen-latest.json --fail-on-drift
```

!!! tip "Why local models matter for cost-aware drift detection"
    Because local models have zero per-call cost, they're the only option
    that makes sense to run continuously (e.g. hourly). Pair an hourly
    local-model check with weekly checks against your paid providers — see
    [Multi-Provider Matrix](../ci-cd/multi-provider.md) for the full
    scheduling strategy.

## Self-Hosted Alternative: vLLM

For higher-throughput self-hosted serving (e.g. behind a load balancer),
use `hosted_vllm/`:

```python
provider = LiteLLMProvider("hosted_vllm/meta-llama/Llama-3.3-8B-Instruct")
```

This requires running your own vLLM server — see the
[vLLM documentation](https://docs.vllm.ai) for setup.
