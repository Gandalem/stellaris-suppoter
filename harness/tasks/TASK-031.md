# TASK-031 Safety hardening and main integration

## Trigger

Post-TASK-003 review reproduced filesystem and integration defects that were outside the original CI cases. Existing successful evidence remains historical evidence, but F-002 is temporarily returned to `in_progress` until the new regressions pass.

## Scope

- Bound synthetic corpus `--force` to generator-owned files only.
- Reject symlink, filesystem-root, repository-root, and repository-parent output targets.
- Convert user-controlled path resolution/status failures into structured diagnostics.
- Require directory traversal capability on POSIX while keeping game input read-only.
- Redact public report diagnostics as well as settings.
- Ignore empty/relative XDG base-directory values.
- Require integer `schema_version = 1`.
- Revalidate on Linux and Windows.
- Integrate TASK-001~003 on a branch based directly on `main` and open a main-targeting PR.

## Non-goals

TASK-004 inventory behavior, actual game files, game version/DLC/mod detection, parser/search.

## Completion

TASK-031 becomes done only after E-047 passes with CI evidence. F-002 may return to verified; F-013/F-014 remain in_progress because broader safety/release tasks are still outstanding. TASK-004 remains blocked by dependency until then.
