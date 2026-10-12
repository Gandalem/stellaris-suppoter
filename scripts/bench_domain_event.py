"""Non-gating Phase C1 source-bound synthetic event candidate parse-cost sample.

32 authored synthetic event candidates, no game files, no TASK-019 evaluation.
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


def observe() -> dict[str, object]:
    raw = (
        "namespace = authored\n"
        + "\n".join(
            f"country_event = {{ id = authored.{i} title = title_{i} "
            "trigger = { flag = yes } immediate = { no_op = @dynamic } }"
            for i in range(COUNT)
        )
    ).encode()
    ctx = SourceContext(
        "authored-event-benchmark", "synthetic", "authored",
        "events/bench_event.txt", hashlib.sha256(raw).hexdigest(),
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
            start = time.perf_counter_ns()
            result = adapt_domain(parsed, raw, ctx, "event")
            adapt_ms.append((time.perf_counter_ns() - start) / 1_000_000)
            adapt_calls.append(canonical.call_count)
        assert result.complete and len(result.candidates) == COUNT
        with patch(
            "stellaris_supporter.domain.generic.parse_bytes", wraps=parse_bytes
        ) as canonical:
            start = time.perf_counter_ns()
            assert all(verify_domain_candidate(c, raw, ctx) for c in result.candidates)
            verify_ms.append((time.perf_counter_ns() - start) / 1_000_000)
            verify_calls.append(canonical.call_count)
    assert adapt_calls == [1] * REPEATS
    assert verify_calls == [COUNT] * REPEATS
    return {
        "kind": "event",
        "source_sha256": ctx.file_sha256,
        "synthetic_candidate_count": COUNT,
        "repeats": REPEATS,
        "platform": platform.system(),
        "python": platform.python_version(),
        "adapt_parse_calls": adapt_calls,
        "separate_verify_parse_calls": verify_calls,
        "adapt_ms": [round(x, 3) for x in adapt_ms],
        "separate_verify_ms": [round(x, 3) for x in verify_ms],
        "adapt_ms_median": round(statistics.median(adapt_ms), 3),
        "separate_verify_ms_median": round(statistics.median(verify_ms), 3),
        "TASK_019_official_evaluation": False,
    }


if __name__ == "__main__":
    print(json.dumps(observe(), ensure_ascii=False, sort_keys=True))
