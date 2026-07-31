import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import {
  assertExportedObjectType,
  assertForwardedCallbacks,
  assertNamedImports,
  assertRequestCoordinatorBehavior,
  combinedSource,
  loadPureDeclarations,
  loadRequestCoordinatorFactory,
  readSourceModules,
} from '../detailPageContractTestUtils.mjs';

const pageUrl = new URL('../../pages/EventDetailPage.tsx', import.meta.url);
const hookUrl = new URL('./useEventDetail.ts', import.meta.url);
const headerUrl = new URL('./EventDetailHeader.tsx', import.meta.url);
const bodyUrl = new URL('./EventDetailBody.tsx', import.meta.url);
const runtimeUrl = new URL('./eventDetailRuntime.ts', import.meta.url);
const transcriptActionsUrl = new URL('./TranscriptActions.tsx', import.meta.url);
const transcriptDialogFrameUrl = new URL('./TranscriptDialogFrame.tsx', import.meta.url);
const transcriptWorkspaceUrl = new URL('./TranscriptWorkspaceDialog.tsx', import.meta.url);
const transcriptEditorPanelUrl = new URL('./TranscriptEditorPanel.tsx', import.meta.url);
const transcriptComparisonPanelUrl = new URL('./TranscriptComparisonPanel.tsx', import.meta.url);
const transcriptRevisionPanelUrl = new URL('./TranscriptRevisionPanel.tsx', import.meta.url);
const dualNavigationCss = readFileSync(new URL('../../pages/DualNavigationDemo.css', import.meta.url), 'utf8');
const packageJson = JSON.parse(readFileSync(new URL('../../../package.json', import.meta.url), 'utf8'));
const checkScript = readFileSync(new URL('../../../../../scripts/check.sh', import.meta.url), 'utf8');
const modules = readSourceModules([
  pageUrl,
  hookUrl,
  headerUrl,
  bodyUrl,
  runtimeUrl,
  transcriptActionsUrl,
]);
const implementation = combinedSource(modules);
const pageModule = modules.find((module) => module.name === 'EventDetailPage.tsx');
assert.ok(pageModule);
const page = pageModule.source;

