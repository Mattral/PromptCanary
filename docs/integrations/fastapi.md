# FastAPI Apps

Two common patterns: pre-deployment gating in CI, and an in-app health
endpoint that surfaces the latest drift status.

## Pre-Deployment Gate

Block a deploy if the LLM behind your FastAPI app has drifted:

```python
# scripts/pre_deploy_check.py
import sys
from promptcanary import CanarySuite, LiteLLMProvider, FileBaselineStore, compare
from promptcanary.core.models import DriftSeverity

_SEVERITY_RANK = {
    DriftSeverity.NONE: 0, DriftSeverity.LOW: 1,
    DriftSeverity.MEDIUM: 2, DriftSeverity.HIGH: 3, DriftSeverity.CRITICAL: 4,
}

def main() -> int:
    suite = CanarySuite.from_yaml("canary.yaml")
    provider = LiteLLMProvider("openai/gpt-5.4")
    store = FileBaselineStore("baselines/")

    result = suite.run(provider, show_progress=False)
    baseline = store.load_latest(suite_name=suite.name, model_id=provider.config.model_id)
    drift = compare(baseline, result)

    print(drift.summary)
    if _SEVERITY_RANK[drift.severity] > _SEVERITY_RANK[DriftSeverity.LOW]:
        print("Drift exceeds threshold -- blocking deploy.")
        return 1

    print("Safe to deploy.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

```yaml
# In your deploy workflow, before the deploy step:
- run: python scripts/pre_deploy_check.py
```

## Health Endpoint

Expose the most recent drift status as a FastAPI endpoint -- useful for
dashboards or uptime monitoring integrations:

```python
from fastapi import FastAPI
from promptcanary.storage.file import FileBaselineStore

app = FastAPI()
store = FileBaselineStore("baselines/")

@app.get("/health/canary")
def canary_health():
    baselines = store.list_baselines(suite_name="production-agent")
    if not baselines:
        return {"status": "unknown", "reason": "no baselines saved yet"}
    latest = baselines[0]
    return {
        "status": "ok",
        "suite": latest["suite_name"],
        "model": latest["model_id"],
        "last_checked": latest["created_at"],
    }
```

!!! note
    This endpoint reports the *last saved baseline*, not a live drift
    check -- running a full canary suite on every health-check request
    would be slow and costly. Run drift checks on a schedule (see
    [GitHub Actions](../ci-cd/github-actions.md)) and have this endpoint
    surface the most recent result.

## Background Task Pattern

For apps that want periodic in-process checks without a separate CI job:

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio

from promptcanary import CanarySuite, LiteLLMProvider, FileBaselineStore, compare

suite = CanarySuite.from_yaml("canary.yaml")
provider = LiteLLMProvider("openai/gpt-5.4")
store = FileBaselineStore("baselines/")
latest_drift = {"status": "pending"}

async def periodic_canary_check():
    while True:
        result = suite.run(provider, show_progress=False)
        baseline = store.load_latest(suite.name, provider.config.model_id)
        drift = compare(baseline, result)
        latest_drift["status"] = "drift" if drift.has_drift else "ok"
        latest_drift["summary"] = drift.summary
        await asyncio.sleep(3600)  # hourly

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(periodic_canary_check())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

@app.get("/health/canary")
def canary_health():
    return latest_drift
```
