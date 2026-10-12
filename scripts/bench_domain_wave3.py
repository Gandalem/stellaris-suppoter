"""Non-gating Phase B synthetic per-file vs per-candidate parse observation.

Not an installed game grammar, not a hardware-normalised performance SLA and
not TASK-019 or E-035. No network or game file access.
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


def source_for(kind: str) -> tuple[bytes, str]:
    if kind == "tradition":
        entries = " ".join(
            f"group_{i} = {{ id = trad_{i} name = trad_{i}_name "
            "potential = { flag = yes } }"
            for i in range(COUNT)
        )
        return f"traditions = {{ {entries} }}".encode(), "common/traditions/bench_wave3.txt"
    entries = "\n".join(
        f"ascension_perk = {{ id = perk_{i} name = perk_{i}_name "
        "potential = { flag = yes } }"
        for i in range(COUNT)
    )
    return entries.encode(), "common/ascension_perks/bench_wave3.txt"


def observe(kind: str) -> dict[str, object]:
    raw, path = source_for(kind)
    ctx = SourceContext(
        "authored-wave3-perf", "synthetic", "authored",
        path, hashlib.sha256(raw).hexdigest(),
    )
    parsed = parse_bytes(raw)
    adapt_ms: list[float] = []
    verify_ms: list[float] = []
    adapt_calls: list[int] = []
    verify_calls: list[int] = []
    for _ in range(REPEATS):
        with patch("stellaris_supporter.domain.generic.parse_bytes", wraps=parse_bytes) as canonical:
            start = time.perf_counter_ns()
            result = adapt_domain(parsed, raw, ctx, kind)
            adapt_ms.append((time.perf_counter_ns() - start) / 1_000_000)
            adapt_calls.append(canonical.call_count)
        assert result.complete and len(result.candidates) == COUNT
        with patch("stellaris_supporter.domain.generic.parse_bytes", wraps=parse_bytes) as canonical:
            start = time.perf_counter_ns()
            assert all(
                verify_domain_candidate(candidate, raw, ctx)
                for candidate in result.candidates
            )
            verify_ms.append((time.perf_counter_ns() - start) / 1_000_000)
            verify_calls.append(canonical.call_count)
    assert adapt_calls == [1] * REPEATS
    assert verify_calls == [COUNT] * REPEATS
    return {
        "kind": kind,
        "source_sha256": ctx.file_sha256,
        "synthetic_candidate_count": COUNT,
        "repeats": REPEATS,
        "adapt_canonical_parse_calls": adapt_calls,
        "separate_verification_parse_calls": verify_calls,
        "adapt_ms_samples": [round(x, 3) for x in adapt_ms],
        "verify_all_ms_samples": [round(x, 3) for x in verify_ms],
        "adapt_ms_median": round(statistics.median(adapt_ms), 3),
        "verify_all_ms_median": round(statistics.median(verify_ms), 3),
        "task019_official_performance": False,
    }


if __name__ == "__main__":
    print(json.dumps({
        "platform": platform.system(),
        "python": platform.python_version(),
        "results": [observe("tradition"), observe("ascension_perk")],
    }, ensure_ascii=False, sort_keys=True))
