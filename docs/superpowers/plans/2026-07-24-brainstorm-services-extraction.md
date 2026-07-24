# Brainstorm Services Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `brainstorm_routes.py` to a thin HTTP adapter by moving each existing brainstorm workflow into a focused service without changing API, OpenAPI, prompts, SQLite behavior, files, logging, responses, or frontend behavior.

**Architecture:** Keep all request models, route decorators, endpoint names, signatures, and route order in `routes/brainstorm_routes.py`. Extract question persistence, one-shot answers, conversations, contemplation, and concept precipitation into dependency-injected backend services; retain route-level compatibility facades for call-time monkeypatching and move Prompt Registry ownership to the new modules. Every production module must remain at or below 400 lines.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, pytest, Ruff.

---

### Task 1: Lock the complete route, model, prompt, and forwarding contracts

**Files:**
- Create: `tests/test_brainstorm_route_contracts.py`
- Modify: `tests/test_api_constraints.py`
- Modify: `tests/test_route_path_security.py`

- [ ] **Step 1: Add route and OpenAPI characterization tests.**

  Record all 16 routes as ordered tuples of router index, path, method set, and endpoint name. Assert each `APIRoute.endpoint` is the same object exported by `brainstorm_routes`, and compare evaluated signatures including parameter kind, annotations, defaults, and return annotations.

- [ ] **Step 2: Lock request model identity and mutation behavior.**

  Instantiate every request model, snapshot `model_dump(mode="json")`, pass the same object through a monkeypatched service wrapper, and assert object identity plus the unchanged snapshot. Lock the OpenAPI request-body schema references for all body-bearing endpoints.

- [ ] **Step 3: Lock Prompt Registry keys and content.**

  Assert `get_all_prompts()["brainstorm"]` exposes exactly `answer`, `summary`, `contemplate`, and `concept_extract`. Store SHA-256 digests for each prompt list so moving source files cannot silently alter prompt text or task visibility.

- [ ] **Step 4: Lock compatibility hooks and logger namespace.**

  Add tests proving route-level monkeypatches for `connect`, `chat`, `classify_content`, `BRAINSTORM_DIR`, `_build_reference_docs`, and the concept creator are resolved at call time. Assert emitted service records retain logger name `zhiji_backend.routes.brainstorm_routes`.

- [ ] **Step 5: Verify Red.**

  Run:

  ```bash
  PYTHONPATH=src ZHIJI_HOME=/private/tmp/zhiji-brainstorm-contracts \
    .venv/bin/python -m pytest -q \
    tests/test_brainstorm_route_contracts.py \
    tests/test_api_constraints.py \
    tests/test_route_path_security.py
  ```

  Expected: new extraction/forwarding assertions fail because the five service modules and route wrappers do not exist, while baseline characterization assertions pass.

- [ ] **Step 6: Commit the contract tests.**

  ```bash
  git add tests/test_brainstorm_route_contracts.py tests/test_api_constraints.py tests/test_route_path_security.py
  git commit -m "test: lock brainstorm route extraction contracts"
  ```

### Task 2: Extract question persistence and Markdown ownership

**Files:**
- Create: `src/zhiji_backend/brainstorm_question_service.py`
- Modify: `src/zhiji_backend/routes/brainstorm_routes.py`
- Create: `tests/test_brainstorm_question_service.py`

- [ ] **Step 1: Add failing service tests.**

  Cover list filters and pagination, topic counts, missing/detail responses, judged and linked event serialization, Markdown reads, creation write order, classification success/failure, single and batch deletion, unsafe artifact deletion logging, and done-state updates. Capture exact SQL-visible outcomes and response dictionaries.

- [ ] **Step 2: Verify Red.**

  ```bash
  PYTHONPATH=src ZHIJI_HOME=/private/tmp/zhiji-brainstorm-question \
    .venv/bin/python -m pytest -q tests/test_brainstorm_question_service.py
  ```

  Expected: import failure for `zhiji_backend.brainstorm_question_service`.

- [ ] **Step 3: Move question workflows into the service.**

  Expose dependency-injected functions for list, counts, detail, create, delete, batch delete, and mark done. Pass `connect`, classification, Markdown path, safe-unlink, clock/UUID behavior, and the historical logger from route wrappers. Preserve exact SQL, timestamps, best-effort classification, and file/database ordering.

- [ ] **Step 4: Replace route bodies with thin wrappers and verify Green.**

  Run question service, route contract, path security, and API constraint tests. Confirm `BRAINSTORM_DIR` monkeypatching still affects path resolution.

- [ ] **Step 5: Commit.**

  ```bash
  git add src/zhiji_backend/brainstorm_question_service.py src/zhiji_backend/routes/brainstorm_routes.py tests/test_brainstorm_question_service.py
  git commit -m "refactor: extract brainstorm question service"
  ```

### Task 3: Extract one-shot answer generation

