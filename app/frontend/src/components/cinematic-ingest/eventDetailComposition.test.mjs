import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
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
const modules = readSourceModules([pageUrl, hookUrl, headerUrl, bodyUrl]);
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
  assert.match(implementation, /apiFetch\('\/api\/chains\/suggestions\/count'\)/);
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
