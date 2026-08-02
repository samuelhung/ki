# System Dialog And Content Delete Design

## Goal

Replace browser-native confirmation and deletion-error UI in content ingest with a reusable system dialog service. The service must render above the application shell, support asynchronous destructive actions, and show the backend's rejection reason without losing the current content state.

This pass creates the shared dialog foundation and migrates only content-ingest deletion. Existing browser dialogs in other modules remain unchanged and can migrate separately.

## Existing State

- `components/Modal.tsx` is the product's shared modal frame, but it renders in place with `z-50` and has no global orchestration API.
- `useIngestEvents.ts` calls browser `confirm()` before deletion.
- Failed deletion is reduced to a callback and displayed as a temporary toast in `Ingest.tsx`.
- The backend already returns a useful FastAPI `detail` value for expected HTTP failures. Network failures and unstructured server failures require a stable fallback.

## Architecture

### System Dialog Provider

Add a `SystemDialogProvider` near the application root, inside `HashRouter` and outside routed pages. It owns the single visible system dialog and exposes a `useSystemDialog()` hook.

The public API supports:

- `alert(options): Promise<void>` for acknowledgement-only messages.
- `confirmAction(options): Promise<'completed' | 'cancelled' | 'failed'>` for destructive or asynchronous confirmations.

`confirmAction` accepts product copy, a visual tone, confirm/cancel labels, a pending label, an asynchronous `action`, an error title, and an error fallback. The provider invokes the callback only after confirmation. Business modules retain API URLs, request payloads, refresh behavior, and error parsing.

The first version permits one active dialog. Calls received while a dialog is active are serialized in a small FIFO queue so promises are never replaced or left unresolved. Provider unmount cancels the active request and settles queued requests.

### Shared Modal Frame

Keep `Modal` as the visual source of truth. Extend it only where the global service needs stronger platform behavior:

- Render through a portal attached to `document.body`.
- Use the system overlay layer above navigation, dock, cinematic canvases, and page overlays.
- Add `role="dialog"`, `aria-modal="true"`, an accessible title relationship, and initial focus.
- Restore focus to the triggering element when the dialog closes.
- Lock background scrolling while open.
- Support a non-dismissible state while an asynchronous action is running.

Existing colors, border treatment, spacing, radius, typography, close control, and backdrop remain unchanged.

## Content Delete Flow

### Confirmation

Clicking a row's delete icon stops row selection and opens the global destructive confirmation:

- Title: `删除内容`
- Body: `确认删除「{内容标题}」？此操作不可撤销。`
- Secondary action: `取消`
- Destructive action: `确认删除`
- Pending label: `删除中...`

While deletion is pending, both actions, backdrop dismissal, close control, and Escape dismissal are disabled. Repeated confirmation cannot issue a second DELETE request.

### Success

When the DELETE request succeeds:

1. Refresh the current event page.
2. Reconcile selection through the existing list behavior.
3. Close the dialog.
4. Resolve the caller as `completed`.

No success toast is added.

### Rejection Or Failure

Every unsuccessful outcome uses the same global dialog, including business rejection, validation errors, 404, 409, 500, invalid response bodies, network failures, and timeouts.

The pending confirmation changes in place to an acknowledgement state:

- Title: `无法删除`
- Body: the normalized backend `detail`, when it is a non-empty string.
- Fallback: `删除失败，请稍后重试。`
- Action: `知道了`

Structured non-string validation details are converted to a concise readable message only when they can be represented safely; otherwise the fallback is used. Raw HTML, stack traces, secrets, and full response bodies are never rendered.

Closing the failure state preserves the current list and selection. A failed request does not trigger an optimistic removal.

## Ownership Boundaries

- `SystemDialogProvider`: global rendering, lifecycle, queueing, focus, dismissal, pending state, and error-state transition.
- `Modal`: shared visual frame and platform-level portal/accessibility behavior.
- `useIngestEvents`: event loading, DELETE request, response validation, error normalization, and list refresh.
- `Ingest`: supplies the selected event title and invokes the system dialog flow.
- `EmbeddedIngestList`: continues to emit the event id and click event; it does not own dialog state.

The global service must not import ingest APIs or know event models.

## Error Normalization

Add a focused deletion-response helper with these rules:

1. Successful HTTP responses return normally.
2. For non-success responses, parse JSON once when possible.
3. Use a trimmed string `detail` as the reason.
4. If `detail` is a small validation array, join its human-readable `msg` values.
5. Ignore unsupported objects, HTML, and oversized text.
6. Network exceptions preserve a short existing `Error.message` only when safe; otherwise use the fallback.

The UI always receives a plain text reason.

## Testing

### Automated

- Dialog provider tests cover alert acknowledgement, confirm cancellation, async completion, pending lock, action rejection changing to error state, queue settlement, Escape behavior, and focus restoration.
- Modal contracts cover portal rendering, system layer, accessibility attributes, and non-dismissible mode.
- Content-ingest tests prove browser `confirm()` is removed, exactly one DELETE request is sent, backend detail is preserved, fallback errors are stable, success refreshes the list, and failure preserves it.
- Existing frontend cinematic tests, type checking, and production build must remain green.
- Existing backend tests remain green because the API contract is unchanged.

### Local Browser QA

Run the application against isolated local data and verify:

1. Successful deletion of an event with dependent records.
2. A refusal path by deleting the local record after the confirmation is opened, producing a backend 404 reason.
3. Confirmation, pending, and rejection states at desktop and compact widths.
4. Dialog stays above top navigation and bottom dock.
5. Escape/backdrop behavior, focus restoration, and absence of browser-native dialogs.
6. No console errors and SQLite `PRAGMA quick_check` remains `ok`.

Production data is not used for destructive verification.

## Out Of Scope

- Migrating deletion or confirmation dialogs in study, brainstorm, library, tasks, transcript revisions, or other modules.
- Changing backend deletion policy or dependency cleanup.
- Adding success notifications.
- Redesigning the shared modal visual language.
