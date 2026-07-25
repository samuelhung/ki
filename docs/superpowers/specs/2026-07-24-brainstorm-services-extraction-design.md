# Brainstorm Services Extraction Design

## Goal

Reduce `src/zhiji_backend/routes/brainstorm_routes.py` from 1121 lines to a thin
HTTP adapter by assigning each existing workflow to one focused service. The
refactor must not change the HTTP API, OpenAPI output, SQLite schema or SQL
semantics, AI prompts or parameters, response payloads, errors, logging, files,
or frontend behavior.

## Current Responsibilities

The route module currently owns five separate business areas:

1. Question listing, counts, detail, creation, deletion, batch deletion, status,
   Markdown paths, and classification.
2. One-shot answers generated from selected event documents.
3. Multi-turn conversations, document references, history, and final summaries.
4. Bidirectional contemplation between events and questions, including cache
   reads, AI judgments, partial JSON recovery, and cache writes.
5. Summary concept parsing and concept precipitation into the event store.

Keeping these workflows in one route module obscures their dependencies and
forces unrelated changes through the same 1121-line file.

## Selected Architecture

Keep one `APIRouter` and all request models, decorators, endpoint names,
signatures, and route order in `routes/brainstorm_routes.py`. Endpoint bodies
become thin wrappers that resolve their dependencies at call time and delegate
to the following service modules:

- `brainstorm_question_service.py`: question CRUD, topic counts, Markdown
  synchronization, status updates, and best-effort classification.
- `brainstorm_answer_service.py`: one-shot document answering and answer
  persistence.
- `brainstorm_conversation_service.py`: reference document loading, message
  history, reference parsing, conversation start/follow-up/read, and summary.
- `brainstorm_contemplation_service.py`: linked-question lookup, both matching
  directions, cache persistence, sorting, AI invocation, and malformed JSON
  recovery.
- `brainstorm_concept_service.py`: summary concept parsing, duplicate checks,
  context assembly, and concept precipitation.

Every new production module must remain at or below 400 lines. The route module
should finish below 400 lines and contain only models, route declarations,
security-sensitive path facades, compatibility facades, and dependency
forwarding.

## Compatibility Contract

The extraction must preserve all 16 current routes in their exact order,
including paths, methods, endpoint names, evaluated signatures, parameter kinds,
Pydantic request model identities, request-body schemas, response annotations,
and decorators.

Call-time dependency forwarding is required. Existing tests and integrations
may monkeypatch route-level names such as `connect`, `chat`,
`classify_content`, `BRAINSTORM_DIR`, `_build_reference_docs`, or
`_create_concept`. Thin route-level compatibility facades must continue to make
those patches effective without duplicating business logic.

The following runtime behavior is frozen:

- SQL text, ordering, limits, transaction boundaries, and write ordering.
- Markdown headings, timestamps, separators, append behavior, and `content_md`
  synchronization.
- Prompt text, system messages, AI temperature, token limits, timeouts, module
  names, and task names.
- Response dictionaries, Chinese messages, HTTP status codes, broad exception
  handling, best-effort fallbacks, and logger message text.
- Contemplation cache grouping, sorting, low-result persistence, and partial JSON
  recovery.
- Concept duplicate handling and the runtime import of the ingest concept
  creator.

Service loggers must continue emitting under the historical namespace
`zhiji_backend.routes.brainstorm_routes` so log filters and diagnostics do not
change.

## Prompt Registry

`prompt_registry.py` will follow prompts to their new owning modules while
preserving the exact public task set:

- `answer`
- `summary`
- `contemplate`
- `concept_extract`

Characterization tests will snapshot task keys and prompt content digests before
the extraction. Historical task labels that appear unintuitive, such as the
one-shot answer and contemplation AI calls, are behavior and must not be renamed
in this structural PR.

## Testing Strategy

Before moving production logic, add characterization coverage for:

- Complete route order, metadata, endpoint identity, signatures, model identity,
  and OpenAPI request schemas.
- Route wrapper forwarding and call-time monkeypatch behavior.
- Prompt Registry task keys and prompt content digests.
- Existing Markdown path containment and deletion behavior.
- Exact SQL-visible outcomes, prompts, AI arguments, responses, errors, logging,
  cache behavior, malformed JSON recovery, and concept creation calls for each
  extracted service.

Each service extraction follows Red-Green-Refactor and lands as an independent
commit. Focused tests run after every extraction. Final verification includes the
full backend suite, `scripts/check.sh`, structure baseline comparison against the
current `origin/main`, `git diff --check`, and an independent whole-branch code
review.

## Known Behavior Kept Out Of Scope

This PR will not opportunistically repair existing behavior, including ignored
helper parameters, broad exception catches that return error dictionaries,
historical AI task labels, or connection-lifetime oddities in contemplation.
Those changes require separate behavior-focused specifications and regression
tests.

It also does not change database tables, API validation, prompts, frontend code,
page layout, product copy, or production deployment.

## Delivery

The work starts from the merged `main` commit containing PR #40. After all gates
pass, the branch is pushed as a Draft PR for review. It is not merged or deployed
automatically.
