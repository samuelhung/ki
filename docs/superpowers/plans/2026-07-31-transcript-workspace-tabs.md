# Transcript Workspace Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three transcript dialogs with one `转写处理` workspace containing `人工修正`, `AI 语义分段`, and `修订记录` tabs.

**Architecture:** `TranscriptWorkspaceDialog` owns the single portal-backed Dock/Bento frame, header, close guard, and tab row. Three focused panel components own editing, AI comparison, and revision history content; `useTranscriptWorkflow` owns one workspace-open flag and one active-tab value, and performs the approved transitions without changing backend APIs.

**Tech Stack:** React 19, TypeScript 6, React DOM portals, Lucide React, existing KI Dock/Bento CSS, Node test runner, Vite.

---

## File Map

- Create `app/frontend/src/components/cinematic-ingest/TranscriptWorkspaceDialog.tsx`: single modal frame, tab navigation, close guard, and panel composition.
- Create `app/frontend/src/components/cinematic-ingest/TranscriptEditorPanel.tsx`: manual transcript editor and save footer without modal ownership.
- Create `app/frontend/src/components/cinematic-ingest/TranscriptComparisonPanel.tsx`: idle, processing, failed, ready, confirmed, retry, and confirmation states without modal ownership.
- Create `app/frontend/src/components/cinematic-ingest/TranscriptRevisionPanel.tsx`: revision list, read-only content, and restore controls without modal ownership.
- Modify `app/frontend/src/components/cinematic-ingest/TranscriptDialogFrame.tsx`: keep the shared portal/Bento shell and add an optional tab row slot.
- Modify `app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx`: expose one title-row `转写处理` command.
- Modify `app/frontend/src/components/cinematic-ingest/useTranscriptWorkflow.ts`: replace three dialog flags with one workspace state and implement tab transitions.
- Modify `app/frontend/src/pages/EventDetailPage.tsx`: render one workspace and pass the existing workflow actions into it.
- Modify `app/frontend/src/pages/DualNavigationDemo.css`: add discovery-style transcript tabs and preserve bounded panel scrolling.
- Modify `app/frontend/src/components/cinematic-ingest/transcriptWorkflow.test.mjs`: lock workspace reset and transition contracts.
- Modify `app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs`: lock the single-entry and single-dialog composition.
- Delete `TranscriptEditorDialog.tsx`, `TranscriptComparisonDialog.tsx`, and `TranscriptRevisionDialog.tsx` after their focused panel replacements pass.

### Task 1: Lock The Single Workspace Contract

**Files:**
- Modify: `app/frontend/src/components/cinematic-ingest/transcriptWorkflow.test.mjs`
- Modify: `app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs`

- [ ] **Step 1: Write failing composition assertions**

Update module URLs and the transcript UI test to require one workspace and three panels:

```js
const transcriptWorkspaceUrl = new URL('./TranscriptWorkspaceDialog.tsx', import.meta.url);
const transcriptEditorPanelUrl = new URL('./TranscriptEditorPanel.tsx', import.meta.url);
const transcriptComparisonPanelUrl = new URL('./TranscriptComparisonPanel.tsx', import.meta.url);
const transcriptRevisionPanelUrl = new URL('./TranscriptRevisionPanel.tsx', import.meta.url);

for (const url of [
  transcriptWorkspaceUrl,
  transcriptEditorPanelUrl,
  transcriptComparisonPanelUrl,
  transcriptRevisionPanelUrl,
]) assert.ok(existsSync(url));

assert.match(actions, /转写处理/);
assert.doesNotMatch(actions, />人工修正</);
assert.doesNotMatch(actions, />AI 语义分段</);
assert.doesNotMatch(actions, /aria-label="修订记录"/);
assert.match(page, /<TranscriptWorkspaceDialog/);
assert.doesNotMatch(page, /<TranscriptEditorDialog/);
assert.doesNotMatch(page, /<TranscriptComparisonDialog/);
assert.doesNotMatch(page, /<TranscriptRevisionDialog/);

const workspace = readFileSync(transcriptWorkspaceUrl, 'utf8');
for (const label of ['转写处理', '人工修正', 'AI 语义分段', '修订记录']) {
  assert.match(workspace, new RegExp(label));
}
assert.match(workspace, /TranscriptDialogFrame/);
assert.match(workspace, /TranscriptEditorPanel/);
assert.match(workspace, /TranscriptComparisonPanel/);
assert.match(workspace, /TranscriptRevisionPanel/);
```

