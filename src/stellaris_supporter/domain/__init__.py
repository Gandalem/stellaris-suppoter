"""Domain adapters for ordered parser output."""

from stellaris_supporter.domain.technology import (
    DEFAULT_ADAPTER_MAX_RAW_OUTPUT_BYTES,
    AdapterSerializationLimitError,
    RawNodeRef,
    SourceContext,
    SourceRef,
    TechnologyAdaptResult,
    TechnologyCandidate,
    TechnologyDiagnostic,
    TechnologyField,
    TechnologyPrerequisite,
    adapt_technologies,
)

__all__ = [
    "DEFAULT_ADAPTER_MAX_RAW_OUTPUT_BYTES",
    "AdapterSerializationLimitError",
    "RawNodeRef",
    "SourceContext",
    "SourceRef",
    "TechnologyAdaptResult",
    "TechnologyCandidate",
    "TechnologyDiagnostic",
    "TechnologyField",
    "TechnologyPrerequisite",
    "adapt_technologies",
]
