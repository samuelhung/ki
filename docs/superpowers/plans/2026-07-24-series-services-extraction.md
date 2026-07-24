# Series Services Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `series_routes.py` to a thin HTTP adapter by moving each existing专题系列 workflow into a focused service without changing API, OpenAPI, prompts, SQLite schema, or runtime behavior.

**Architecture:** Route decorators, request models, function names, signatures, and order remain in `routes/series_routes.py`. Candidate persistence, discovery modes, expansion/naming, generated content, and post-ingest matching become dependency-injected backend services; `prompt_registry.py` follows prompts to their new owners. Every production module remains at or below 400 lines.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, pytest, Ruff.

---

### Task 1: Lock the complete external and internal contracts

**Files:**
- Modify: `tests/test_series_service.py`
- Create: `tests/test_series_route_contracts.py`

- [ ] Add a characterization test that records all 19 series route positions, paths, methods, endpoint names, signatures, and request-body schema references.
- [ ] Add wrapper tests for every route that will be extracted. Monkeypatch the target service function and assert the request object plus call-time `connect`, `init_db`, and `_call_ai_chat` dependencies are forwarded unchanged.
- [ ] Add a Prompt registry test asserting the current `series` tasks remain exactly `discover`, `intro`, `summary`, `paper`, and `auto_suggest`, with non-empty prompt payloads before and after extraction.
- [ ] Run `python -m pytest -q tests/test_series_service.py tests/test_series_route_contracts.py`; verify the new forwarding tests fail because the service modules do not exist yet.
- [ ] Commit as `test: lock series route extraction contracts`.

### Task 2: Extract candidate persistence and discovery workflows

**Files:**
- Create: `src/zhiji_backend/series_candidate_service.py`
- Create: `src/zhiji_backend/series_discovery_service.py`
- Create: `src/zhiji_backend/series_topic_discovery_service.py`
- Modify: `src/zhiji_backend/routes/series_routes.py`
- Create: `tests/test_series_discovery_services.py`

- [ ] Add failing service tests for duplicate detection, stale-candidate cleanup, fenced JSON parsing, exact AI arguments, candidate insert/update behavior, invalid/empty AI responses, insufficient-event responses, ID bracket cleanup, and database writes.
- [ ] Move `_find_duplicate()` and `_cleanup_stale_candidates()` into `series_candidate_service.py`, retaining the exact thresholds, SQL, date format, and malformed-member fallback.
- [ ] Move `discover_series()`, `discover_stage1()`, and `discover_stage2()` business logic into `series_discovery_service.py`; expose dependency-injected functions while keeping exact prompts, limits, error dictionaries, logging, and persistence behavior.
- [ ] Move `discover_by_topic()` into `series_topic_discovery_service.py`, preserving keyword bigrams, SQL ordering/limit, AI parameters, de-duplication, and response shape.
- [ ] Replace route bodies with thin wrappers and run the focused tests until green.
- [ ] Confirm each new production module is at most 400 lines and commit as `refactor: extract series discovery services`.

### Task 3: Extract expansion and naming workflows

**Files:**
- Create: `src/zhiji_backend/series_expansion_service.py`
- Modify: `src/zhiji_backend/routes/series_routes.py`
- Create: `tests/test_series_expansion_service.py`

- [ ] Add failing tests for missing series, empty expansion pool, scan-cache behavior, exact AI call arguments, recommendation persistence, malformed AI output, and name suggestion success/error responses.
- [ ] Move `expand_series()` and `suggest_series_name()` into `series_expansion_service.py` with injected database, initializer, and chat dependencies.
- [ ] Keep route names, signatures, decorators, order, prompts, timestamps, and responses unchanged; wrappers must resolve dependencies at call time.
- [ ] Run focused tests and commit as `refactor: extract series expansion service`.

### Task 4: Extract generated专题 content

**Files:**
- Create: `src/zhiji_backend/series_generation_service.py`
- Modify: `src/zhiji_backend/routes/series_routes.py`
- Modify: `src/zhiji_backend/prompt_registry.py`
- Create: `tests/test_series_generation_service.py`

- [ ] Add failing tests for intro, summary, and paper: missing专题, insufficient members, exact prompt/AI parameters, empty output, SQLite update, timestamp format, and response shape.
- [ ] Move the three generators into `series_generation_service.py` without changing prompt text, source ordering, token/timeout values, HTTP errors, or stored fields.
- [ ] Update the Prompt registry file/function mappings so the same five public series tasks and prompt contents remain visible.
- [ ] Run generation, route-contract, and Prompt registry tests; commit as `refactor: extract series generation service`.

### Task 5: Extract post-ingest automatic matching

**Files:**
- Create: `src/zhiji_backend/series_auto_suggest_service.py`
- Modify: `src/zhiji_backend/routes/series_routes.py`
- Modify: `src/zhiji_backend/task_queue.py`
- Modify: `src/zhiji_backend/prompt_registry.py`
- Create: `tests/test_series_auto_suggest_service.py`

- [ ] Add failing tests for missing/empty events, no published series, exact AI arguments, empty/invalid results, suggestion writes, and failure logging without propagation.
- [ ] Move `auto_suggest_series()` into `series_auto_suggest_service.py`; update `task_queue.py` to import the new owner lazily while preserving non-blocking failure semantics.
- [ ] Point Prompt registry `auto_suggest` at the new service and verify prompt visibility remains unchanged.
- [ ] Run focused tests and commit as `refactor: extract series auto suggestion service`.

### Task 6: Retire the structural baseline entry and verify integration

**Files:**
- Modify: `structure-baseline.json`
- Modify: `tests/test_series_route_contracts.py` if an integration assertion needs tightening

- [ ] Confirm `series_routes.py` now contains only models, route declarations, and dependency forwarding, and is below 400 lines.
- [ ] Regenerate the structural baseline and verify only `src/zhiji_backend/routes/series_routes.py` is removed from oversized files; no Ruff suppression is added.
- [ ] Run focused series tests, full backend `python -m pytest -q`, `scripts/check.sh`, baseline comparison against `origin/main`, and `git diff --check`.
- [ ] Request independent spec and code-quality review, fix all Critical/Important findings, and rerun affected plus full checks.
- [ ] Commit as `build: retire series routes structural baseline`, push the branch, and create a Draft PR. Do not merge or deploy automatically.
