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
