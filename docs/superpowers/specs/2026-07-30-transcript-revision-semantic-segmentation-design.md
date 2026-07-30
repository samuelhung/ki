# Transcript Revision And Semantic Segmentation Design

## Problem

Content ingestion currently treats the single `result.text` returned by Volcengine AUC as the finished transcript. The pipeline writes that text directly to `events.raw_summary` and `ingest/transcripts/{event_id}.md`, then generates the AI summary from it. There is no separate stage for a person to correct recognition errors, no semantic paragraphing step, and no revision history.

The feature must support both existing and future ingested content without automatically rewriting historical data. A person remains responsible for textual accuracy. AI is responsible only for punctuation and semantic paragraph boundaries after a person has reviewed and saved the transcript.

## Approved Workflow

The workflow is:

1. Preserve an immutable original transcript revision.
2. Let the user open the current transcript, correct it, and save a manual revision. Saving unchanged text is allowed and records that the transcript was reviewed.
3. Enable AI semantic segmentation only while the active revision is a manual revision.
4. Generate an AI preview that may change punctuation and paragraph breaks but may not add, remove, replace, reorder, or change the case of any body character.
5. Show the manual revision and AI preview side by side on desktop or stacked on compact layouts.
6. Apply the AI result only after explicit user confirmation.
7. Keep every accepted revision available for inspection and restoration.

AI segmentation never silently overwrites the manual revision. Cancelling or rejecting a preview leaves the active transcript unchanged.

## Data Model

Add a `transcript_revisions` table with:

- `id`: stable revision identifier.
- `event_id`: owning event, deleted with the event.
- `parent_revision_id`: revision that was active when this revision was created.
- `source_revision_id`: populated when restoring an older revision.
- `kind`: `original`, `manual`, `segmented`, or `restored`.
- `content`: complete transcript text.
- `created_at`: UTC creation time.

Add a `transcript_revision_state` table with one row per initialized event:

- `event_id`: primary key.
- `original_revision_id`: immutable first revision.
- `active_revision_id`: revision represented by `events.raw_summary`.
- `artifact_revision_id`: revision currently published to the transcript Markdown artifact, or null when synchronization is pending.
- `summary_revision_id`: revision from which the current AI summary was generated, or null when no summary exists.
- `updated_at`: UTC update time.

Revision rows are append-only. Restoring a prior revision creates a new `restored` revision whose content matches the selected source revision; it does not reactivate or mutate the historical row.

`events.raw_summary` remains the compatibility field consumed by existing search, classification, summary, brainstorm, and industry-analysis code. The active revision content is also mirrored to `ingest/transcripts/{event_id}.md`.

## Initialization And Compatibility

For a newly ingested event, create the `original` revision from the ASR or extracted document text before treating the ingest as complete. Set it as active. When the initial AI summary succeeds, record that original revision as `summary_revision_id`.

For an existing event with no revision state, initialize lazily when the transcript workflow is first opened or modified:

1. Read the current `events.raw_summary`.
2. Create an immutable `original` revision containing exactly that text.
3. Set it as the active revision.
4. If an AI summary already exists, treat the new original revision as its best-known source revision; otherwise leave `summary_revision_id` null.

No bulk rewrite or production-data migration is required. Schema migration creates only the new empty tables and indexes.

Deleting an event deletes its revision history through the existing event-deletion path and database cascade behavior. Existing transcript and summary artifact deletion remains unchanged.

## API Surface

Add event-scoped transcript endpoints:

