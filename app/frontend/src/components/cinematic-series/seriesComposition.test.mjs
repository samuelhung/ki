import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const curtain = readFileSync(new URL('../../CurtainContext.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/CinematicSeries.tsx', import.meta.url), 'utf8');
const detail = readFileSync(new URL('../../pages/SeriesDetail.tsx', import.meta.url), 'utf8');
const css = `${readFileSync(new URL('./cinematic-series.css', import.meta.url), 'utf8')}\n${readFileSync(new URL('./cinematic-series-detail.css', import.meta.url), 'utf8')}`;

test('series keeps legacy comparison routes while primary list and detail routes share the migrated page', () => {
  assert.match(app, /path="series" element=\{<CinematicSeries \/>\}/);
  assert.match(app, /path="series\/:id" element=\{<CinematicSeries \/>\}/);
  assert.match(app, /path="series-old" element=\{<Series \/>\}/);
  assert.match(app, /path="series-old\/:id" element=\{<SeriesDetail \/>\}/);
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

test('series header keeps task creation and moves deletion into an accessible overflow menu', () => {
  assert.match(detail, />添加待办</);
  assert.match(detail, /aria-label="更多专题操作"/);
  assert.match(detail, /moreMenuOpen/);
  assert.match(detail, /className="series-more-menu"[\s\S]*setConfirmDelete\(true\)/);
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

test('series overflow uses action popover semantics without an incomplete ARIA menu model', () => {
  assert.doesNotMatch(detail, /aria-haspopup="menu"/);
  assert.doesNotMatch(detail, /role="menu(?:item)?"/);
  assert.match(detail, /aria-expanded=\{moreMenuOpen\}/);
});

test('embedded legacy detail wraps long generated content inside compact screens', () => {
  assert.match(css, /\.ki-shell-series \.series-detail-legacy-content\s*\{[^}]*overflow-wrap:\s*anywhere/s);
  assert.match(css, /\.ki-shell-series \.series-detail-legacy-content \*\s*\{[^}]*min-width:\s*0/s);
});