Replace the three-dialog frame test with a single-workspace assertion:

```js
assertNamedImports(frameModule, 'react-dom', ['createPortal']);
assert.match(frame, /document\.querySelector<HTMLElement>\('\.dual-nav-demo'\) \|\| document\.body/);
assert.equal((workspace.match(/<TranscriptDialogFrame/g) || []).length, 1);
for (const panel of [editorPanel, comparisonPanel, revisionPanel]) {
  assert.doesNotMatch(panel, /createPortal|TranscriptDialogFrame/);
}
```

- [ ] **Step 2: Write failing workflow transition assertions**

Replace the old three-dialog reset expectations in `transcriptWorkflow.test.mjs`:

```js
assert.match(source, /setWorkspaceOpen\(false\)/);
assert.match(source, /setWorkspaceTab\('manual'\)/);
assert.doesNotMatch(source, /setEditorOpen|setComparisonOpen|setHistoryOpen/);

const saveManual = source.match(/const saveManual[\s\S]*?\}, \[[^\]]*\]\);/)?.[0] || '';
assert.match(saveManual, /await commitActivation\(snapshot\)/);
assert.match(saveManual, /setWorkspaceTab\('segment'\)/);
assert.doesNotMatch(saveManual, /startSegmentation/);

const confirmSegmentation = source.match(/const confirmSegmentation[\s\S]*?\}, \[[^\]]*\]\);/)?.[0] || '';
assert.match(confirmSegmentation, /setTask\(\(current\)/);
assert.doesNotMatch(confirmSegmentation, /setWorkspaceOpen\(false\)/);

const restoreRevision = source.match(/const restoreRevision[\s\S]*?\}, \[[^\]]*\]\);/)?.[0] || '';
assert.match(restoreRevision, /setWorkspaceTab\('history'\)/);
assert.doesNotMatch(restoreRevision, /setWorkspaceOpen\(false\)/);
```

- [ ] **Step 3: Run focused tests and verify the expected failure**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test \
  src/components/cinematic-ingest/transcriptWorkflow.test.mjs \
  src/components/cinematic-ingest/eventDetailComposition.test.mjs
```

Expected: FAIL because `TranscriptWorkspaceDialog.tsx` and the panel files do not exist and the hook still owns three dialog states.

- [ ] **Step 4: Commit the red tests**

```bash
git add app/frontend/src/components/cinematic-ingest/transcriptWorkflow.test.mjs \
  app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs
git commit -m "test: define unified transcript workspace"
```

### Task 2: Consolidate Workflow State And Title Entry

**Files:**
- Modify: `app/frontend/src/components/cinematic-ingest/useTranscriptWorkflow.ts`
- Modify: `app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx`
- Modify: `app/frontend/src/pages/EventDetailPage.tsx`

- [ ] **Step 1: Replace three open flags with workspace state**

Add the exported tab type and state:

```ts
export type TranscriptWorkspaceTab = 'manual' | 'segment' | 'history';

