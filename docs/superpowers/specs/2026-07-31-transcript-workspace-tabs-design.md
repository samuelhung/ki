# Transcript Workspace Tabs Design

## Goal

Replace the three separate transcript action dialogs with one continuous transcript workspace. The workspace keeps the approved human-first workflow while reducing the title-row actions to one `转写处理` entry.

The existing `专题发现` overlay is the visual and interaction reference: one Dock/Bento window, a persistent header, a three-item tab row, a bounded content region, and controls that remain visible at compact viewport sizes.

## Entry Point And Frame

While `转写原文` is active, show one right-aligned `转写处理` button beside the content title. Opening it creates a viewport-level portal using the existing transcript Dock/Bento frame and backdrop, so the top navigation and bottom Dock remain below the modal layer.

The window title is `转写处理`. Its header and close control remain stable while the tab content changes. Closing the workspace is blocked during a save, AI confirmation, or restore operation. Closing with unsaved manual edits requires confirmation.

## Tabs

The tab row contains:

1. `人工修正`
2. `AI 语义分段`
3. `修订记录`

`人工修正` is the default tab whenever the workspace is opened from the title-row button. Tab changes do not create revisions or start AI work by themselves.

### 人工修正

Show the current active transcript in the editable text area. Saving creates a manual revision through the existing API, including when the user saves unchanged text to record that review is complete.

After a successful save:

- keep the workspace open;
- update the active transcript snapshot and metadata;
- clear the dirty state;
- automatically switch to `AI 语义分段`;
- do not start semantic segmentation automatically.

If saving fails, remain on `人工修正`, preserve the edited text, and show the existing actionable error.

### AI 语义分段

The tab is always visible. Before a manual revision is active, it is disabled and communicates `请先完成人工修正并保存`.

After manual review, the tab presents an explicit `开始语义分段` action. Starting the action uses the existing segmentation task and polling flow. Processing, failure, validation failure, ready preview, regeneration, and confirmation all stay inside this tab.

The ready state compares `人工修正版` with `AI 分段预览`. Desktop uses synchronized side-by-side panes; compact layouts stack the panes. Confirming the preview creates the segmented revision and refreshes the active transcript without closing the workspace. The tab then shows the confirmed state and keeps revision history available through its own tab.

AI output remains subject to the existing invariant: punctuation, whitespace, and paragraph boundaries may change; body characters may not change. Entering or switching to this tab never bypasses backend validation.

### 修订记录

Show the existing revision list and read-only content viewer. Selecting a revision loads its full content. Restoring a historical revision requires confirmation and creates a new restored revision.

After a successful restore, keep the workspace open, refresh the transcript snapshot, and remain on `修订记录` so the new active version is immediately visible.

## State Ownership

Use one workspace-open state and one active-tab state instead of three independent dialog-open states. The existing transcript workflow hook continues to own transcript loading, manual edits, segmentation polling, confirmation, revision selection, and restoration.

The tab container coordinates only presentation transitions:

- opening the workspace selects `人工修正`;
- successful manual save selects `AI 语义分段`;
- starting AI work does not open another dialog;
- successful segmentation confirmation stays on the AI tab;
- opening history selects `修订记录`;
- changing the selected event closes the workspace and clears transient state.

The current editor, comparison, and revision bodies should remain focused components. They render inside the shared workspace rather than owning separate portals or modal frames.

## Responsive Layout

Match the `专题发现` tab treatment and spacing using transcript-specific class names. Do not couple transcript behavior to discovery business classes.

The workspace has a fixed responsive height bounded by `100svh`. Its header, tabs, and contextual footer remain visible. Only the active tab's main content area scrolls:

- the manual editor scrolls inside its text area;
- both comparison panes scroll independently and synchronize reading position;
- the revision list and selected revision content scroll independently.

At compact widths, tab labels remain fully visible. The comparison panes stack vertically, and revision history changes from two columns to a bounded list above the content viewer. No modal content may extend behind the top navigation or bottom Dock.

## Error And Transition Rules

- A failed manual save keeps the user's unsaved text.
- A failed or expired AI task keeps the manual revision active and exposes retry in the AI tab.
- A stale-base `409` shows the existing refresh-required message and never switches tabs automatically.
- Closing AI processing cancels frontend polling but does not apply partial output.
- Tab switching during processing does not start a second task; returning to the AI tab shows the current task state.
- Restoring or confirming a revision never regenerates the AI summary automatically; the existing stale-summary notice remains authoritative.

## Verification

Automated coverage must verify:

- the title row exposes one `转写处理` entry rather than three dialog actions;
- the workspace owns one portal and the three tab labels;
- opening selects `人工修正`;
- successful manual save keeps the workspace open and selects the AI tab without starting AI;
- the AI tab is disabled until a manual revision is active;
- AI processing, preview, failure, retry, and confirmation render inside the shared workspace;
- revision selection and restore render inside the shared workspace;
- event changes reset the workspace and transient task state;
- unsaved-edit, saving, confirming, and restoring close guards remain intact.

Browser acceptance uses `390x844` and `1024x768` viewports. For all three tabs, verify the backdrop covers the viewport, the header/tabs/footer remain visible, the intended inner region scrolls, and top/bottom hit testing resolves to the backdrop rather than navigation or Dock controls.

## Scope

This change consolidates the existing transcript UI. It does not change revision storage, API contracts, AI validation rules, segmentation prompts, summary-staleness behavior, or production data.
