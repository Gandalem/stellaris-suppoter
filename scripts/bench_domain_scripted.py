"""TASK-014 C2 non-gating scripted 32-candidate source verification observation.

Authored synthetic fixtures only. Never a TASK-019 hardware performance SLA.
No real game files or network access.
"""

from __future__ import annotations

import hashlib
import json
import platform
import statistics
import time
from unittest.mock import patch

from stellaris_supporter.domain.generic import adapt_domain, verify_domain_candidate
from stellaris_supporter.domain.technology import SourceContext
from stellaris_supporter.parsing import parse_bytes

COUNT = 32
REPEATS = 3
KINDS = ("scripted_trigger", "scripted_effect")
PREFIX = {
    "scripted_trigger": "common/scripted_triggers/",
    "scripted_effect": "common/scripted_effects/",
}


def observe(kind: str) -> dict[str, object]:
    raw = "\n".join(
        f"scripted_{i} = {{ limit = {{ has_flag = yes }} "
        f"if = {{ amount = {i} }} }}"
        for i in range(COUNT)
    ).encode()
    context = SourceContext(
        "authored-scripted-perf", "synthetic", "authored",
        PREFIX[kind] + "bench_wave5.txt",
        hashlib.sha256(raw).hexdigest(),
    )
    parsed = parse_bytes(raw)
    adapt_calls: list[int] = []
    verify_calls: list[int] = []
    adapt_ms: list[float] = []
    verify_ms: list[float] = []
    for _ in range(REPEATS):
        with patch(
            "stellaris_supporter.domain.generic.parse_bytes", wraps=parse_bytes
        ) as canonical:
            started = time.perf_counter_ns()
            result = adapt_domain(parsed, raw, context, kind)
            adapt_ms.append((time.perf_counter_ns() - started) / 1_000_000)
            adapt_calls.append(canonical.call_count)
        assert result.complete and not result.diagnostics
        assert len(result.candidates) == COUNT
        assert all(c.localisation_key is None for c in result.candidates)
        with patch(
            "stellaris_supporter.domain.generic.parse_bytes", wraps=parse_bytes
        ) as canonical:
            started = time.perf_counter_ns()
            assert all(
                verify_domain_candidate(c, raw, context)
                for c in result.candidates
            )
            verify_ms.append((time.perf_counter_ns() - started) / 1_000_000)
            verify_calls.append(canonical.call_count)
    assert adapt_calls == [1] * REPEATS
    assert verify_calls == [COUNT] * REPEATS
    return {
        "kind": kind,
        "source_sha256": context.file_sha256,
        "synthetic_candidate_count": COUNT,
        "repeats": REPEATS,
        "adapt_parse_calls": adapt_calls,
        "separate_verify_parse_calls": verify_calls,
        "adapt_ms": [round(x, 3) for x in adapt_ms],
        "verify_ms": [round(x, 3) for x in verify_ms],
        "adapt_ms_median": round(statistics.median(adapt_ms), 3),
        "separate_verify_ms_median": round(statistics.median(verify_ms), 3),
        "task_019_official_performance": False,
    }


if __name__ == "__main__":
    print(json.dumps({
        "platform": platform.system(),
        "python": platform.python_version(),
        "results": [observe(kind) for kind in KINDS],
    }, ensure_ascii=False, sort_keys=True))
