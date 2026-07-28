import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const curtain = readFileSync(new URL('../../CurtainContext.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/CinematicSeries.tsx', import.meta.url), 'utf8');
const detail = [
  '../../pages/SeriesDetail.tsx',
  './useSeriesDetail.ts',
  './SeriesSummaryPanel.tsx',
  './SeriesMemberPanel.tsx',
].map((path) => readFileSync(new URL(path, import.meta.url), 'utf8')).join('\n');
const viteConfig = readFileSync(new URL('../../../vite.config.ts', import.meta.url), 'utf8');
const packageJson = readFileSync(new URL('../../../package.json', import.meta.url), 'utf8');
const css = `${readFileSync(new URL('./cinematic-series.css', import.meta.url), 'utf8')}\n${readFileSync(new URL('./cinematic-series-detail.css', import.meta.url), 'utf8')}`;

test('series list and detail routes share the migrated page', () => {
  assert.match(app, /path="series" element=\{<CinematicSeries \/>\}/);
  assert.match(app, /path="series\/:id" element=\{<CinematicSeries \/>\}/);
});

test('series routes skip the global curtain like content ingest and toolbox', () => {
  const skipExpression = app.match(/const skipInitialCurtain = ([^;]+);/)?.[1] || '';
  const bypassFunction = curtain.match(/function shouldBypassCurtain[\s\S]*?\n\}/)?.[0] || '';
  assert.match(skipExpression, /location\.pathname === '\/series'/);
  assert.match(skipExpression, /location\.pathname\.startsWith\('\/series\/'\)/);
  assert.match(bypassFunction, /pathname === '\/series'/);
  assert.match(bypassFunction, /pathname\.startsWith\('\/series\/'\)/);
});

test('migrated series uses the content-ingest shell hierarchy and one shared scene canvas', () => {
  assert.match(page, /import KiNavigationShell from/);
  assert.match(page, /import SpotlightListRow from/);
  assert.match(page, /<KiNavigationShell[\s\S]*className="ki-shell-ingest-preview ki-shell-series"[\s\S]*sceneVariant="ingest"/);
  assert.match(page, /className="ki-shell-content"/);
  assert.match(page, /className="ki-shell-legacy-ingest"/);
  assert.match(page, /className="legacy-ingest-root is-shell-embedded cinematic-ingest/);
  assert.match(page, /className="ki-ingest-split-stage"/);
  assert.match(page, /className="ki-ingest-list-pane"/);
  assert.match(page, /className="ki-ingest-detail-pane"/);
  assert.doesNotMatch(page, /CinematicTemplatePage|CinematicLaserWorkspace|LaserFlow|useLaserRenderProfile/);
});

test('series mounts the complete legacy detail directly in the right pane', () => {
  assert.match(page, /<LegacySeriesDetail\s+embedded/);
  assert.match(page, /seriesId=\{selected\.id\}/);
  assert.match(page, /onSeriesChange=\{handleSeriesChange\}/);
  assert.match(page, /onDeleted=\{handleSeriesDeleted\}/);
  assert.doesNotMatch(page, /专题概览|完整内容/);
  assert.match(css, /\.ki-shell-series \.series-detail-legacy-embedded\s*\{[^}]*position:\s*relative[^}]*width:\s*100%[^}]*height:\s*100%/s);
});

test('series discovery actions are handled in place from the global dock', () => {
  assert.match(page, /onGlobalAction=\{handleGlobalAction\}/);
  assert.match(page, /item\.key === 'global'/);
  assert.match(page, /item\.key === 'topic'/);
  assert.match(page, /item\.key === 'compose'/);
  assert.match(page, /globalStage1\(\)/);
  assert.match(page, /open\('topic'\)/);
  assert.match(page, /open\('manual'\)/);
});

test('series list removes inactive status filtering while keeping spotlight rows and search', () => {
  assert.match(page, /topAccessory=/);
  assert.match(page, /className="ki-ingest-list-search"/);
  assert.doesNotMatch(page, /seriesStatus|series-status-tabs|statusTabs/);
  assert.match(page, /filterSeriesItems\(items, seriesQuery, 'all'\)/);
  assert.match(page, /<SpotlightListRow/);
  assert.match(page, /className="ki-ingest-list-row series-list-row"/);
});

test('series AI generation actions live beside the content they update', () => {
  assert.match(detail, /className="series-intro-section[^"]*"[\s\S]*className="series-context-action series-intro-action"[\s\S]*onClick=\{handleGenerateIntro\}/);
  assert.match(detail, /className="series-context-action series-summary-action"[\s\S]*onClick=\{handleGenerateSummary\}/);
  assert.match(detail, /className="series-context-action series-paper-action"[\s\S]*onClick=\{handleGeneratePaper\}/);
  assert.match(detail, /生成结构化速览/);
  assert.match(detail, /生成深度分析/);
});