const [workspaceOpen, setWorkspaceOpen] = useState(false);
const [workspaceTab, setWorkspaceTab] = useState<TranscriptWorkspaceTab>('manual');
```

On event changes, reset the workspace and transient state:

```ts
setWorkspaceOpen(false);
setWorkspaceTab('manual');
setEditorText('');
setTask(null);
setSelectedRevision(null);
setRevisionContent('');
```

Replace `openEditor` with:

```ts
const openWorkspace = useCallback(() => {
  if (!transcript) return;
  setEditorText(transcript.content);
  setWorkspaceTab('manual');
  setWorkspaceOpen(true);
  setError('');
}, [transcript]);
```

Add a guarded close action:

```ts
const closeWorkspace = useCallback(() => {
  if (saving || confirming || restoring) return;
  if (editorText !== (transcript?.content || '')
    && !window.confirm('有未保存的人工修正，确认放弃吗？')) return;
  segmentRun.current += 1;
  pollLifecycle.current.abort();
  setSegmenting(false);
  setWorkspaceOpen(false);
}, [confirming, editorText, restoring, saving, transcript?.content]);
```

Keep manual save inside the workspace and switch tabs only after activation succeeds:

```ts
await commitActivation(snapshot);
setEditorText(snapshot.content);
setTask(null);
setWorkspaceTab('segment');
```

At the start of segmentation, set `workspaceTab` to `segment`, clear the previous task, and do not change `workspaceOpen`. After confirmation, keep the workspace open and expose the confirmed task state:

```ts
await commitActivation(snapshot);
setEditorText(snapshot.content);
setTask((current) => current ? {
  ...current,
  status: 'confirmed',
  confirmed_revision_id: snapshot.active_revision.id,
} : current);
```

After restoration, keep the workspace open and on history:

```ts
await commitActivation(snapshot);
setEditorText(snapshot.content);
setTask(null);
setWorkspaceTab('history');
setSelectedRevision(snapshot.active_revision);
setRevisionContent(snapshot.content);
```

Return `workspaceOpen`, `workspaceTab`, `setWorkspaceTab`, `openWorkspace`, and `closeWorkspace`; remove `editorOpen`, `comparisonOpen`, `historyOpen`, their setters, `openEditor`, `openHistory`, and `closeComparison`.

- [ ] **Step 2: Reduce the title row to one command**

Change `TranscriptActions` props to:

```ts
interface TranscriptActionsProps {
  transcript: TranscriptSnapshot | null;
  loading: boolean;
  error: string;
  refreshRequired: boolean;
  onOpen: () => void;
  onRefresh: () => void;
}
```

Render one text-and-icon command while retaining status metadata:

```tsx
<button type="button" onClick={onOpen} disabled={loading || !transcript}
  className="transcript-action-button" title="人工修正、AI 语义分段与修订记录">
  <FilePenLine size={14} />转写处理
</button>
```

- [ ] **Step 3: Wire the single workspace in EventDetailPage**

Replace the three action callbacks with `onOpen={transcriptWorkflow.openWorkspace}`. Remove the three dialog render blocks and add:

```tsx
<TranscriptWorkspaceDialog
  open={transcriptWorkflow.workspaceOpen}
  tab={transcriptWorkflow.workspaceTab}
  transcript={transcriptWorkflow.transcript}
  editorText={transcriptWorkflow.editorText}
  saving={transcriptWorkflow.saving}
  segmenting={transcriptWorkflow.segmenting}
  confirming={transcriptWorkflow.confirming}
  task={transcriptWorkflow.task}
  selectedRevision={transcriptWorkflow.selectedRevision}
  revisionContent={transcriptWorkflow.revisionContent}
  historyLoading={transcriptWorkflow.historyLoading}
  restoring={transcriptWorkflow.restoring}
  error={transcriptWorkflow.error}
  onTabChange={transcriptWorkflow.setWorkspaceTab}
  onEditorChange={transcriptWorkflow.setEditorText}
  onSaveManual={transcriptWorkflow.saveManual}
  onStartSegmentation={transcriptWorkflow.startSegmentation}
  onConfirmSegmentation={transcriptWorkflow.confirmSegmentation}
  onSelectRevision={transcriptWorkflow.loadRevision}
  onRestoreRevision={transcriptWorkflow.restoreRevision}
  onClose={transcriptWorkflow.closeWorkspace}
