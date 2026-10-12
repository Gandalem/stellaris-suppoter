"""PR #32 R1/P2 regression: authored synthetic event IDs have a real suffix.

These rules are deliberately *not* claims about installed Stellaris grammar.
The general ten-domain _ID matcher must remain unchanged.
"""

from __future__ import annotations

import hashlib

import pytest

from stellaris_supporter.domain.generic import adapt_domain, verify_domain_candidate
from stellaris_supporter.domain.technology import SourceContext
from stellaris_supporter.parsing import parse_bytes


def event_result(
    event_id: str,
    *,
    event_type: str = "country_event",
    namespace: str = "namespace = authored\n",
    file: str = "event_id_review.txt",
):
    raw = (
        namespace + f"{event_type} = {{ id = {event_id} title = authored_title }}"
    ).encode("utf-8")
    ctx = SourceContext(
        "A", "synthetic", "authored", "events/" + file,
        hashlib.sha256(raw).hexdigest(),
    )
    return raw, ctx, adapt_domain(parse_bytes(raw), raw, ctx, "event")


@pytest.mark.parametrize("event_type", ["country_event", "planet_event"])
@pytest.mark.parametrize(
    "event_id",
    ["authored.", "authored..1", "authored.1."],
)
def test_r1_event_invalid_qualified_id_is_never_complete(event_type, event_id):
    raw, ctx, result = event_result(
        event_id, event_type=event_type, file="invalid_suffix.txt"
    )
    assert not result.blocked and len(result.candidates) == 1
    candidate = result.candidates[0]
    # Preserve the original literal and byte-range provenance even though the
    # authored-synthetic ID is not acceptable for a complete definition.
    assert candidate.game_id == event_id
    assert candidate.id_source_ref is not None
    assert candidate.id_source_ref.raw_bytes(raw) == event_id.encode()
    assert candidate.source_ref.snapshot_id == "A"
    assert candidate.source_ref.relative_path == ctx.relative_path
    assert (result.complete, candidate.resolution, candidate.support_level) == (
        False, "partial", "partial"
    )
    assert "DOMAIN_EVENT_INVALID_QUALIFIED_ID" in [
        diagnostic.code for diagnostic in result.diagnostics
    ]
    assert any(
        d.code == "DOMAIN_EVENT_INVALID_QUALIFIED_ID"
        and d.source_ref == candidate.id_source_ref
        for d in result.diagnostics
    )
    assert verify_domain_candidate(candidate, raw, ctx)


@pytest.mark.parametrize("event_type", ["country_event", "planet_event"])
@pytest.mark.parametrize("event_id", ["authored.1", "authored.example"])
def test_r1_event_valid_qualified_ids_remain_complete(event_type, event_id):
    raw, ctx, result = event_result(event_id, event_type=event_type)
    assert result.complete and not result.blocked
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert (candidate.game_id, candidate.resolution, candidate.support_level) == (
        event_id, "raw_definition", "synthetic_static"
    )
    assert candidate.id_source_ref.raw_bytes(raw) == event_id.encode()
    assert verify_domain_candidate(candidate, raw, ctx)
