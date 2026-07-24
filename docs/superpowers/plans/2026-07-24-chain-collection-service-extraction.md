# Chain Collection Service Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the core industry-chain trade-data collection operation from `chain_routes.py` without changing routes, prompts, parsing, storage, or error behavior.

**Architecture:** Keep `_do_collect()` as a compatibility wrapper in `chain_routes.py` and move its implementation into `chain_collection_service.py`. Inject SQLite, AI chat, and logging at call time; retain lazy web-search import behavior. Leave endpoint orchestration untouched because the existing batch endpoint has a separate connection-lifecycle defect that must not be silently changed in this structural PR.

**Tech Stack:** Python 3.12, SQLite, pytest, Ruff.

---

### Task 1: Lock Collection Behavior

**Files:**
- Create: `tests/test_chain_collection_service.py`
- Modify: `tests/test_chain_node_service.py`

- [ ] Add a failing wrapper test proving `_do_collect()` forwards current `connect`, `chat`, and `logger` dependencies.
- [ ] Add service tests for the local no-data response and web-search extraction, numeric cleanup, source persistence, and response shape.
- [ ] Run focused tests and verify they fail because `chain_collection_service` does not exist.
- [ ] Commit the failing tests.

### Task 2: Extract Core Collection

**Files:**
- Create: `src/zhiji_backend/chain_collection_service.py`
- Modify: `src/zhiji_backend/routes/chain_routes.py`

- [ ] Move `_do_collect` implementation unchanged into `collect_node_data()` with injected `connect_fn`, `chat_fn`, and `service_logger`.
- [ ] Keep web search imported lazily only when `use_web=True`.
- [ ] Replace `_do_collect()` with a thin call-time dependency wrapper; do not change either endpoint body.
- [ ] Run focused tests and Ruff.
- [ ] Commit the extraction.

### Task 3: Baseline And Delivery

**Files:**
- Modify: `structure-baseline.json`

- [ ] Regenerate the structural baseline and verify against `main`.
- [ ] Confirm the new service stays below 400 lines and `chain_routes.py` decreases.
- [ ] Run backend full tests and `scripts/check.sh`.
- [ ] Review `git diff --check main...HEAD` and the complete diff.
- [ ] Push and create a Draft PR; do not merge or deploy automatically.
