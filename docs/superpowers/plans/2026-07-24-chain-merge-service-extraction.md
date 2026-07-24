# Chain Merge Service Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `chain_routes.py` by extracting industry-chain overlap detection and merge orchestration without changing HTTP routes, request schemas, database writes, AI prompts, or responses.

**Architecture:** Keep `chain_routes.py` as the compatibility facade so FastAPI route order, endpoint names, Pydantic models, and monkeypatch seams remain stable. Move the two large business operations into `chain_merge_service.py`, using explicit call-time dependency injection for SQLite, AI chat, icon selection, and logging.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, pytest, Ruff.

---

### Task 1: Lock The Extraction Contract

**Files:**
- Create: `tests/test_chain_merge_service.py`
- Modify: `tests/test_chain_node_service.py`

- [ ] **Step 1: Add failing wrapper dependency tests**

Assert that `check_chain_overlaps()` and `merge_chains()` preserve their public signatures and delegate to `chain_merge_service` with the current values of `chain_routes.connect`, `chain_routes.chat`, `_suggest_icon`, and `logger`.

- [ ] **Step 2: Add representative service behavior tests**

Use a temporary SQLite database to verify overlap detection output and a merge into chain A. Stub AI ordering so tests are deterministic and assert node reassignment, sort order, metadata removal, hint reassignment, and response shape.

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=src /Users/yuk/Documents/zhiji/ki/.venv/bin/python -m pytest -q \
  tests/test_chain_merge_service.py \
  tests/test_chain_node_service.py::test_chain_merge_route_wrappers_forward_call_time_dependencies
```

Expected: collection or assertion failure because `chain_merge_service` and wrapper delegation do not exist yet.

- [ ] **Step 4: Commit the failing contract tests**

```bash
git add tests/test_chain_merge_service.py tests/test_chain_node_service.py
git commit -m "test: lock chain merge extraction contract"
```

### Task 2: Extract Merge Business Logic

**Files:**
- Create: `src/zhiji_backend/chain_merge_service.py`
- Modify: `src/zhiji_backend/routes/chain_routes.py`

- [ ] **Step 1: Add service dependency protocols**

Define narrow protocols for the merge request and injected callables. Keep FastAPI's existing `HTTPException` behavior for invalid `into` values and conflicting new names.

- [ ] **Step 2: Move overlap detection unchanged**

Move the body of `check_chain_overlaps()` into:

```python
def check_chain_overlaps(*, connect_fn: ConnectFn) -> dict[str, object]:
    ...
```

Preserve SQL, fuzzy matching, score calculation, ordering, and response keys exactly.

- [ ] **Step 3: Move merge orchestration unchanged**

Move the body of `merge_chains()` into:

```python
def merge_chains(
    request: MergeRequestLike,
    *,
    connect_fn: ConnectFn,
    chat_fn: ChatFn,
    icon_suggester: IconSuggester,
    service_logger: logging.Logger,
) -> dict[str, object]:
    ...
```

Preserve the AI prompt, 30-second AI timeout, fallback ordering, SQL statements, commit boundary, and response payload.

- [ ] **Step 4: Replace route bodies with thin wrappers**

Keep decorators, endpoint names, signatures, models, and route order in `chain_routes.py`. Delegate using call-time dependencies so existing monkeypatch behavior remains intact.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
PYTHONPATH=src /Users/yuk/Documents/zhiji/ki/.venv/bin/python -m pytest -q \
  tests/test_chain_merge_service.py tests/test_chain_node_service.py \
  tests/test_route_structure_regressions.py tests/test_api_constraints.py
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit the extraction**

```bash
git add src/zhiji_backend/chain_merge_service.py src/zhiji_backend/routes/chain_routes.py
git commit -m "refactor: extract chain merge service"
```

### Task 3: Reduce The Structural Baseline

**Files:**
- Modify: `structure-baseline.json`

- [ ] **Step 1: Regenerate the deterministic baseline**

Run:

```bash
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/check_structure_baseline.py --write-baseline
```

Expected: `chain_routes.py` line count decreases and `chain_merge_service.py` does not enter the oversized-file baseline.

- [ ] **Step 2: Verify the reduction against main**

Run:

```bash
ZHIJI_STRUCTURE_BASE_REF=main \
  /Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/check_structure_baseline.py
```

Expected: pass with no structural regressions.

- [ ] **Step 3: Commit the reduced baseline**

```bash
git add structure-baseline.json
git commit -m "build: reduce chain route structural baseline"
```

### Task 4: Full Verification And Draft PR

**Files:**
- Verify only.

- [ ] **Step 1: Run backend full suite**

```bash
PYTHONPATH=src UV_CACHE_DIR=/private/tmp/ki-uv-cache \
  /private/tmp/ki-uv-tool/bin/uv run --frozen python -m pytest -q
```

- [ ] **Step 2: Run the unified gate**

```bash
UV_CACHE_DIR=/private/tmp/ki-uv-cache \
PATH=/private/tmp/ki-uv-tool/bin:/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH \
  ./scripts/check.sh
```

- [ ] **Step 3: Inspect final hygiene**

Run `git diff --check main...HEAD`, `git status --short`, and review the complete diff. Confirm no API, Schema, UI, or production-data changes.

- [ ] **Step 4: Push and create a Draft PR**

Push `codex/structure-cleanup-chain-routes` and create a Draft PR targeting `main`. Do not merge or deploy automatically.