/>
```

- [ ] **Step 4: Run workflow and type checks**

Run:

```bash
node --experimental-strip-types --test src/components/cinematic-ingest/transcriptWorkflow.test.mjs
npm run typecheck
```

Expected: workflow tests PASS; typecheck still FAILS only because `TranscriptWorkspaceDialog` has not been created.

Do not commit this intermediate state because the page intentionally references the not-yet-created workspace. Continue directly to Task 3 and commit the complete compiling unit there.

### Task 3: Build The Shared Tabbed Workspace

**Files:**
- Create: `app/frontend/src/components/cinematic-ingest/TranscriptWorkspaceDialog.tsx`
- Create: `app/frontend/src/components/cinematic-ingest/TranscriptEditorPanel.tsx`
- Create: `app/frontend/src/components/cinematic-ingest/TranscriptComparisonPanel.tsx`
- Create: `app/frontend/src/components/cinematic-ingest/TranscriptRevisionPanel.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/TranscriptDialogFrame.tsx`
- Delete: `app/frontend/src/components/cinematic-ingest/TranscriptEditorDialog.tsx`
- Delete: `app/frontend/src/components/cinematic-ingest/TranscriptComparisonDialog.tsx`
- Delete: `app/frontend/src/components/cinematic-ingest/TranscriptRevisionDialog.tsx`

- [ ] **Step 1: Add a frame slot for tabs**

Add `navigation?: ReactNode` to `TranscriptDialogFrameProps` and render it after the header:

```tsx
{navigation}
<div className="global-dock-workspace-body transcript-dialog-workspace-body">
  {children}
</div>
```

Change the dialog grid rows to `auto auto minmax(0, 1fr)` through the transcript workspace class rather than changing global Dock dialogs.

- [ ] **Step 2: Extract the manual editor panel**

Move the editor field and footer into `TranscriptEditorPanel` with no `open`, portal, header, Escape listener, or close action:

```tsx
export function TranscriptEditorPanel({ value, saving, error, onChange, onSave }: Props) {
  return <>
    <div className="transcript-editor-field">
      <textarea autoFocus value={value}
        onChange={(event) => onChange(event.target.value)}
        spellCheck={false} aria-label="转写原文编辑器" />
      {error && <p className="transcript-dialog-error">{error}</p>}
    </div>
    <footer className="transcript-workspace-footer">
      <span>保存后将新增一个人工修正版，原始转写不会被覆盖。</span>
      <div><button type="button" className="is-primary" onClick={onSave} disabled={saving}>
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
        保存人工修正版
      </button></div>
    </footer>
  </>;
}
```

- [ ] **Step 3: Extract AI comparison with an explicit idle state**

Preserve `GapAlignedText`, synchronized scroll, processing, failure, validation failure, ready preview, retry, and confirm behavior. When no task exists and segmentation is allowed, render:

```tsx
<div className="transcript-dialog-state transcript-segment-idle">
  <WandSparkles size={22} />
  <strong>按语义整理标点与段落</strong>
  <span>不会修改任何正文字符，生成后需人工确认。</span>
  <button type="button" className="is-primary" onClick={onStart} disabled={segmenting}>
    {segmenting ? <Loader2 size={14} className="animate-spin" /> : <WandSparkles size={14} />}
    开始语义分段
  </button>