test('event detail preserves the exact exported event type and page callback ownership', () => {
  assertExportedObjectType(modules, 'EventDetailData', {
    id: { type: 'string', optional: false },
    source_id: { type: 'string', optional: false },
    title: { type: 'string', optional: false },
    title_cn: { type: 'string', optional: true },
    url: { type: 'string', optional: false },
    topic: { type: 'string', optional: false },
    status: { type: 'string', optional: false },
    created_at: { type: 'string', optional: false },
    raw_summary: { type: 'string', optional: true },
    ai_summary: { type: 'string', optional: true },
    overview: { type: 'string', optional: true },
    last_error: { type: 'string', optional: true },
    summary_cn: { type: 'string', optional: true },
    translation_status: { type: 'string', optional: true },
    transcript_path: { type: 'string', optional: true },
    summary_path: { type: 'string', optional: true },
    video_path: { type: 'string', optional: true },
    video_url: { type: 'string', optional: true },
    audio_path: { type: 'string', optional: true },
    document_path: { type: 'string', optional: true },
    associated_questions: { type: 'any[]', optional: true },
  });
  assert.match(page, /const id = eventId \|\| routeId/);
  assert.match(page, /onEventChange\?\.\(/);
});

test('event media status and visible presentation contracts can move together', () => {
  const { STATUS_LABEL, STATUS_COLOR, toMediaPath } = loadPureDeclarations(modules, ['STATUS_LABEL', 'STATUS_COLOR', 'toMediaPath']);
  assert.equal(toMediaPath('/Users/name/app/data/ingest/video/item.mp4'), '/ingest/video/item.mp4');
  assert.equal(toMediaPath('/tmp/item.mp4'), null);
  assert.equal(STATUS_LABEL.processing, '处理中');
  assert.equal(STATUS_LABEL.completed, '已完成');
  assert.equal(STATUS_COLOR.failed, 'text-red-400');
  assert.match(implementation, /useAuthenticatedMediaUrl\(toMediaPath\(/);
  for (const label of ['内容采集', '转写原文', 'AI 总结', '关联问题', '产业分析', '凝神静思', '添加待办']) {
    assert.match(implementation, new RegExp(label));
  }
  for (const hook of ['event-detail-embedded-state', 'event-detail-embedded', 'event-detail-embedded__inner', 'custom-scrollbar']) {
    assert.match(implementation, new RegExp(hook));
  }
});

test('event requests preserve endpoints methods refreshes and errors', () => {
  assert.match(implementation, /const API_BASE = '\/api\/events'/);
  assert.match(implementation, /apiFetch\(`\$\{API_BASE\}\/\$\{id\}`/);
  assert.match(implementation, /apiFetch\(`\$\{API_BASE\}\/\$\{eventId\}\/summarize\?force=true`, \{ method: 'POST' \}\)/);
  assert.match(implementation, /apiFetch\(`\/api\/brainstorm\/event\/\$\{detail\.id\}\/linked-questions`/);
  assert.match(implementation, /apiFetch\('\/api\/chains\/suggestions\/count'/);
  for (const endpoint of ['/api/brainstorm/contemplate', '/api/brainstorm/answer', '/api/chains/analyze', '/api/chains/hints/sync']) {
    assert.match(implementation, new RegExp(`apiFetch\\('${endpoint.replaceAll('/', '\\/')}'[\\s\\S]{0,100}method: 'POST'`));
  }
  assert.match(implementation, /setContemplateError\(e\.message \|\| '凝神静思失败'\)/);
  assert.match(implementation, /setChainError\(e\.message \|\| '分析失败'\)/);
  assert.match(implementation, /setSyncResult\('同步失败: ' \+ e\.message\)/);
});

test('event extraction forwards callbacks and exports its real request coordinator', async () => {
  assert.ok(existsSync(hookUrl), 'Task 5.4 must add useEventDetail.ts');
  const hook = readFileSync(hookUrl, 'utf8');
  const hookModule = modules.find((module) => module.name === 'useEventDetail.ts');
  assert.ok(hookModule);
  assertNamedImports(hookModule, '../ingest/requestLifecycle', ['RequestLifecycle']);
  assertNamedImports(hookModule, '../ingest/ingestRequestPolicy', ['isLatestRequest']);
  await assertRequestCoordinatorBehavior(loadRequestCoordinatorFactory(hookModule));

  assert.ok(existsSync(headerUrl), 'Task 5.4 must add EventDetailHeader.tsx');
  assert.ok(existsSync(bodyUrl), 'Task 5.4 must add EventDetailBody.tsx');
  assert.match(page, /useEventDetail\(/);
  assertForwardedCallbacks(pageModule, 'EventDetailHeader', {
    onSummarize: 'handleSummarize',
    onContemplate: 'handleContemplate',
  });
  assertForwardedCallbacks(pageModule, 'EventDetailBody', {
    onTabChange: 'setTab',
    onLinkQuestions: 'handleContemplateLink',
    onChainAnalyze: 'handleChainAnalyze',
    onSyncHints: 'handleSyncHints',
  });
  assert.match(hook, /signal/);
  assert.match(hook, /isCurrent|sequence/);
  assert.doesNotMatch(hook, /onEventChange/);
});

test('event selection owners stay monotonic while reads and writes use their required signals', () => {
  const { createSelectedEventOwner } = loadPureDeclarations(modules, ['createSelectedEventOwner']);
  const owners = createSelectedEventOwner();
  const staleEventA = owners.select('event-a');
  owners.invalidate(staleEventA);
  const eventB = owners.select('event-b');
  owners.invalidate(eventB);
  const currentEventA = owners.select('event-a');
  assert.equal(owners.isCurrent(staleEventA), false);
  assert.equal(owners.isCurrent(currentEventA), true);

  const hookModule = modules.find((module) => module.name === 'useEventDetail.ts');
  assert.ok(hookModule);
  const postCalls = [];
  const suggestionCountCalls = [];
  function visit(node) {
    if (ts.isCallExpression(node) && node.expression.getText(hookModule.sourceFile) === 'apiFetch') {
      if (node.arguments[0]?.getText(hookModule.sourceFile) === "'/api/chains/suggestions/count'") {
        suggestionCountCalls.push(node);
      }
      const options = node.arguments[1];
      if (options && ts.isObjectLiteralExpression(options)) {
        const method = options.properties.find((property) => (
          ts.isPropertyAssignment(property) && property.name.getText(hookModule.sourceFile) === 'method'
        ));
        if (method && ts.isPropertyAssignment(method) && method.initializer.getText(hookModule.sourceFile) === "'POST'") {
          postCalls.push(options);
        }
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(hookModule.sourceFile);
  assert.equal(postCalls.length, 5);
  for (const options of postCalls) {
    assert.equal(options.properties.some((property) => property.name?.getText(hookModule.sourceFile) === 'signal'), false);
  }
  assert.equal(suggestionCountCalls.length, 2);
  for (const call of suggestionCountCalls) {
    const options = call.arguments[1];
    assert.ok(options && ts.isObjectLiteralExpression(options));
    const signal = options.properties.find((property) => (
      ts.isPropertyAssignment(property) && property.name.getText(hookModule.sourceFile) === 'signal'
    ));
    assert.ok(signal && ts.isPropertyAssignment(signal));
    assert.equal(signal.initializer.getText(hookModule.sourceFile), 'owner.signal');
  }
});

test('event action loading remains authoritative across an A-B-A selection cycle', () => {
  const { createActiveActionRegistry, activeActionState } = loadPureDeclarations(
    modules,
    ['createActiveActionRegistry', 'activeActionState'],
  );
  const actions = createActiveActionRegistry();
  const tokens = [
    actions.begin('summarize', 'event-a'),
    actions.begin('contemplate', 'event-a'),
    actions.begin('chain', 'event-a'),
    actions.begin('sync', 'event-a'),
  ];
  assert.deepEqual(activeActionState(actions, 'event-a'), {
    summarizingId: 'event-a', contemplating: true, contemplateLinking: false, chainLoading: true, syncingHints: true,
  });
  assert.deepEqual(activeActionState(actions, 'event-b'), {
    summarizingId: null, contemplating: false, contemplateLinking: false, chainLoading: false, syncingHints: false,
  });
  assert.equal(actions.begin('summarize', 'event-a'), null, 'the restored loading state must match the duplicate-action guard');
  assert.deepEqual(activeActionState(actions, 'event-a'), {
    summarizingId: 'event-a', contemplating: true, contemplateLinking: false, chainLoading: true, syncingHints: true,
  });
  tokens.forEach((token) => actions.end(token));
  assert.equal(activeActionState(actions, 'event-a').summarizingId, null);
  const hook = readFileSync(hookUrl, 'utf8');
  assert.match(hook, /useSyncExternalStore\(activeActions\.subscribe, activeActions\.getSnapshot, activeActions\.getSnapshot\)/);
  assert.match(hook, /activeActionState\(activeActions, id\)/);
  for (const staleSetter of ['setSummarizingId', 'setContemplating', 'setContemplateLinking', 'setChainLoading', 'setSyncingHints']) {
    assert.doesNotMatch(hook, new RegExp(staleSetter));
  }
});

test('transcript correction UI opens one workspace from the title row', () => {
  for (const url of [
    transcriptActionsUrl,
    transcriptWorkspaceUrl,
    transcriptEditorPanelUrl,
    transcriptComparisonPanelUrl,
    transcriptRevisionPanelUrl,
  ]) assert.ok(existsSync(url), `${url.pathname.split('/').at(-1)} must exist`);

  const header = readFileSync(headerUrl, 'utf8');
  const actions = readFileSync(transcriptActionsUrl, 'utf8');
  assert.match(header, /tab === 'body'/);
  assert.match(header, /transcript-title-row[\s\S]*<h1[\s\S]*transcriptActions/);
  assert.match(header, /flex-wrap/);
  assert.match(header, /justify-between/);
  assert.match(actions, />转写处理</);
  assert.doesNotMatch(actions, />人工修正</);
  assert.doesNotMatch(actions, />AI 语义分段</);
  assert.doesNotMatch(actions, /aria-label="修订记录"/);
  assert.match(actions, /ml-auto/);
  assert.match(page, /<TranscriptWorkspaceDialog/);
  assert.doesNotMatch(page, /<TranscriptEditorDialog/);
  assert.doesNotMatch(page, /<TranscriptComparisonDialog/);
  assert.doesNotMatch(page, /<TranscriptRevisionDialog/);
});

test('one transcript workspace owns the global Dock frame and composes all panels', () => {
  for (const url of [
    transcriptWorkspaceUrl,
    transcriptEditorPanelUrl,
    transcriptComparisonPanelUrl,
    transcriptRevisionPanelUrl,
  ]) assert.ok(existsSync(url), `${url.pathname.split('/').at(-1)} must exist`);
  assert.ok(existsSync(transcriptDialogFrameUrl));

  const frameModule = readSourceModules([transcriptDialogFrameUrl])[0];
  assert.ok(frameModule);
  const frame = frameModule.source;
  const workspace = readFileSync(transcriptWorkspaceUrl, 'utf8');
  const panels = [
    readFileSync(transcriptEditorPanelUrl, 'utf8'),
    readFileSync(transcriptComparisonPanelUrl, 'utf8'),
    readFileSync(transcriptRevisionPanelUrl, 'utf8'),
  ];

  assertNamedImports(frameModule, 'react-dom', ['createPortal']);
  assert.match(frame, /import '\.\.\/\.\.\/pages\/GlobalDockWorkspaceFrame\.css';/);
  assert.match(frame, /document\.querySelector<HTMLElement>\('\.dual-nav-demo'\) \|\| document\.body/);
  assert.match(frame, /dual-nav-action-backdrop global-dock-backdrop global-dock-workspace-backdrop transcript-dialog-backdrop/);
  assert.match(frame, /global-dock-workspace-stage is-wide transcript-dialog-stage/);
  assert.match(frame, /KiMagicBentoFrame/);
  assert.match(frame, /global-dock-workspace-dialog/);
  assert.match(frame, /createPortal\([\s\S]*dialog[\s\S]*portalHost\)/);
  for (const label of ['转写处理', '人工修正', 'AI 语义分段', '修订记录']) {
    assert.match(workspace, new RegExp(label));
  }
  for (const component of ['TranscriptDialogFrame', 'TranscriptEditorPanel', 'TranscriptComparisonPanel', 'TranscriptRevisionPanel']) {
    assert.match(workspace, new RegExp(component));
  }
  assert.equal(workspace.match(/<TranscriptDialogFrame/g)?.length, 1);
  for (const panel of panels) {
    assert.doesNotMatch(panel, /createPortal/);
    assert.doesNotMatch(panel, /TranscriptDialogFrame/);
  }
  assert.doesNotMatch(dualNavigationCss, /\.transcript-editor-dialog textarea\s*\{/);
});

test('the standard cinematic npm and CI path covers every completed detail composition', () => {
  const script = packageJson.scripts['test:cinematic-scene'];
  for (const file of [
    'src/components/cinematic-brainstorm/brainstormDetailComposition.test.mjs',
    'src/components/cinematic-series/seriesDetailComposition.test.mjs',
    'src/components/cinematic-study/studyDetailComposition.test.mjs',
    'src/components/cinematic-ingest/eventDetailComposition.test.mjs',
    'src/components/cinematic-ingest/ingestPageComposition.test.mjs',
    'src/components/react-bits/kiLegacyIngestShellComposition.test.mjs',
  ]) assert.match(script, new RegExp(file.replaceAll('/', '\\/')));
  assert.match(checkScript, /npm run test:cinematic-scene/);
});
