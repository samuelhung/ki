import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import { escapeHtml, sanitizeHtml } from '../../safeHtml.ts';
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

const pageUrl = new URL('../../pages/SeriesDetail.tsx', import.meta.url);
const formatUrl = new URL('./seriesDetailFormat.tsx', import.meta.url);
const hookUrl = new URL('./useSeriesDetail.ts', import.meta.url);
const summaryPanelUrl = new URL('./SeriesSummaryPanel.tsx', import.meta.url);
const memberPanelUrl = new URL('./SeriesMemberPanel.tsx', import.meta.url);
const modules = readSourceModules([pageUrl, formatUrl, hookUrl, summaryPanelUrl, memberPanelUrl]);
const implementation = combinedSource(modules);
const pageModule = modules.find((module) => module.name === 'SeriesDetail.tsx');
assert.ok(pageModule);
const page = pageModule.source;

test('series detail preserves the exact exported data type and callbacks', () => {
  assertExportedObjectType(modules, 'SeriesDetailData', {
    id: { type: 'string', optional: false },
    name: { type: 'string', optional: false },
    description: { type: 'string|null', optional: false },
    member_ids: { type: 'string', optional: false },
    sort_order: { type: 'string|null', optional: false },
    status: { type: 'string', optional: false },
    intro: { type: 'string', optional: true },
    summary: { type: 'string', optional: true },
    paper: { type: 'string', optional: true },
    created_at: { type: 'string', optional: false },
    updated_at: { type: 'string', optional: true },
    members: { type: 'SeriesMember[]', optional: false },
  });
  assert.match(page, /const id = seriesId \|\| routeId/);
  assert.match(implementation, /onSeriesChange\?\.\(/);
  assert.match(implementation, /onDeleted\?\.\(/);
});

test('series reference and markdown helpers can move while preserving behavior', () => {
  const helpers = loadPureDeclarations(
    modules,
    ['REF_COLORS', 'refColor', 'refsToHtml', 'summaryToHtml'],
    { escapeHtml, sanitizeHtml },
  );
  assert.equal(helpers.refColor(1), 'text-blue-400 hover:text-blue-200');
  assert.equal(helpers.refColor(9), 'text-blue-400 hover:text-blue-200');
  assert.match(helpers.refsToHtml('来源 [2]'), /class="ref-link text-amber-400 hover:text-amber-200" data-ref="2"/);
  const summary = helpers.summaryToHtml('## 结构化速览\n### 判断\n- **重点** [1]\n<script>alert(1)</script>');
  assert.doesNotMatch(summary, /^<h3[^>]*>结构化速览<\/h3>/);
  assert.match(summary, /data-ref="1"/);
  assert.doesNotMatch(summary, /<script>/);
  assert.match(summary, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(helpers.summaryToHtml('## 结构化速览\n正文', 'paper'), />结构化速览<\/h3>/);
});

test('series endpoints preserve suggestion count generation deletion and refresh semantics', () => {
  assert.match(implementation, /apiFetch\(`\/api\/ingest\/series\/\$\{id\}`\)/);
  assert.match(implementation, /apiFetch\(`\/api\/ingest\/series\/\$\{id\}\/suggestions`\)/);
  assert.match(implementation, /const items = d\.suggestions \|\| \[\];\s*setSuggestions\(items\)/);
  assert.match(implementation, /待确认 \(\{suggestions\.length\}\)/);
  for (const [suffix, method] of [['intro', 'PUT'], ['summary', 'PUT'], ['paper', 'PUT'], ['members', 'POST'], ['expand', 'POST']]) {
    assert.match(implementation, new RegExp(`apiFetch\\(\\\`/api/ingest/series/\\$\\{id\\}/${suffix}\\\`[\\s\\S]{0,100}method: '${method}'`));
  }
  assert.match(implementation, /apiFetch\(`\/api\/ingest\/series\/\$\{id\}`, \{ method: 'DELETE' \}\)/);
  assert.match(implementation, /await loadDetail\(\)/);
  assert.match(implementation, /const \[loadError, setLoadError\] = useState\(''\)/);
  assert.match(implementation, /const \[operationError, setOperationError\] = useState\(''\)/);
});

test('series labels css hooks and branches can move but page forwards exact panel callbacks', () => {
  for (const label of ['专题导言', '结构化速览', '深度分析', '专题内容', '删除专题', '添加待办']) {
    assert.match(implementation, new RegExp(label));
  }
  for (const hook of ['series-detail-legacy-embedded', 'series-detail-legacy-content', 'series-operation-state', 'series-intro-section', 'series-context-action series-summary-action', 'series-context-action series-paper-action']) {
    assert.match(implementation, new RegExp(hook));
  }
  assert.match(page, /if \(embedded\)/);
});

test('series extraction forwards callbacks and exports its real request coordinator', async () => {
  assert.ok(existsSync(hookUrl), 'Task 5.3 must add useSeriesDetail.ts');
  const hook = readFileSync(hookUrl, 'utf8');
  const hookModule = modules.find((module) => module.name === 'useSeriesDetail.ts');
  assert.ok(hookModule);
  assertNamedImports(hookModule, '../ingest/requestLifecycle', ['RequestLifecycle']);
  assertNamedImports(hookModule, '../ingest/ingestRequestPolicy', ['isLatestRequest']);
  await assertRequestCoordinatorBehavior(loadRequestCoordinatorFactory(hookModule));

  assert.ok(existsSync(formatUrl), 'Task 5.3 must add seriesDetailFormat.tsx');
  assert.ok(existsSync(summaryPanelUrl), 'Task 5.3 must add SeriesSummaryPanel.tsx');
  assert.ok(existsSync(memberPanelUrl), 'Task 5.3 must add SeriesMemberPanel.tsx');
  const format = readFileSync(formatUrl, 'utf8');
  for (const helper of ['refColor', 'refsToHtml', 'summaryToHtml']) {
    assert.match(format, new RegExp(`export function ${helper}\\b`));
  }
  assertForwardedCallbacks(pageModule, 'SeriesSummaryPanel', {
    onGenerateIntro: 'handleGenerateIntro',
    onGenerateSummary: 'handleGenerateSummary',
    onGeneratePaper: 'handleGeneratePaper',
    onReferenceClick: 'handleRefClick',
  });
  assertForwardedCallbacks(pageModule, 'SeriesMemberPanel', {
    onToggleMember: 'togglePanel',
    onOpenMember: 'handleOpenMember',
  });
  assert.match(page, /useSeriesDetail\(/);
  assert.match(hook, /isCurrent|sequence/);
});

test('series id changes reset mutation ui and only committed effects switch selected owners', () => {
  const hook = readFileSync(hookUrl, 'utf8');
  const ownerFactory = loadPureDeclarations(modules, ['createSelectedSeriesOwner']);
  const owners = ownerFactory.createSelectedSeriesOwner();
  const staleSeriesA = owners.select('series-a');

  owners.invalidate(staleSeriesA);
  const seriesB = owners.select('series-b');
  owners.invalidate(seriesB);
  const currentSeriesA = owners.select('series-a');

  assert.equal(owners.isCurrent(staleSeriesA), false, 'returning to an id must not revive its stale owner');
  assert.equal(owners.isCurrent(currentSeriesA), true, 'the latest selected owner must remain current');

  const hookStart = hook.indexOf('export function useSeriesDetail');
  const layoutEffectStart = hook.indexOf('useLayoutEffect(', hookStart);
  assert.notEqual(layoutEffectStart, -1, 'selected owner changes must use a committed layout effect');
  assert.doesNotMatch(hook.slice(hookStart, layoutEffectStart), /selectedSeriesOwner\.select\(/, 'render must not switch the selected owner');
  const ownerEffect = hook.slice(layoutEffectStart, hook.indexOf('\n  useEffect(', layoutEffectStart));
  assert.match(ownerEffect, /selectedSeriesOwner\.select\(id\)/);
  assert.match(ownerEffect, /return \(\) => selectedSeriesOwner\.invalidate\(owner\)/);

  const idEffect = hook.match(/useEffect\(\(\) => \{([\s\S]*?)\n  \}, \[id, embedded\]\);/)?.[1] || '';
  for (const reset of [
    "setLoadError('')",
    "setOperationError('')",
    'setIntroGenerating(false)',
    'setSummaryGenerating(false)',
    'setPaperGenerating(false)',
    'setDeleting(false)',
    'setConfirmDelete(false)',
    'setBatchAdding(false)',
    'setShowProgress(false)',
    "setProgressStage('adding')",
    'setRefreshing(false)',
    'setShowSuggestions(false)',
    'setSelectedIds([])',
  ]) {
    assert.ok(idEffect.includes(reset), `selected-id effect must reset ${reset}`);
  }
});

test('series status polling stays single-flight and schedules only after settle', async () => {
  const hook = readFileSync(hookUrl, 'utf8');
  const pollerFactory = loadPureDeclarations(modules, ['createSingleFlightPoller']);
  let resolveSlowRequest;
  const slowRequest = new Promise((resolve) => { resolveSlowRequest = resolve; });
  const scheduled = [];
  const cancelled = [];
  let pollCalls = 0;
  let timerId = 0;
  const poller = pollerFactory.createSingleFlightPoller({
    poll: async () => { pollCalls += 1; await slowRequest; },
    schedule: (callback, delay) => {
      const timer = { id: ++timerId, callback, delay };
      scheduled.push(timer);
      return timer;
    },
    cancel: (timer) => cancelled.push(timer.id),
  });

  poller.start();
  assert.equal(scheduled.length, 1);
  assert.equal(scheduled[0].delay, 2000);
  scheduled.shift().callback();
  await Promise.resolve();
  assert.equal(pollCalls, 1);
  assert.equal(poller.isInFlight(), true);

  poller.wake();
  assert.equal(pollCalls, 1, 'a visibility wake must not replace a slow in-flight request');
  assert.equal(scheduled.length, 0, 'the next tick must wait for the current request to settle');

  resolveSlowRequest();
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(poller.isInFlight(), false);
  assert.equal(scheduled.length, 1, 'settling the request must schedule exactly one next tick');

  const pendingTimer = scheduled[0];
  poller.stop();
  assert.deepEqual(cancelled, [pendingTimer.id]);
  pendingTimer.callback();
  await Promise.resolve();
  assert.equal(pollCalls, 1, 'stopping the poller must suppress pending ticks');
  assert.doesNotMatch(hook, /setInterval\(poll, 2000\)/);
  assert.match(hook, /poller\.stop\(\)/);
  assert.match(hook, /lifecycle\.abort\(\)/);
});