</div>
```

When the transcript cannot be segmented, render the disabled prerequisite state. When `task.status === 'confirmed'`, render `AI 分段版本已确认使用` and a `重新生成` action. Keep the existing invariant copy in the footer.

- [ ] **Step 4: Extract revision history panel**

Move the list, selected content, restore confirmation, error, and footer into `TranscriptRevisionPanel`. Remove `open`, portal, header, and close controls. Keep `恢复此版本` disabled for the active revision, loading state, or restore operation.

- [ ] **Step 5: Compose the workspace and tab rules**

Create tab metadata:

```ts
const TABS = [
  { key: 'manual', label: '人工修正', icon: FilePenLine },
  { key: 'segment', label: 'AI 语义分段', icon: Pilcrow },
  { key: 'history', label: '修订记录', icon: History },
] as const;
```

The AI tab is disabled only for an untouched original transcript with no task. A confirmed task must remain reviewable after the active revision becomes `segmented`:

```ts
const segmentTabDisabled = Boolean(
  transcript?.active_revision.kind === 'original' && !task,
);
```

Render one frame and discovery-style navigation:

```tsx
<TranscriptDialogFrame
  open={open}
  eyebrow="TRANSCRIPT WORKSPACE"
  title="转写处理"
  titleId="transcript-workspace-title"
  description="先完成人工校正，再进行语义分段；所有版本均可回看。"
  icon={FilePenLine}
  dialogClassName="transcript-workspace-dialog"
  closeDisabled={saving || confirming || restoring}
  onClose={onClose}
  navigation={<nav className="transcript-workspace-tabs" aria-label="转写处理阶段">
    {TABS.map((item) => {
      const disabled = item.key === 'segment' && segmentTabDisabled;
      return <button key={item.key} type="button"
        className={tab === item.key ? 'is-active' : ''}
        disabled={disabled}
        title={disabled ? '请先完成人工修正并保存' : undefined}
        onClick={() => onTabChange(item.key)} data-bento-suspend>
        <item.icon /><span>{item.label}</span>
      </button>;
    })}
  </nav>}
>
  {tab === 'manual' && <TranscriptEditorPanel
    value={editorText}
    saving={saving}
    error={error}
    onChange={onEditorChange}
    onSave={onSaveManual}
  />}
  {tab === 'segment' && <TranscriptComparisonPanel
    canSegment={Boolean(transcript?.can_segment)}
    source={transcript?.content || ''}
    task={task}
    segmenting={segmenting}
    confirming={confirming}
    error={error}
    onStart={onStartSegmentation}
    onRegenerate={onStartSegmentation}
    onConfirm={onConfirmSegmentation}
  />}
  {tab === 'history' && transcript && <TranscriptRevisionPanel
    transcript={transcript}
    selectedRevision={selectedRevision}
    revisionContent={revisionContent}
    loading={historyLoading}
    restoring={restoring}
    error={error}
    onSelect={onSelectRevision}
    onRestore={onRestoreRevision}
  />}
</TranscriptDialogFrame>
```

Keep the existing `beforeunload` protection in `TranscriptWorkspaceDialog` while the workspace is open and editor text differs from active transcript content. Handle Escape by calling the same guarded `onClose` function.

- [ ] **Step 6: Delete obsolete dialog owners and run focused tests**

Delete the three old dialog files only after their panel replacements compile. Run:

```bash
node --experimental-strip-types --test \
  src/components/cinematic-ingest/transcriptWorkflow.test.mjs \
  src/components/cinematic-ingest/eventDetailComposition.test.mjs
npm run typecheck
```

Expected: focused tests and TypeScript check PASS.

- [ ] **Step 7: Commit the workspace component unit**

```bash
git add app/frontend/src/components/cinematic-ingest/TranscriptDialogFrame.tsx \
  app/frontend/src/components/cinematic-ingest/TranscriptWorkspaceDialog.tsx \
  app/frontend/src/components/cinematic-ingest/TranscriptEditorPanel.tsx \
  app/frontend/src/components/cinematic-ingest/TranscriptComparisonPanel.tsx \
  app/frontend/src/components/cinematic-ingest/TranscriptRevisionPanel.tsx \
  app/frontend/src/components/cinematic-ingest/useTranscriptWorkflow.ts \
  app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx \
  app/frontend/src/pages/EventDetailPage.tsx \
  app/frontend/src/components/cinematic-ingest/TranscriptEditorDialog.tsx \
  app/frontend/src/components/cinematic-ingest/TranscriptComparisonDialog.tsx \
  app/frontend/src/components/cinematic-ingest/TranscriptRevisionDialog.tsx