test('series header exposes task creation and deletion as compact icon actions', () => {
  assert.match(detail, /className=\{embedded \? 'series-header-action series-header-task-action'/);
  assert.match(detail, /aria-label="添加待办"/);
  assert.match(detail, /title="添加待办"/);
  assert.match(detail, /<ListPlus size=\{15\}/);
  assert.match(detail, /className="series-header-action series-header-delete-action"/);
  assert.match(detail, /aria-label="删除专题"/);
  assert.match(detail, /title="删除专题"/);
  assert.match(detail, /<Trash2 size=\{15\}/);
  assert.doesNotMatch(detail, /moreMenuOpen|series-more-menu|更多专题操作|<Ellipsis/);
});

test('valid series route ids drive selection while only invalid routes are replaced', () => {
  assert.match(page, /const routeItem = items\.find\(\(item\) => item\.id === routeId\)/);
  assert.match(page, /if \(routeItem\) \{[\s\S]*setSelectedId\(routeId\)[\s\S]*return;/);
  assert.match(page, /navigate\(fallbackId \? `\/series\/\$\{fallbackId\}` : '\/series', \{ replace: true \}\)/);
  assert.doesNotMatch(page, /routeId && selectedId && routeId !== selectedId[\s\S]*navigate\(`\/series\/\$\{selectedId\}`/);
});

test('series operation failures stay inline instead of replacing the loaded detail', () => {
  assert.match(detail, /const \[loadError, setLoadError\] = useState\(''\)/);
  assert.match(detail, /const \[operationError, setOperationError\] = useState\(''\)/);
  assert.match(detail, /if \(loadError \|\| !series\)/);
  assert.doesNotMatch(detail, /if \(operationError \|\| !series\)/);
  assert.match(detail, /series-operation-state\$\{operationError \? ' is-error' : ''\}/);
});

test('series delete action keeps a fixed compact footprint in the embedded header', () => {
  assert.match(css, /\.series-detail-legacy-embedded \.series-header-delete-action\s*\{[^}]*width:\s*28px[^}]*height:\s*28px[^}]*padding:\s*0/s);
  assert.match(css, /\.series-detail-legacy-embedded \.series-header-task-action\s*\{[^}]*width:\s*28px[^}]*height:\s*28px[^}]*padding:\s*0/s);
});

test('embedded legacy detail wraps long generated content inside compact screens', () => {
  assert.match(css, /\.ki-shell-series \.series-detail-legacy-content\s*\{[^}]*overflow-wrap:\s*anywhere/s);
  assert.match(css, /\.ki-shell-series \.series-detail-legacy-content \*\s*\{[^}]*min-width:\s*0/s);
});

test('series cancels stale detail and manual-search requests', () => {
  assert.match(page, /import \{ RequestLifecycle \} from/);
  assert.match(page, /detailRequestLifecycleRef = useRef\(new RequestLifecycle\(\)\)/);
  assert.match(page, /eventRequestLifecycleRef = useRef\(new RequestLifecycle\(\)\)/);
  assert.match(page, /signal: request\.signal/);
  assert.match(page, /detailRequestLifecycleRef\.current\.abort\(\)/);
  assert.match(page, /eventRequestLifecycleRef\.current\.abort\(\)/);
});

test('series memoizes generated long-form html and coalesces scroll state writes', () => {
  assert.match(detail, /const summaryHtml = useMemo\(/);
  assert.match(detail, /const paperHtml = useMemo\(/);
  assert.match(detail, /__html: summaryHtml/);
  assert.match(detail, /__html: paperHtml/);
  assert.match(detail, /scrollFrameRef = useRef\(0\)/);
  assert.match(detail, /requestAnimationFrame\(commitScrollState\)/);
  assert.doesNotMatch(detail, /onScroll=\{\(\) => \{ if \(id\) viewStateRef\.current\.set/);
});

test('series no longer ships the retired knowledge graph surface or graph libraries', () => {
  assert.doesNotMatch(detail, /SeriesKnowledgeNetwork|vis-network|vis-data|知识网络/);
  assert.doesNotMatch(packageJson, /"vis-network"|"vis-data"|"@xyflow\/react"|"react-markdown"|"remark-gfm"/);
  assert.doesNotMatch(viteConfig, /vis-network|vis-data|vis-vendor|@xyflow|xyflow-vendor|react-markdown|remark-gfm|markdown-vendor/);
});

test('series member expansion does not nest the open-detail button inside another button', () => {
  assert.match(detail, /<div role="button" tabIndex=\{0\} onClick=\{\(\) => togglePanel\(m\.id\)\}/);
  assert.match(detail, /onKeyDown=\{\(event\) => \{ if \(event\.key === 'Enter' \|\| event\.key === ' '\) togglePanel\(m\.id\); \}\}/);
  assert.doesNotMatch(detail, /<button onClick=\{\(\) => togglePanel\(m\.id\)\}[\s\S]{0,900}<button onClick=/);
});
