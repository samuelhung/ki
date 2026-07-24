# Structure Cleanup Baseline Design

## Status

Approved direction on 2026-07-24. This is the first independently reversible sub-project of Round 4.

## Goal

Create a deterministic structural inventory and a no-regression gate before splitting large modules. The change must not alter runtime behavior, HTTP contracts, the database schema, page layout, copy, animation, or WebGL rendering.

## Current State

The repository already enforces a pinned Ruff baseline and an exact frontend explicit-`any` baseline. Those gates cover syntax, selected Python lint rules, and TypeScript escape hatches, but they do not make structural growth visible.

The largest active files currently include:

- `src/zhiji_backend/routes/chain_routes.py` at 1,667 lines.
- `src/zhiji_backend/routes/series_routes.py` at 1,370 lines.
- `src/zhiji_backend/routes/brainstorm_routes.py` at 1,121 lines.
- `src/zhiji_backend/database_backup.py` at 1,082 lines.
- `src/zhiji_backend/task_queue.py` at 963 lines.
- `app/frontend/src/pages/SeriesDetail.tsx` at 882 lines.
- `app/frontend/src/pages/BrainstormDetailPage.tsx` at 841 lines.

Ruff also has targeted per-file `E402` exceptions. These are legitimate current debt, but new exceptions must not be added silently.

## Approaches Considered

### Documentation-only inventory

Record large files and suppressions in a Markdown report. This is easy to review but immediately becomes stale and cannot prevent regression.

### Fixed global line limit

Reject every source file above a single maximum. This is simple but would either fail the current tree or require a limit so high that it would not constrain most modules. It also encourages mechanical splits without ownership boundaries.

### Checked baseline with target-branch comparison

Record current oversized files and Ruff per-file ignores in a machine-readable baseline. Require the checked-in baseline to match the working tree exactly, then compare it with the pull request base and reject new oversized files, growth in an existing oversized file, or new lint suppressions. Reductions and removals are allowed when the baseline is updated in the same commit.

This is the selected approach because it matches the established explicit-`any` gate, exposes debt without pretending it can be removed atomically, and makes every future structural change measurable.

## Architecture

### Structural scanner

Add `scripts/check_structure_baseline.py`. It scans active Python, TypeScript, and TSX production files under `src/zhiji_backend` and `app/frontend/src`.

The scanner records physical line counts only for files above 400 lines. Physical lines are intentionally used because they are deterministic, language-independent, and easy to verify with standard tools. Generated output, tests, build output, dependencies, and temporary directories are excluded.

The scanner also reads `[tool.ruff.lint.per-file-ignores]` from `pyproject.toml` and records the normalized path-to-rule mapping. It does not duplicate the explicit-`any` scanner.

### Checked baseline

Add `structure-baseline.json` at the repository root with this contract:

```json
{
  "schema_version": 1,
  "oversized_files": {
    "path/to/file.py": 401
  },
  "ruff_per_file_ignores": {
    "path/to/file.py": ["E402"]
  }
}
```

Normal execution requires this file to equal the current scan. `--write-baseline` performs the sole deterministic update path.

When `ZHIJI_STRUCTURE_BASE_REF` is set, the scanner loads the baseline from that Git commit and rejects:

- A new production source file above 400 lines.
- Any line-count increase in a file that was already oversized.
- A new Ruff per-file-ignore path or rule.
- A schema version mismatch or malformed baseline.

An oversized file may shrink or disappear. A Ruff exception may be removed. Both require regenerating the checked baseline so local and CI results remain reproducible.

### Integration

Add the scanner to `scripts/check.sh` next to the existing Ruff and explicit-`any` gates. Add `ZHIJI_STRUCTURE_BASE_REF` to the pull-request workflow using the same base SHA already used by the explicit-`any` gate.

Unit tests cover scanning, malformed input, exact drift, allowed reductions, rejected growth, new oversized files, and new Ruff suppressions. The existing structure-quality test verifies that the unified check and CI wiring cannot be removed accidentally.

## Initial Priorities Produced By The Baseline

The baseline does not split modules. It establishes this order for later Round 4 pull requests:

1. Backend route ownership: chain, series, and brainstorm routes.
2. Backend lifecycle ownership: database backup and task queue.
3. Frontend page ownership: series and brainstorm detail workspaces.
4. Ruff exception removal where import-time initialization can be made explicit.
5. Compatibility and dead-code removal only after reference and runtime evidence proves it unused.

Each later split gets its own design, tests, pull request, and visual/API regression checks.

## Failure Behavior

The gate exits non-zero with path-level, metric-level messages. It never rewrites the baseline unless `--write-baseline` is passed. Git reference lookup failures are explicit; a missing baseline in an old reference is treated as no historical constraint so the gate can be introduced in this pull request.

## Verification

- Focused unit tests for the scanner.
- Existing structure-quality tests.
- `scripts/check.sh`.
- Backend `pytest -q`.
- Frontend production build and existing cinematic tests.
- `git diff --check`.

No production deployment is part of this baseline sub-project.

## Boundaries

- No source module is split in this pull request.
- No dependency is added.
- No broad lint rule expansion is bundled with the baseline.
- No source line is changed merely to improve a metric.
- Production data and deployment configuration are untouched.
