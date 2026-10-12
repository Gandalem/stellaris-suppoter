"""Non-gating authored synthetic domain parse and per-candidate verification sample.

Not TASK-019, not a hardware-independent latency guarantee, and not evidence
for a real Stellaris installation. Runs entirely in memory, with no game I/O.
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

ENTITY_COUNT = 32
REPEATS = 3


def run() -> dict[str, object]:
    source = "\n".join(
        f"trait_{i} = {{ cost = {i} potential = {{ flag = yes }} }}"
        for i in range(ENTITY_COUNT)
    ).encode("utf-8")
    digest = hashlib.sha256(source).hexdigest()
    ctx = SourceContext(
        "authored-wave2-benchmark", "synthetic", "authored",
        "common/traits/bench_wave2.txt", digest,
    )
    parsed = parse_bytes(source)
    adapt_ms: list[float] = []
    per_candidate_verify_ms: list[float] = []
    adapt_parse_calls: list[int] = []
    verify_parse_calls: list[int] = []
    for _ in range(REPEATS):
        with patch(
            "stellaris_supporter.domain.generic.parse_bytes", wraps=parse_bytes
        ) as canonical:
            begin = time.perf_counter_ns()
            result = adapt_domain(parsed, source, ctx, "trait")
            adapt_ms.append((time.perf_counter_ns() - begin) / 1_000_000)
            adapt_parse_calls.append(canonical.call_count)
        assert result.complete and len(result.candidates) == ENTITY_COUNT
        with patch(
            "stellaris_supporter.domain.generic.parse_bytes", wraps=parse_bytes
        ) as canonical:
            begin = time.perf_counter_ns()
            assert all(
                verify_domain_candidate(candidate, source, ctx)
                for candidate in result.candidates
            )
            per_candidate_verify_ms.append(
                (time.perf_counter_ns() - begin) / 1_000_000
            )
            verify_parse_calls.append(canonical.call_count)
    assert adapt_parse_calls == [1] * REPEATS
    assert verify_parse_calls == [ENTITY_COUNT] * REPEATS
    return {
        "kind": "authored_synthetic_only",
        "python": platform.python_version(),
        "platform": platform.system(),
        "corpus_sha256": digest,
        "entities": ENTITY_COUNT,
        "repeat_count": REPEATS,
        "adapt_parse_calls_per_iteration": adapt_parse_calls,
        "candidate_verification_parse_calls_per_iteration": verify_parse_calls,
        "adapt_ms_samples": [round(v, 3) for v in adapt_ms],
        "verify_all_candidates_ms_samples": [
            round(v, 3) for v in per_candidate_verify_ms
        ],
        "adapt_ms_median": round(statistics.median(adapt_ms), 3),
        "verify_all_candidates_ms_median": round(
            statistics.median(per_candidate_verify_ms), 3
        ),
        "official_task_019_performance_evaluation": False,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