- `GET /api/events/{event_id}/transcript`: return active content, active revision metadata, whether manual segmentation is allowed, summary staleness, and revision history metadata.
- `GET /api/events/{event_id}/transcript/revisions/{revision_id}`: return the complete read-only content for one revision owned by the event.
- `PUT /api/events/{event_id}/transcript/manual`: accept complete edited content and `base_revision_id`; create and activate a manual revision.
- `POST /api/events/{event_id}/transcript/segment`: accept `base_revision_id`; start semantic segmentation and return a task identifier.
- `GET /api/events/{event_id}/transcript/segment/{task_id}`: return processing state, failure details, or a validated preview with its base revision.
- `POST /api/events/{event_id}/transcript/segment/{task_id}/confirm`: revalidate and activate the preview as a segmented revision.
- `POST /api/events/{event_id}/transcript/revisions/{revision_id}/restore`: create and activate a restored revision after explicit confirmation.

Manual save, segmentation confirmation, and restoration use optimistic concurrency. Their base revision must still be active. A stale request returns `409 Conflict` and does not create a revision.

Segmentation tasks are temporary and event-scoped. They do not count as revisions, expire after a bounded period, and cannot be confirmed after the event's active revision changes. Repeated confirmation is idempotent and returns the already-created segmented revision.

The existing `POST /api/events/{event_id}/summarize?force=true` endpoint remains the explicit summary-regeneration action. A successful forced summary records the active revision as `summary_revision_id`.

## Body-Character Invariant

Define a canonical body-character sequence by removing:

- all Unicode punctuation categories (`P*`), and
- all Unicode whitespace characters.

Everything else is a body character and must remain code-point-for-code-point identical and in the same order. This includes Chinese and Latin letters, letter case, digits, emoji, mathematical symbols, and other non-punctuation symbols.

The backend validates this invariant:

1. immediately after every AI chunk is returned,
2. after all chunks are reassembled, and
3. again when the user confirms the preview.

If any validation fails, the task fails with a safe user-facing message and the manual revision remains active. The validator reports only the position and class of mismatch in application logs; it does not log transcript content.

Manual editing is not subject to this invariant because correcting body text is the purpose of the manual step.

## AI Segmentation

Use the existing configured AI client under a distinct ingest task name so usage and failures can be observed separately from summarization. The system prompt states that the output must contain the complete input text, may only adjust punctuation and paragraph breaks, and must not explain its work or wrap the result in Markdown fences.

Long transcripts are processed in bounded chunks. Chunk boundaries prefer existing paragraph breaks, sentence punctuation, or whitespace, falling back to a fixed Unicode-character boundary. Each request receives read-only prefix and suffix context plus one marked core chunk, and must return only the transformed core chunk. Context is never copied into output. Validate each transformed core against its original before joining chunks, then validate the full result.

The task reports progress by completed chunk count. A failed chunk fails the whole preview; partial AI output is never shown as an accepted result. Retrying starts a new task from the same still-active manual revision.

## Difference Model

Because body characters are invariant, punctuation and whitespace can be represented as gaps before, between, and after stable body-character anchors. The comparison view aligns those body characters and highlights only changed gap content:

- punctuation additions, removals, and replacements;
- paragraph breaks added or removed;
- other whitespace normalization when present.

This avoids presenting unchanged transcript text as a large character-level diff and remains predictable for long content. The backend returns the preview text; the frontend derives display-only gap differences without modifying either source.

## Interface And Layout

In `ContentDetailPanel`, place `人工修正` and `AI 语义分段` on the same row as the content title, aligned to the right. Show these actions only while the `转写原文` tab is active. Other detail tabs keep the current header.

The title stays on the left with source and status metadata. On compact layouts, the actions wrap below the title and remain right-aligned rather than compressing or truncating the title. Use compact Lucide icons with text labels and existing ingest visual tokens.

`AI 语义分段` is disabled until a manual revision is active. Its tooltip says `请先完成人工修正并保存`. After a manual save, show `已人工校验` and its time in the metadata area. After confirmation, show `已完成语义分段`.

The manual correction surface is a large transcript editor with `取消` and `保存人工修正版`. Unchanged content may be saved. Closing with unsaved changes requires confirmation.

The AI comparison surface contains:

