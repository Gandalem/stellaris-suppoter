"""Domain adapters for ordered parser output."""

from stellaris_supporter.domain.technology import (
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