**Files:**
- Create: `src/zhiji_backend/brainstorm_answer_service.py`
- Modify: `src/zhiji_backend/routes/brainstorm_routes.py`
- Modify: `src/zhiji_backend/prompt_registry.py`
- Create: `tests/test_brainstorm_answer_service.py`

- [ ] **Step 1: Add failing answer tests.**

  Cover empty event selection, missing rows, empty article text, per-article prompt construction, exact `chat` arguments, `None` AI fallback, title/text truncation, Markdown append format, link insertion, `content_md` synchronization, merged event IDs, and exact response shape.

- [ ] **Step 2: Verify Red.**

  ```bash
  PYTHONPATH=src ZHIJI_HOME=/private/tmp/zhiji-brainstorm-answer \
    .venv/bin/python -m pytest -q tests/test_brainstorm_answer_service.py
  ```

  Expected: import failure for `zhiji_backend.brainstorm_answer_service`.

- [ ] **Step 3: Move the one-shot answer and latest-answer parser.**

  Preserve prompt text, historical `module="brainstorm"` and task labels, temperature, token limits, timeout, warning text, timestamps, separators, and writes. Keep route-level compatibility facades where Prompt Registry or tests resolve historical helper names.

- [ ] **Step 4: Update Prompt Registry and verify Green.**

  Point `brainstorm.answer` to the new owner without changing task keys or prompt digests. Run answer, route contract, and Prompt Registry tests.

- [ ] **Step 5: Commit.**

  ```bash
  git add src/zhiji_backend/brainstorm_answer_service.py src/zhiji_backend/routes/brainstorm_routes.py src/zhiji_backend/prompt_registry.py tests/test_brainstorm_answer_service.py
  git commit -m "refactor: extract brainstorm answer service"
  ```

### Task 4: Extract multi-turn conversation and summary workflows

**Files:**
- Create: `src/zhiji_backend/brainstorm_conversation_service.py`
- Modify: `src/zhiji_backend/routes/brainstorm_routes.py`
- Modify: `src/zhiji_backend/prompt_registry.py`
- Create: `tests/test_brainstorm_conversation_service.py`

- [ ] **Step 1: Add failing conversation tests.**

  Cover reference document ordering/truncation, message history, reference parsing, empty start/message validation, exact prompts and AI arguments, start/follow-up persistence, malformed `refs_json`, missing question/history/documents, concept context in summaries, summary persistence, and every error dictionary/HTTP exception.

- [ ] **Step 2: Verify Red.**

  ```bash
  PYTHONPATH=src ZHIJI_HOME=/private/tmp/zhiji-brainstorm-conversation \
    .venv/bin/python -m pytest -q tests/test_brainstorm_conversation_service.py
  ```

  Expected: import failure for `zhiji_backend.brainstorm_conversation_service`.

- [ ] **Step 3: Move conversation helpers and workflows.**

  Extract AI call, reference document loading, history loading, reference parsing, start, follow-up, read, and summary. Inject `connect`, `chat`, Markdown path, and compatibility helper callables. Preserve ignored parameters and broad exception-to-error-dictionary behavior.

- [ ] **Step 4: Preserve call-time monkeypatching and Prompt Registry.**

  Route wrappers must forward route-level `_build_reference_docs` and related facades at call time. Point `brainstorm.summary` to the extracted owner while preserving prompt digests.

- [ ] **Step 5: Verify Green and commit.**

  Run conversation, answer, route contract, API constraint, and Prompt Registry tests, then commit:

  ```bash
  git add src/zhiji_backend/brainstorm_conversation_service.py src/zhiji_backend/routes/brainstorm_routes.py src/zhiji_backend/prompt_registry.py tests/test_brainstorm_conversation_service.py
  git commit -m "refactor: extract brainstorm conversation service"
  ```

### Task 5: Extract bidirectional contemplation

**Files:**
- Create: `src/zhiji_backend/brainstorm_contemplation_service.py`
- Modify: `src/zhiji_backend/routes/brainstorm_routes.py`
- Modify: `src/zhiji_backend/prompt_registry.py`
- Create: `tests/test_brainstorm_contemplation_service.py`

- [ ] **Step 1: Add failing contemplation tests.**

  Cover invalid direction, missing/empty entities, linked and cached rows, candidate exclusion, exact limits and source filters, exact prompt/AI arguments, high/medium/low persistence, result ordering, stale cached events, fenced JSON, valid JSON, malformed/truncated JSON recovery, and parse-failure logging.

- [ ] **Step 2: Verify Red.**

  ```bash
  PYTHONPATH=src ZHIJI_HOME=/private/tmp/zhiji-brainstorm-contemplate \
    .venv/bin/python -m pytest -q tests/test_brainstorm_contemplation_service.py
  ```

  Expected: import failure for `zhiji_backend.brainstorm_contemplation_service`.