- `人工修正版` and `AI 分段预览` panes;
- highlighted punctuation and paragraph differences;
- task progress and validation status;
- `取消`, `重新生成`, and `确认使用` actions.

Desktop uses side-by-side panes with synchronized reading positions. Compact layouts stack the panes. Both layouts keep stable bounds and independent scrolling so long text does not resize the surrounding workspace.

Add a lightweight `修订记录` entry showing revision type and time. Opening a revision is read-only. Restoration requires a second confirmation and creates a new active restored revision.

## Summary Staleness

The summary is stale when `summary_revision_id` differs from `active_revision_id`. After manual save, segmentation confirmation, or restoration, show `原文已更新，可重新生成 AI 总结`. Do not regenerate or clear the existing summary automatically.

The user may invoke the existing forced-summary action. While regeneration is running, the old summary may remain visible with a processing state; replace it only after generation succeeds. On success, update `summary_revision_id` to the revision actually summarized. If the active revision changes while generation is running, keep the returned summary associated with its input revision and continue to mark it stale.

## Persistence And Failure Handling

The database is the source of truth for the active revision. Revision creation, active-state update, and `events.raw_summary` update occur in one SQLite transaction after the base revision is rechecked.

The Markdown transcript is a compatibility artifact. Update it with a temporary file and atomic replacement after validating the target path. Record `artifact_revision_id` only after publication succeeds. If publication fails, keep the accepted database revision, return a pending-synchronization status rather than full success, and retry publication on the next transcript read or mutation. Detail reads continue to use the database source of truth, preventing a stale artifact from replacing the accepted revision.

AI timeout, empty output, invalid output, task expiry, version conflict, or network failure never changes the active revision. UI errors are actionable and do not expose provider credentials or transcript contents in logs.

## Verification

### Backend

- Unit-test canonicalization with Chinese, Latin case, digits, emoji, symbols, Unicode punctuation, spaces, and newlines.
- Prove punctuation and paragraph-only edits pass while added, deleted, replaced, reordered, or case-changed body characters fail.
- Test lazy initialization, new-ingest initialization, unchanged manual confirmation, segmented confirmation, restoration, and summary staleness.
- Test optimistic-concurrency conflicts, expired tasks, repeated confirmation, event deletion, empty transcripts, and artifact-publication failures.
- Test long-text chunking at paragraph, punctuation, whitespace, and fixed-size boundaries; verify complete reassembly and whole-result validation.
- Confirm active text remains synchronized with `events.raw_summary` and is still consumed by existing search, summary, classification, brainstorm, and industry-analysis paths.

### Frontend

- Verify title-row actions render only on the transcript tab and wrap without overlapping the title at compact widths.
- Verify AI segmentation remains disabled until a manual revision is saved, including an unchanged manual confirmation.
- Test unsaved-edit protection, save failures, task progress, invalid AI output, preview retry, confirmation, stale-version conflict, revision history, and restoration.
- Test punctuation/paragraph gap highlighting and side-by-side versus stacked layouts.
- Verify the stale-summary prompt appears after transcript changes and clears only after a successful summary for the active revision.

### Browser Acceptance

Use a historical event and complete the real path: open transcript, save a manual correction or unchanged confirmation, request semantic segmentation, inspect punctuation and paragraph differences, confirm, refresh, and verify the active content and history persist.

Use a second fixture whose mocked AI result changes a body character. The backend must reject the preview, the manual revision must remain active, and no segmented revision may be created.

Verify desktop and compact viewports with real click targets and scroll behavior. Confirm title and actions do not overlap and long comparison panes remain usable.

## Scope

This work adds on-demand transcript correction, semantic segmentation, version history, restoration, and summary-staleness signaling for existing and future content-ingest events. It does not automatically correct transcription errors, infer omitted speech, batch-process historical content, automatically regenerate summaries, replace the ASR provider, or modify unrelated content-ingest workflows and cinematic effects.
