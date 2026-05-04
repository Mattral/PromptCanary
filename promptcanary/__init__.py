"""
promptcanary
~~~~~~~~~~~~

Detect silent behavioral drift in LLM providers — before it breaks production.

Quick start::

    from promptcanary import CanarySuite, LiteLLMProvider
    from promptcanary.core.probes import JsonValidityProbe, StepByStepProbe
    from promptcanary.core.models import CanaryPrompt

    suite = CanarySuite(
        name="my-suite",
        prompts=[CanaryPrompt(text="Return JSON: {name: 'Alice'}")],
        probes=[JsonValidityProbe(), StepByStepProbe(expect_steps=False)],
    )
    provider = LiteLLMProvider("openai/gpt-4o-mini")
    result = suite.run(provider)
    print(result.overall_score)

See https://github.com/promptcanary/promptcanary for full documentation.
"""

from promptcanary.core.comparator import compare
from promptcanary.core.models import (
    BaselineSnapshot,
    CanaryPrompt,
    CanaryRunResult,
    DriftReport,
    DriftSeverity,
    LLMResponse,
    ProbeCategory,
    ProbeComparison,
    ProbeResult,
    ProviderConfig,
    ReportFormat,
)
from promptcanary.core.probes import (
    BaseProbe,
    ConfidenceLanguageProbe,
    DirectAnswerProbe,
    ExpectedKeywordsProbe,
    FactualConsistencyProbe,
    JsonKeyOrderProbe,
    JsonSchemaProbe,
    JsonValidityProbe,
    KeywordPresenceProbe,
    MarkdownHeaderProbe,
    RefusalProbe,
    ResponseLengthProbe,
    SafetyLanguageProbe,
    SentimentProbe,
    StepByStepProbe,
    VerbosityProbe,
    get_probe,
    get_probe_registry,
    probe,
)
from promptcanary.core.reporter import DriftReporter, Reporter
from promptcanary.core.suite import CanarySuite
from promptcanary.providers.litellm import LiteLLMProvider
from promptcanary.storage.file import FileBaselineStore

__version__ = "0.1.0"
__author__ = "PromptCanary Contributors"

__all__ = [
    # Version
    "__version__",
    # High-level API
    "CanarySuite",
    "LiteLLMProvider",
    "FileBaselineStore",
    "compare",
    "Reporter",
    "DriftReporter",
    # Models
    "CanaryPrompt",
    "CanaryRunResult",
    "BaselineSnapshot",
    "DriftReport",
    "DriftSeverity",
    "LLMResponse",
    "ProbeCategory",
    "ProbeComparison",
    "ProbeResult",
    "ProviderConfig",
    "ReportFormat",
    # Probes
    "BaseProbe",
    "probe",
    "get_probe",
    "get_probe_registry",
    "JsonValidityProbe",
    "JsonSchemaProbe",
    "JsonKeyOrderProbe",
    "ResponseLengthProbe",
    "MarkdownHeaderProbe",
    "KeywordPresenceProbe",
    "ExpectedKeywordsProbe",
    "StepByStepProbe",
    "VerbosityProbe",
    "ConfidenceLanguageProbe",
    "DirectAnswerProbe",
    "RefusalProbe",
    "SafetyLanguageProbe",
    "FactualConsistencyProbe",
    "SentimentProbe",
]