- [ ] **Step 3: Move contemplation workflows.**

  Extract direction dispatch, linked-question lookup, event-to-question matching, question-to-event matching, sorting, AI invocation, and JSON recovery. Preserve SQL connection timing, cache write behavior, task labels, prompt text, and logger text even where the historical behavior is awkward.

- [ ] **Step 4: Update Prompt Registry and verify Green.**

  Point `brainstorm.contemplate` to the new owner and preserve all four prompt task digests. Run contemplation and route contract tests.

- [ ] **Step 5: Commit.**

  ```bash
  git add src/zhiji_backend/brainstorm_contemplation_service.py src/zhiji_backend/routes/brainstorm_routes.py src/zhiji_backend/prompt_registry.py tests/test_brainstorm_contemplation_service.py
  git commit -m "refactor: extract brainstorm contemplation service"
  ```

### Task 6: Extract concept parsing and precipitation

**Files:**
- Create: `src/zhiji_backend/brainstorm_concept_service.py`
- Modify: `src/zhiji_backend/routes/brainstorm_routes.py`
- Modify: `src/zhiji_backend/prompt_registry.py`
- Create: `tests/test_brainstorm_concept_service.py`

- [ ] **Step 1: Add failing concept tests.**

  Cover missing question, missing summary, primary and related concept parsing, duplicate names, existing concept flags, duplicate precipitation, linked-context construction, exact concept creator arguments, back-link insertion, success response, and HTTP 500/logging on creation failure.

- [ ] **Step 2: Verify Red.**

  ```bash
  PYTHONPATH=src ZHIJI_HOME=/private/tmp/zhiji-brainstorm-concepts \
    .venv/bin/python -m pytest -q tests/test_brainstorm_concept_service.py
  ```

  Expected: import failure for `zhiji_backend.brainstorm_concept_service`.

- [ ] **Step 3: Move concept workflows.**

  Extract summary parsing and precipitation. Inject `connect`, reference document loading, and a call-time concept creator so monkeypatches and the runtime ingest import remain compatible. Preserve regexes, response text, exception conversion, and link writes.

- [ ] **Step 4: Update Prompt Registry, verify Green, and commit.**

  Point `brainstorm.concept_extract` at the new owner while preserving registry content. Run concept, conversation, route contract, and Prompt Registry tests, then commit:

  ```bash
  git add src/zhiji_backend/brainstorm_concept_service.py src/zhiji_backend/routes/brainstorm_routes.py src/zhiji_backend/prompt_registry.py tests/test_brainstorm_concept_service.py
  git commit -m "refactor: extract brainstorm concept service"
  ```

### Task 7: Retire the oversized-file baseline and verify integration

**Files:**
- Modify: `structure-baseline.json`
- Modify: `tests/test_brainstorm_route_contracts.py` only if final integration coverage requires tightening

- [ ] **Step 1: Check ownership and file sizes.**

  Confirm `brainstorm_routes.py` contains only request models, route declarations, security/compatibility facades, and dependency forwarding. Run `wc -l` and require the route plus every new production module to be at most 400 lines.

- [ ] **Step 2: Retire only the brainstorm route baseline entry.**

  Remove `src/zhiji_backend/routes/brainstorm_routes.py` from `structure-baseline.json`. Do not lower unrelated baselines or add Ruff ignores.

- [ ] **Step 3: Run focused and full verification.**

  ```bash
  PYTHONPATH=src ZHIJI_HOME=/private/tmp/zhiji-brainstorm-final \
    .venv/bin/python -m pytest -q tests/test_brainstorm_*.py \
    tests/test_api_constraints.py tests/test_route_path_security.py

  PYTHONPATH=src ZHIJI_HOME=/private/tmp/zhiji-brainstorm-final \
    .venv/bin/python -m pytest -q

  env PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH \
    UV_BIN=/Users/yuk/Documents/zhiji/ki/.worktrees/dependency-supply-chain/.venv/bin/uv \
    scripts/check.sh

  env ZHIJI_STRUCTURE_BASE_REF=origin/main \
    .venv/bin/python scripts/check_structure_baseline.py

  git diff --check origin/main...HEAD
  ```

  Expected: all tests and gates pass; the structure report has one fewer oversized file and no new Ruff ignore.

- [ ] **Step 4: Request independent whole-branch review.**

  Review `origin/main..HEAD` for route/OpenAPI drift, SQL or prompt changes, dependency forwarding errors, logger changes, circular imports, and missing behavior coverage. Fix all Critical and Important findings, then rerun focused and full checks.

- [ ] **Step 5: Commit and publish for review.**

  ```bash
  git add structure-baseline.json src/zhiji_backend tests
  git commit -m "build: retire brainstorm routes structural baseline"
  git push -u origin codex/structure-cleanup-brainstorm-services
  gh pr create --draft --base main --fill
  ```

  Wait for `check` and `supply-chain` CI. Do not merge or deploy automatically.
