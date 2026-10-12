# TASK-014 Phase C2 — Scripted Trigger / Scripted Effect

2026-10-12 Asia/Seoul. Verified actual PR #32 merge `e77b38dd3d568ee368d07e3a18777d4aacee8ce2`, main Package CI #38248847704 (Ubuntu 704, Windows 701+3 existing skips, Ruff/harness both success) and Documentation #38248847705 (both success); all four jobs checked out the true main SHA. Created separate `task/TASK-014-domain-adapters-wave5-scripted` from that SHA.

Two authored **synthetic** root-ID script adapters implemented without any game-data installation or engine evaluation. Scripted kinds intentionally have `localisation_key=None` and no guessed KO/EN name. Existing raw backing/whole ParseResult validation, 1,000 diagnostic budget, eleven previous kinds, Technology/SQLite/Search/CLI preserved. New authored tests red before production registration, implementation tests and CI/evidence tracked at `harness/evidence/TASK-014-domain-adapters-wave5-scripted.md`. Exact final PR CI and temporary merge SHA to be recorded on PR after real runs.

TASK-014 doing, F-005 in_progress, E-027 not_run; C3 evaluation still pending until owner merge and true main CI of C2. TASK-015–022 todo; latest_game_version null, product_implemented false. No automatic merge or direct main edit.
