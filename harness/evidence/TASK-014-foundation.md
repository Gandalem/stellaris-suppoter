# TASK-014 foundation — four-domain synthetic partial implementation

Started from actual main `526cad817a1fbde65fcb6d89758c9017d5b92bde` after PR #26 TASK-013 closeout and PR #27 overlay plan both merged, with Package/Documentation main CI success.

This is a **partial, unmerged** implementation PR, not E-027 complete evidence. TASK-014 remains `doing`; F-005 stays `in_progress`, E-027 stays `not_run`. No real Stellaris source files, version, DLC or game-engine semantics verified.

## Added foundation
- Explicit opt-in candidate-path registry for `component_template`, `building`, `district`, `pop_job`.
- `DomainCandidate`, `DomainField`, `DomainDiagnostic`, result/conflict models separate from `TechnologyCandidate`.
- In authored synthetic fixtures, component IDs are the unique static `key` field; other three IDs are root literal identifiers. Unsupported dynamic/missing IDs remain partial.
- AST ordered fields, duplicate field and definition occurrence, condition raw blocks, exact file-qualified SourceRef bytes, and unknown top-level input are preserved. No game precedence inference.
- Source SHA, path registry, AST byte-span/token/field relationships, document order and parser/lexer limits checked before adaptation; hard parser resource errors block extraction. `verify_domain_candidate` compares against a re-parse, never trusts supplied JSON blindly.
- `find_domain_collisions` reports same-kind/same-snapshot duplicates, without merging or choosing winners.
- Localisation uses the existing bounded resolver through explicit synthetic ID-key policy; actual game per-domain mapping remains an unverified hypothesis.
- New authored synthetic tests cover four normal domains, ID failure, duplicate/collision, provenance modification, raw-budget, snapshot isolation, parser-limit, CRLF/BOM and unsupported syntax.

## Explicit non-goals / remaining E-027 gates
- Domains not yet implemented: traits, government, civic, origin, traditions, ascension perk, events, scripted triggers/effects.
- Across-file/locale coverage matrix is not yet complete. Dynamic translation and verified actual localisation key mapping are unproven.
- No repository/storage integration, CLI search/show support for these four domains, schema migration, ref/diff, or real game compatibility.
- Full security attack matrix, full synthetic domain E-027 coverage, and final cross-OS CI must pass before evaluation is upgraded from `not_run`.
- Existing technology/CLI/SQLite/SourceRef contracts remain unchanged.
