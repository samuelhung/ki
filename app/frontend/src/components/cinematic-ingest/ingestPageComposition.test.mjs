import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import { getModalBackdropHandler } from '../modalLifecycle.ts';
import {
  completeTitleSave,
  createTitleEditorState,
  titleEditorReducer,
} from './titleEditorRuntime.ts';
import {
  assertForwardedCallbacks,
  assertNamedImports,
  combinedSource,
  loadPureDeclarations,
  loadRequestCoordinatorFactory,
  objectArrayValues,
  readSourceModules,
} from '../detailPageContractTestUtils.mjs';

const pageUrl = new URL('../../pages/Ingest.tsx', import.meta.url);
const hookUrl = new URL('./useIngestEvents.ts', import.meta.url);
const workspaceUrl = new URL('./IngestWorkspaceContent.tsx', import.meta.url);
const utilsUrl = new URL('./ingestUtils.ts', import.meta.url);
const detailPanelUrl = new URL('./ContentDetailPanel.tsx', import.meta.url);
const detailActionsUrl = new URL('./useIngestDetailActions.ts', import.meta.url);
const transcriptActionsUrl = new URL('./TranscriptActions.tsx', import.meta.url);
const titleActionButtonUrl = new URL('./TitleActionButton.tsx', import.meta.url);
const titleEditorDialogUrl = new URL('./TitleEditorDialog.tsx', import.meta.url);
const dualNavigationCssUrl = new URL('../../pages/DualNavigationDemo.css', import.meta.url);
const modules = readSourceModules([pageUrl, hookUrl, workspaceUrl, detailPanelUrl, detailActionsUrl, utilsUrl]);
const implementation = combinedSource(modules);
const pageModule = modules.find((module) => module.name === 'Ingest.tsx');
assert.ok(pageModule);
const page = pageModule.source;
const dualNavigationCss = readFileSync(dualNavigationCssUrl, 'utf8');