git commit -m "feat: add tabbed transcript workspace"
```

### Task 4: Match Discovery Tabs And Verify Responsive Behavior

**Files:**
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`
- Modify: `app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs`

- [ ] **Step 1: Add failing responsive CSS assertions**

Require tab and bounded-content contracts:

```js
assert.match(dualNavigationCss, /\.transcript-workspace-tabs\s*\{/);
assert.match(dualNavigationCss, /\.transcript-workspace-tabs button\.is-active/);
assert.match(dualNavigationCss, /\.transcript-workspace-dialog[\s\S]*grid-template-rows:\s*auto auto minmax\(0, 1fr\)/);
assert.match(dualNavigationCss, /\.transcript-comparison-pane[\s\S]*overflow:\s*auto/);
assert.match(dualNavigationCss, /@media \(max-width: 760px\)[\s\S]*\.transcript-workspace-tabs/);
```

Run the focused composition test and confirm it fails because the tab styles do not exist.

- [ ] **Step 2: Add transcript-specific discovery-style tabs**

Implement:

```css
.transcript-workspace-dialog {
  grid-template-rows: auto auto minmax(0, 1fr);
}

.transcript-workspace-tabs {
  display: flex;
  gap: 22px;
  margin-top: 20px;
  border-bottom: 1px solid rgba(255, 255, 255, .065);
}

.transcript-workspace-tabs button {
  position: relative;
  display: grid;
  min-width: 82px;
  grid-template-rows: 16px auto;
  justify-items: center;
  gap: 4px;
  padding: 0 5px 10px;
  border: 0;
  background: transparent;
  color: rgba(255, 255, 255, .34);
  font-size: var(--dock-font-meta);
}

.transcript-workspace-tabs button::after {
  content: "";
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 1px;
  background: #d9c4ff;
  opacity: 0;
  transform: scaleX(.4);
}

.transcript-workspace-tabs button.is-active { color: rgba(255, 255, 255, .86); }
.transcript-workspace-tabs button.is-active::after { opacity: 1; transform: scaleX(1); }
.transcript-workspace-tabs button:disabled { cursor: not-allowed; opacity: .38; }
```

At `max-width: 760px`, set `gap: 8px`, make each tab `flex: 1`, remove minimum widths, and keep full labels visible. Retain the current stacked comparison and revision layouts.

- [ ] **Step 3: Run the full frontend verification suite**

Run:

```bash
npm run typecheck
npm run build
npm run test:cinematic-scene
npm run lint:explicit-any
git diff --check
```

Expected: typecheck and build exit 0, cinematic tests report 303 or more tests with 0 failures, explicit-any baseline remains unchanged, and diff check is clean.

- [ ] **Step 4: Verify the real local workspace at two viewports**

Build into the isolated local backend and open `http://127.0.0.1:9120/#/ingest`. Use only the temporary transcript QA event.

At `390x844` and `1024x768`, verify:

- the title row has only `转写处理`;
- one modal opens with all three full tab labels;
- manual save keeps the modal open and selects AI without starting a task;
- the disabled AI prerequisite is visible before manual review;
- editor, comparison panes, revision list, and revision content scroll inside their regions;
- header, tabs, and contextual footer never overlap;
- top and bottom `elementFromPoint` calls hit the backdrop rather than navigation or Dock;
- switching tabs during a task does not create a duplicate segmentation request.

- [ ] **Step 5: Commit responsive styling and acceptance contracts**

```bash
git add app/frontend/src/pages/DualNavigationDemo.css \
  app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs
git commit -m "style: unify transcript workspace tabs"
```
