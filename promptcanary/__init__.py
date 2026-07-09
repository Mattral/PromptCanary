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
    provider = LiteLLMProvider("openai/gpt-5.4-mini")
    result = suite.run(provider)
    print(result.overall_score)

See https://github.com/Mattral/PromptCanary for full documentation.
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
    ToolCallArgsProbe,
    ToolCallNameProbe,
    ToolCallPresenceProbe,
    ToolCallSchemaProbe,
    VerbosityProbe,
    get_probe,
    get_probe_registry,
    probe,
)
from promptcanary.core.reporter import DriftReporter, Reporter
from promptcanary.core.suite import CanarySuite
from promptcanary.providers.litellm import LiteLLMProvider
from promptcanary.storage.file import FileBaselineStore

__version__ = "0.2.3"
__author__ = "PromptCanary Contributors"

__all__ = [  # noqa: RUF022
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
    # Probes — base
    "BaseProbe",
    "probe",
    "get_probe",
    "get_probe_registry",
    # Probes — format
    "JsonValidityProbe",
    "JsonSchemaProbe",
    "JsonKeyOrderProbe",
    "ResponseLengthProbe",
    "MarkdownHeaderProbe",
    "KeywordPresenceProbe",
    "ExpectedKeywordsProbe",
    # Probes — reasoning
    "StepByStepProbe",
    "VerbosityProbe",
    "ConfidenceLanguageProbe",
    "DirectAnswerProbe",
    # Probes — safety
    "RefusalProbe",
    "SafetyLanguageProbe",
    # Probes — factual
    "FactualConsistencyProbe",
    "SentimentProbe",
    # Probes — tool use
    "ToolCallPresenceProbe",
    "ToolCallNameProbe",
    "ToolCallArgsProbe",
    "ToolCallSchemaProbe",
]