function loadTitleEditorDialogComponent() {
  const source = readFileSync(titleEditorDialogUrl, 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const ModalStub = function ModalStub() {};
  const jsx = (type, props, key) => ({ type, props: props || {}, key: key ?? null });
  const loaded = { exports: {} };
  const requireModule = (specifier) => {
    if (specifier === 'react') return { useRef: (initial) => ({ current: initial }) };
    if (specifier === 'react/jsx-runtime') return { Fragment: Symbol('Fragment'), jsx, jsxs: jsx };
    if (specifier === 'lucide-react') return { Loader2: 'Loader2', Sparkles: 'Sparkles' };
    if (specifier === '../Modal') return ModalStub;
    throw new Error(`Unexpected TitleEditorDialog dependency: ${specifier}`);
  };
  Function('require', 'module', 'exports', compiled)(requireModule, loaded, loaded.exports);
  return { TitleEditorDialog: loaded.exports.TitleEditorDialog, ModalStub };
}

function findElements(node, predicate, matches = []) {
  if (Array.isArray(node)) {
    node.forEach((child) => findElements(child, predicate, matches));
    return matches;
  }
  if (!node || typeof node !== 'object' || !('props' in node)) return matches;
  if (predicate(node)) matches.push(node);
  findElements(node.props.children, predicate, matches);
  return matches;
}

function elementText(node) {
  if (Array.isArray(node)) return node.map(elementText).join('');
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (!node || typeof node !== 'object' || !('props' in node)) return '';
  return elementText(node.props.children);
}

const { TitleEditorDialog: ExecutableTitleEditorDialog, ModalStub } = loadTitleEditorDialogComponent();

function renderTitleEditorDialog(overrides = {}) {
  return ExecutableTitleEditorDialog({
    open: true,
    input: '当前标题',
    suggestions: [],
    selectedTitle: null,
    generating: false,
    saving: false,
    error: '',
    validationError: '',
    onInputChange: () => undefined,
    onSelectSuggestion: () => undefined,
    onGenerate: () => undefined,
    onSave: () => undefined,
    onClose: () => undefined,
    ...overrides,
  });
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function assertIngestRequestCoordinatorBehavior(createRequestCoordinator) {
  const commits = [];
  const errors = [];
  const coordinator = createRequestCoordinator({
    onCommit: (value) => commits.push(value),
    onError: (error) => errors.push(error),
  });
  for (const method of ['start', 'run', 'isCurrent', 'abort']) {
    assert.equal(typeof coordinator[method], 'function', `request coordinator must expose ${method}()`);
  }
  assert.equal('mutateAndRefresh' in coordinator, false);

  const stale = deferred();
  const staleOwner = coordinator.start();
  const staleRun = coordinator.run({ owner: staleOwner, request: () => stale.promise });
  const currentOwner = coordinator.start();
  assert.equal(staleOwner.signal.aborted, true);
  await coordinator.run({ owner: currentOwner, request: async () => ({ id: 'current' }) });
  stale.resolve({ id: 'stale' });
  await staleRun;
  assert.deepEqual(commits, [{ id: 'current' }]);

  const failure = new Error('request failed');
  const errorOwner = coordinator.start();
  await coordinator.run({ owner: errorOwner, request: async () => { throw failure; } });
  assert.deepEqual(errors, [failure]);

  const abortedOwner = coordinator.start();
  const abortedRun = coordinator.run({
    owner: abortedOwner,
    request: (signal) => new Promise((resolve, reject) => {
      assert.equal(signal, abortedOwner.signal);
      signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
    }),
  });
  coordinator.abort();
  await abortedRun;
  assert.equal(coordinator.isCurrent(abortedOwner), false);
  assert.deepEqual(errors, [failure]);
}

function assertCoordinatorUsedByHook(hookModule) {
  const hookDeclaration = hookModule.sourceFile.statements.find((statement) => (
    ts.isFunctionDeclaration(statement) && statement.name?.text === 'useIngestEvents'
  ));
  assert.ok(hookDeclaration);
  const calls = [];
  function visit(node) {
    if (ts.isCallExpression(node)) calls.push(node.expression.getText(hookModule.sourceFile));
    ts.forEachChild(node, visit);
  }
  visit(hookDeclaration);
  for (const expected of [
    'createRequestCoordinator',
    'eventRequestCoordinator.start',
    'eventRequestCoordinator.run',
    'eventRequestCoordinator.isCurrent',
    'eventRequestCoordinator.abort',
  ]) assert.ok(calls.includes(expected), `useIngestEvents must call ${expected}`);
}

test('ingest detail tabs can move while preserving exact definitions and order', () => {
  assert.deepEqual(objectArrayValues(modules, 'DETAIL_TABS'), [
    { key: 'body', label: '转写原文', meta: 'TRANSCRIPT', icon: 'FileText' },
    { key: 'summary', label: 'AI 总结', meta: 'SUMMARY', icon: 'Sparkles' },
    { key: 'questions', label: '关联问题', meta: 'LINKED Q', icon: 'Link2' },
    { key: 'chain', label: '产业分析', meta: 'INDUSTRY', icon: 'Radio' },
  ]);
  assert.match(implementation, /DETAIL_TABS\.map\(\(tab\) =>/);
  assert.match(implementation, /ingest-tab-trigger launcher-action pixel-command/);
});

test('every embedded content selection opens the transcript tab', () => {
  const detailActions = readFileSync(detailActionsUrl, 'utf8');

  assert.match(detailActions, /useState<DetailTab>\('body'\)/);
  assert.doesNotMatch(detailActions, /setDetailTab\('summary'\)/);
  assert.match(
    detailActions,
    /useEffect\(\(\) => \{[\s\S]*?setDetailTab\('body'\);[\s\S]*?loadDetail\(activeEventId\)/,
  );
  assert.match(
    page,
    /const handleSelectEvent = useCallback\(\(eventId: string\) => \{\s*details\.setDetailTab\('body'\);\s*openDetail\(eventId\);\s*\}, \[details\.setDetailTab, openDetail\]\);/,
  );
  assert.match(page, /onSelect=\{handleSelectEvent\}/);
});

test('ingest endpoints preserve list mutation upload and status polling contracts', () => {
  const hook = readFileSync(hookUrl, 'utf8');
  assert.match(implementation, /source_id: 'douyin,user-upload,user-concept'/);
  assert.match(implementation, /buildEventListPath\(historyTab, debouncedSearch, offset\)/);
  assert.match(implementation, /apiFetch\(`\/api\/ingest\/status\/\$\{eventId\}`, \{ signal \}\)/);
  assert.match(implementation, /apiFetch\('\/api\/ingest\/douyin', \{\s*method: 'POST'/);
  assert.match(implementation, /apiFetch\('\/api\/ingest\/file', \{ method: 'POST', timeoutMs: 900_000, body \}\)/);
  assert.match(hook, /import \{ deleteEventRequest \} from '.\/deleteEventRequest';/);
  assert.match(hook, /await deleteEventRequest\(eventId, apiFetch\);/);
  assert.match(hook, /await loadEventsRef\.current\(\);/);
  assert.doesNotMatch(hook, /const API_BASE =/);
  assert.doesNotMatch(hook, /onDeleteErrorRef/);
});

test('content deletion uses the global async dialog and never browser confirmation or toast errors', () => {
  assert.match(page, /useSystemDialog\(\)/);
  assert.match(page, /systemDialog\.confirmAction\(/);
  assert.match(page, /title: '删除内容'/);
  assert.match(page, /errorTitle: '无法删除'/);
  assert.match(page, /pendingLabel: '删除中\.\.\.'/);
  assert.match(page, /action: \(\) => deleteEvent\(eventId\)/);
  assert.doesNotMatch(implementation, /\bconfirm\(/);
  assert.doesNotMatch(implementation, /onDeleteError/);
  assert.doesNotMatch(page, /showDeleteError/);
});

test('ingest lifecycle source preserves cancellation stale suppression refreshes and errors', () => {
  assert.match(implementation, /eventRequestCoordinator\.start\(\)/);
  assert.match(implementation, /eventRequestCoordinator\.run\(/);
  assert.match(implementation, /eventRequestCoordinator\.isCurrent\(owner\)/);
  assert.match(implementation, /eventRequestCoordinator\.abort\(\)/);
  assert.match(implementation, /error\?\.name !== 'AbortError'/);
  assert.match(implementation, /statusRequestLifecycleRef\.current\.isCurrent\(sequence\)/);
  assert.match(implementation, /statusRequestLifecycleRef\.current\.abort\(\)/);
  assert.match(implementation, /await loadEventsRef\.current\(\)/);
  assert.match(implementation, /setEventsError\(error\.message \|\| '加载事件列表失败'\)/);
});

test('ingest list queries are committed callback inputs instead of render-phase refs', () => {
  const hook = readFileSync(hookUrl, 'utf8');
  assert.doesNotMatch(hook, /listQueryRef/);
  assert.match(hook, /buildEventListPath\(historyTab, debouncedSearch, offset\)/);
  assert.match(hook, /\}, \[debouncedSearch, eventRequestCoordinator, historyTab\]\);/);
});

test('ingest labels css hooks and embedded composition can move together', () => {
  for (const label of ['搜索内容标题', '提交抖音视频', '上传文件', '分享文本（从抖音复制）', '分类（可选）']) {
    assert.match(implementation, new RegExp(label));
  }
  assert.match(implementation, /legacy-ingest-root is-shell-embedded cinematic-ingest/);
  assert.match(implementation, /<EmbeddedIngestList/);
  assert.match(implementation, /<ContentDetailPanel/);
  assert.match(implementation, /<EmbeddedIngestWorkspace/);
});

test('embedded ingest exposes title and transcript icon actions from the body title row', () => {
  const workspace = readFileSync(workspaceUrl, 'utf8');
  const detailPanel = readFileSync(detailPanelUrl, 'utf8');
  const transcriptActions = readFileSync(transcriptActionsUrl, 'utf8');

  assert.match(page, /useTranscriptWorkflow\(/);
  assert.match(page, /useTitleEditor\(/);
  assert.match(page, /import \{ TitleActionButton \} from/);
  assert.match(page, /import \{ TitleEditorDialog \} from/);
  assert.match(page, /import \{ TranscriptActionButton, TranscriptStatus \} from/);
  assert.match(page, /titleActions=\{<div className="transcript-title-actions ml-auto flex shrink-0 items-center gap-1\.5">[\s\S]*<TitleActionButton[\s\S]*<TranscriptActionButton[\s\S]*iconOnly/);
  assert.ok(page.indexOf('<TitleActionButton') < page.indexOf('<TranscriptActionButton'));
  assert.match(page, /transcriptStatus=\{<TranscriptStatus/);
  assert.match(page, /<TranscriptWorkspaceDialog/);
  assert.doesNotMatch(page, /<TranscriptEditorDialog/);
  assert.doesNotMatch(page, /<TranscriptComparisonDialog/);
  assert.doesNotMatch(page, /<TranscriptRevisionDialog/);
  assert.match(workspace, /titleActions=\{titleActions\}/);
  assert.match(workspace, /transcriptStatus=\{transcriptStatus\}/);
  assert.match(workspace, /transcriptContent=\{transcriptContent\}/);
  assert.match(workspace, /summaryStale=\{summaryStale\}/);
  assert.match(detailPanel, /transcript-title-row[\s\S]*<h2[\s\S]*tab === 'body'[\s\S]*titleActions/);
  assert.doesNotMatch(workspace, /transcriptActionButton/);
  assert.doesNotMatch(detailPanel, /transcriptActionButton/);
  assert.match(transcriptActions, /iconOnly\?: boolean/);
  assert.match(transcriptActions, /iconOnly = false/);
  assert.match(transcriptActions, /iconOnly \? 'transcript-action-icon' : 'transcript-action-button'/);
  assert.match(transcriptActions, /aria-label=\{iconOnly \? '转写处理' : undefined\}/);
  assert.match(transcriptActions, /title=\{iconOnly \? '转写处理' : '人工修正、AI 语义分段与修订记录'\}/);
  assert.match(transcriptActions, /<FilePenLine size=\{14\} \/>\{!iconOnly && '转写处理'\}/);
  assert.match(
    detailPanel,
    /ingest-detail-meta-row[\s\S]*formatTimeBeijing\(item\.created_at\)[\s\S]*item\.topic[\s\S]*tab === 'body'[\s\S]*transcriptStatus/,
  );
  assert.match(detailPanel, /const bodyText = transcriptContent \?\?/);
  assert.match(detailPanel, /summaryStale[\s\S]*原文已更新，可重新生成 AI 总结/);
  assert.match(detailPanel, /if \(summarizing && !detail\?\.ai_summary\)/);
});

test('title action and editor dialog preserve icon accessibility and complete editor states', () => {
  assert.ok(existsSync(titleActionButtonUrl), 'TitleActionButton.tsx must exist');
  assert.ok(existsSync(titleEditorDialogUrl), 'TitleEditorDialog.tsx must exist');
  const titleAction = readFileSync(titleActionButtonUrl, 'utf8');
  const dialog = readFileSync(titleEditorDialogUrl, 'utf8');

  assert.match(titleAction, /import \{ Pencil \} from 'lucide-react'/);
  assert.match(titleAction, /<button[\s\S]*type="button"[\s\S]*className="transcript-action-icon"[\s\S]*title="修改标题"[\s\S]*aria-label="修改标题"[\s\S]*onClick=\{onOpen\}[\s\S]*<Pencil[\s\S]*<\/button>/);
  assert.doesNotMatch(titleAction, />\s*修改标题\s*</);

  assert.match(dialog, />显示标题</);
  assert.match(dialog, /value=\{input\}/);
  assert.match(dialog, /onChange=\{\(event\) => onInputChange\(event\.target\.value\)\}/);
  assert.match(dialog, /disabled=\{saving\}/);
  assert.doesNotMatch(dialog, /maxLength=/);
  assert.match(dialog, /Array\.from\(input\.trim\(\)\)\.length\}\/20/);
  assert.match(dialog, /generating \? <Loader2[\s\S]*: <Sparkles/);
  assert.match(dialog, /disabled=\{generating \|\| saving\}/);
  assert.match(dialog, /generating \? '生成中' : 'AI 生成'/);
  assert.match(dialog, /suggestions\.length > 0/);
  assert.match(dialog, /suggestions\.map\(\(suggestion\) =>/);
  assert.match(dialog, /onClick=\{\(\) => onSelectSuggestion\(suggestion\)\}/);
  assert.match(dialog, /selectedTitle === suggestion \? ' is-selected' : ''/);
  assert.match(dialog, /disabled=\{saving\}/);
  assert.match(dialog, /\{error &&/);
  assert.match(dialog, /\{validationError &&/);
  assert.match(dialog, />\s*取消\s*</);
  assert.match(dialog, /onClick=\{onSave\}[\s\S]*disabled=\{generating \|\| saving \|\| Boolean\(validationError\)\}/);
  assert.match(dialog, /saving \? <Loader2[\s\S]*saving \? '保存中' : '保存标题'/);
});

test('title row actions remain a compact non-wrapping group', () => {
  assert.match(
    dualNavigationCss,
    /\.transcript-title-actions\s*\{[^}]*display:\s*inline-flex;[^}]*flex:\s*0 0 auto;[^}]*align-items:\s*center;[^}]*justify-content:\s*center;[^}]*flex-wrap:\s*nowrap;[^}]*gap:\s*6px;/s,
  );
});

test('title row icon actions keep a fixed 30 pixel square hit area', () => {
  assert.match(
    dualNavigationCss,
    /\.transcript-action-icon\s*\{[^}]*width:\s*30px;[^}]*height:\s*30px;[^}]*min-height:\s*30px;[^}]*padding:\s*0;[^}]*flex:\s*0 0 30px;/s,
  );
});

test('title editor dialog constrains its content and scrolls suggestions', () => {
  assert.match(
    dualNavigationCss,
    /\.title-editor-dialog\s*\{[^}]*display:\s*flex;[^}]*max-height:\s*min\(70vh,\s*560px\);[^}]*min-height:\s*0;[^}]*flex-direction:\s*column;[^}]*gap:\s*14px;[^}]*overflow:\s*hidden;/s,
  );
  assert.match(
    dualNavigationCss,
    /\.title-editor-suggestions\s*\{[^}]*min-height:\s*0;[^}]*overflow-y:\s*auto;/s,
  );
});

test('title editor dialog uses a compact viewport height on narrow screens', () => {
  assert.match(
    dualNavigationCss,
    /@media \(max-width:\s*640px\)\s*\{[\s\S]*?\.title-editor-dialog\s*\{[^}]*max-height:\s*calc\(100dvh - 150px\);/s,
  );
});

test('title editor component locks close paths while saving and wires reliable input focus', () => {
  let closeCalls = 0;
  const savingDialog = renderTitleEditorDialog({
    saving: true,
    onClose: () => { closeCalls += 1; },
  });
  assert.equal(savingDialog.type, ModalStub);
  assert.equal(savingDialog.props.dismissible, false);
  savingDialog.props.onClose();
  assert.equal(closeCalls, 0, 'defensive onClose must ignore close attempts while saving');
  assert.equal(getModalBackdropHandler(savingDialog.props.dismissible, savingDialog.props.onClose), undefined);

  const cancelButton = findElements(
    savingDialog,
    (node) => node.type === 'button' && elementText(node).trim() === '取消',
  )[0];
  assert.ok(cancelButton);
  cancelButton.props.onClick();
  assert.equal(closeCalls, 0);

  const input = findElements(savingDialog, (node) => node.type === 'input')[0];
  assert.ok(input);
  assert.equal(savingDialog.props.initialFocusRef, input.props.ref);
  assert.ok(input.props.ref && typeof input.props.ref === 'object');

  const openDialog = renderTitleEditorDialog({ onClose: () => { closeCalls += 1; } });
  assert.equal(openDialog.props.dismissible, true);
  openDialog.props.onClose();
  assert.equal(closeCalls, 1);
});

test('title editor component exposes candidate selection and clears it after manual input', () => {
  let state = createTitleEditorState();
  state = titleEditorReducer(state, { type: 'start', input: '当前标题' });
  state = titleEditorReducer(state, {
    type: 'generate-success', suggestions: ['候选一', '候选二', '候选三'],
  });
  state = titleEditorReducer(state, { type: 'select-suggestion', value: '候选二' });

  const render = () => renderTitleEditorDialog({
    ...state,
    validationError: '',
    onInputChange: (value) => { state = titleEditorReducer(state, { type: 'change-input', value }); },
    onSelectSuggestion: (value) => { state = titleEditorReducer(state, { type: 'select-suggestion', value }); },
  });
  let dialog = render();
  let candidateButtons = findElements(dialog, (node) => (
    node.type === 'button' && elementText(node).startsWith('候选')
  ));
  assert.deepEqual(candidateButtons.map((button) => button.props['aria-pressed']), [false, true, false]);

  candidateButtons[2].props.onClick();
  assert.equal(state.input, '候选三');
  assert.equal(state.selectedTitle, '候选三');
  dialog = render();
  const input = findElements(dialog, (node) => node.type === 'input')[0];
  input.props.onChange({ target: { value: '人工修改' } });
  assert.equal(state.input, '人工修改');
  assert.equal(state.selectedTitle, null);
  dialog = render();
  candidateButtons = findElements(dialog, (node) => (
    node.type === 'button' && elementText(node).startsWith('候选')
  ));
  assert.deepEqual(candidateButtons.map((button) => button.props['aria-pressed']), [false, false, false]);
});

test('title editor component disables saving throughout generation', () => {
  const dialog = renderTitleEditorDialog({ generating: true });
  const saveButton = findElements(
    dialog,
    (node) => node.type === 'button' && elementText(node).includes('保存标题'),
  )[0];
  assert.ok(saveButton);
  assert.equal(saveButton.props.disabled, true);
});

test('title saves synchronize list and detail state locally before showing success', () => {
  const eventsHook = readFileSync(hookUrl, 'utf8');
  const detailActions = readFileSync(detailActionsUrl, 'utf8');

  assert.match(eventsHook, /const updateEventTitle = useCallback\(\(eventId: string, titleCn: string\) => \{\s*setEvents\(\(current\) => current\.map\(\(event\) => \(\s*event\.id === eventId \? \{ \.\.\.event, title_cn: titleCn \} : event\s*\)\)\);\s*\}, \[\]\);/);
  assert.match(eventsHook, /return \{[\s\S]*updateEventTitle,/);
  assert.match(detailActions, /const updateEventTitle = useCallback\(\(eventId: string, titleCn: string\) => \{\s*setDetail\(\(current\) => current\?\.id === eventId\s*\? \{ \.\.\.current, title_cn: titleCn \}\s*: current\);\s*\}, \[\]\);/);
  assert.match(detailActions, /return \{[\s\S]*updateEventTitle,/);

  const { synchronizeSavedTitle } = loadPureDeclarations(modules, ['synchronizeSavedTitle']);
  const calls = [];
  completeTitleSave(
    { id: 'event-a', title: 'Original', title_cn: '新标题' },
    {
      onSaved: (eventId, titleCn) => synchronizeSavedTitle(
        eventId,
        titleCn,
        (id, title) => calls.push(['list', id, title]),
        (id, title) => calls.push(['detail', id, title]),
      ),
      onSuccess: () => calls.push(['success']),
      onClose: () => calls.push(['close']),
    },
  );
  assert.deepEqual(calls, [
    ['list', 'event-a', '新标题'],
    ['detail', 'event-a', '新标题'],
    ['success'],
    ['close'],
  ]);
  assert.match(page, /synchronizeSavedTitle\(eventId, titleCn, updateEventTitle, details\.updateEventTitle\)/);
  assert.match(page, /const handleTitleSuccess = useCallback\(\(\) => \{\s*setToast\(\{ text: '标题已更新', type: 'success' \}\);\s*\}, \[\]\);/);
  assert.match(page, /useTitleEditor\(\{\s*activeEventId,\s*onSaved: handleTitleSaved,\s*onSuccess: handleTitleSuccess,\s*\}\)/);
  assert.match(page, /if \(titleEditorEvent\) titleEditor\.start\(titleEditorEvent\);/);
  assert.match(page, /<TitleEditorDialog[\s\S]*open=\{titleEditor\.open\}[\s\S]*input=\{titleEditor\.input\}[\s\S]*suggestions=\{titleEditor\.suggestions\}[\s\S]*selectedTitle=\{titleEditor\.selectedTitle\}[\s\S]*generating=\{titleEditor\.generating\}[\s\S]*saving=\{titleEditor\.saving\}[\s\S]*error=\{titleEditor\.error\}[\s\S]*validationError=\{titleEditor\.validationError\}[\s\S]*onInputChange=\{titleEditor\.changeInput\}[\s\S]*onSelectSuggestion=\{titleEditor\.selectSuggestion\}[\s\S]*onGenerate=\{titleEditor\.generate\}[\s\S]*onSave=\{titleEditor\.save\}[\s\S]*onClose=\{titleEditor\.close\}/);
});

test('title editor never binds a stale detail title to the newly active event', () => {
  const { resolveTitleEditorEvent } = loadPureDeclarations(modules, ['resolveTitleEditorEvent']);
  const eventA = { id: 'event-a', title_cn: '标题 A' };
  const eventB = { id: 'event-b', title_cn: '标题 B' };

  assert.equal(resolveTitleEditorEvent('event-b', eventA), null);
  assert.equal(resolveTitleEditorEvent('event-b', null), null);
  assert.equal(resolveTitleEditorEvent('event-b', eventB), eventB);
  assert.equal(resolveTitleEditorEvent('event-a', eventA), eventA);
  assert.equal(resolveTitleEditorEvent(null, eventA), null);

  assert.match(page, /const titleEditorEvent = resolveTitleEditorEvent\(activeEventId, details\.detail\)/);
  assert.match(page, /<TitleActionButton onOpen=\{handleOpenTitleEditor\} disabled=\{!titleEditorEvent\} \/>/);
});

test('embedded summary regeneration waits for fresh transcript lineage while retaining the old summary', () => {
  const detailActionsModule = modules.find((module) => module.name === 'useIngestDetailActions.ts');
  assert.ok(detailActionsModule);
  assertNamedImports(detailActionsModule, './eventSummaryPolling', [
    'summaryRefreshIsComplete',
    'transcriptSummaryIsStale',
  ]);
  assert.match(detailActionsModule.source, /const previousSummary =/);
  assert.match(detailActionsModule.source, /waitForFreshLineage/);
  assert.match(detailActionsModule.source, /summaryRefreshIsComplete\(/);
  assert.match(detailActionsModule.source, /summarizeRequestSeqRef\.current \+= 1;\s+summarizeAbortRef\.current\?\.abort\(\);\s+setSummarizingId\(null\);/);
  assert.doesNotMatch(detailActionsModule.source, /if \(data\.ai_summary\)/);
});

test('request coordinator loader transpiles typed hook exports without resolving React imports', () => {
  const source = `
    import React, { useState } from 'react';
    interface Options { onCommit: (value: string) => void; }
    export function createRequestCoordinator(options: Options) {
      return (value: string) => options.onCommit(value);
    }
  `;
  const module = {
    name: 'typedHook.ts',
    source,
    sourceFile: ts.createSourceFile('typedHook.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS),
  };
  let committed = '';
  const coordinator = loadRequestCoordinatorFactory(module)({ onCommit: (value) => { committed = value; } });
  coordinator('loaded');
  assert.equal(committed, 'loaded');
});

test('ingest extraction forwards callbacks and exports its real request coordinator', async () => {
  assert.ok(existsSync(hookUrl), 'Task 5.6 must add useIngestEvents.ts');
  const hook = readFileSync(hookUrl, 'utf8');
  const hookModule = modules.find((module) => module.name === 'useIngestEvents.ts');
  assert.ok(hookModule);
  assertNamedImports(hookModule, '../ingest/requestLifecycle', ['RequestLifecycle', 'abortableDelay']);
  assertNamedImports(hookModule, '../ingest/ingestRequestPolicy', ['isLatestRequest']);
  await assertIngestRequestCoordinatorBehavior(loadRequestCoordinatorFactory(hookModule));
  assertCoordinatorUsedByHook(hookModule);

  assert.ok(existsSync(workspaceUrl), 'Task 5.6 must add IngestWorkspaceContent.tsx');
  assert.match(page, /useIngestEvents\(/);
  assertForwardedCallbacks(pageModule, 'IngestWorkspaceContent', {
    onRetry: 'loadEvents',
    onLoadMore: 'loadMore',
    onSelect: 'handleSelectEvent',
    onDelete: 'handleDelete',
    onTopicChange: 'handleEmbeddedTopicChange',
    onSearchChange: 'handleEmbeddedSearchChange',
    onSummarize: 'handleEmbeddedSummarize',
    onContemplate: 'details.handleContemplate',
    onLinkQuestions: 'details.handleContemplateLink',
    onChainAnalyze: 'details.handleChainAnalyze',
    onSyncHints: 'details.handleSyncHints',
  });
  assert.doesNotMatch(page, /new RequestLifecycle\(\)|new AbortController\(\)/);
  assert.match(hook, /isLatestRequest|isCurrent|sequence/);
});
