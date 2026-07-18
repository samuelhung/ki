import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const curtain = readFileSync(new URL('../../CurtainContext.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/CinematicToolbox.tsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('./cinematic-toolbox.css', import.meta.url), 'utf8');

test('toolbox keeps the legacy route while the primary routes use the migrated page', () => {
  assert.match(app, /path="toolbox" element=\{<CinematicToolbox \/>\}/);
  assert.match(app, /path="tools" element=\{<CinematicToolbox \/>\}/);
  assert.match(app, /path="toolbox-old" element=\{<Toolbox \/>\}/);
});

test('toolbox routes skip the global initial curtain like content ingest', () => {
  const skipExpression = app.match(/const skipInitialCurtain = ([^;]+);/)?.[1] || '';
  assert.match(skipExpression, /location\.pathname === '\/ingest'/);
  assert.match(skipExpression, /location\.pathname === '\/toolbox'/);
  assert.match(skipExpression, /location\.pathname === '\/tools'/);
});

test('toolbox route navigation bypasses the global curtain', () => {
  const bypassFunction = curtain.match(/function shouldBypassCurtain[\s\S]*?\n\}/)?.[0] || '';
  assert.match(bypassFunction, /pathname === '\/ingest'/);
  assert.match(bypassFunction, /pathname === '\/toolbox'/);
  assert.match(bypassFunction, /pathname === '\/tools'/);
});

test('migrated toolbox uses the exact content-ingest shell hierarchy', () => {
  assert.match(page, /import KiNavigationShell from/);
  assert.match(page, /<KiNavigationShell[\s\S]*className="ki-shell-ingest-preview ki-shell-toolbox"[\s\S]*sceneVariant="ingest"/);
  assert.match(page, /className="ki-shell-content"/);
  assert.match(page, /className="ki-shell-legacy-ingest"/);
  assert.match(page, /className="legacy-ingest-root is-shell-embedded cinematic-ingest/);
  assert.match(page, /className="ki-ingest-split-stage"/);
  assert.match(page, /className="ki-ingest-list-pane"/);
  assert.match(page, /className="ingest-topic-orbit ki-ingest-topic-orbit/);
  assert.match(page, /className="ki-ingest-detail-pane"/);
  assert.match(page, /className="ingest-detail-reader toolbox-detail-reader"/);
  assert.match(page, /className="detail-scroll-shell"[\s\S]*className="detail-scroll toolbox-detail-scroll"/);
  assert.doesNotMatch(page, /ki-toolbox-workspace|ki-toolbox-index-pane|ki-toolbox-detail-pane/);
  assert.doesNotMatch(page, /CinematicTemplatePage|CinematicLaserWorkspace|LaserFlow/);
});

test('toolbox preserves the old calculator modes and detailed results', () => {
  assert.match(page, /贷款利率换算器/);
  assert.match(page, /等本等息/);
  assert.match(page, /等额本息/);
  assert.match(page, /方案对比/);
  assert.match(page, /正向/);
  assert.match(page, /反向/);
  assert.match(page, /还款计划明细/);
  assert.match(page, /成本拐点/);
  assert.match(page, /\/#\/toolbox-old/);
});

test('toolbox keeps explanatory and schedule content permanently expanded', () => {
  assert.doesNotMatch(page, /showWhy|showSchedule|toolbox-explain-toggle|toolbox-schedule-toggle/);
  assert.doesNotMatch(page, /ChevronDown|ChevronUp|\bTable\b/);
  assert.match(page, /为什么“销售说的”和“真实成本”不一样/);
  assert.match(page, /className="toolbox-reading-section toolbox-explanation"/);
  assert.match(page, /className="toolbox-reading-section toolbox-schedule-wrap"/);
});

test('toolbox detail uses a continuous reading hierarchy', () => {
  assert.match(page, /className="toolbox-section-label"/);
  assert.match(page, /className="toolbox-primary-results"/);
  assert.match(page, /className="toolbox-metric-list"/);
  assert.match(page, /className="toolbox-reading-section toolbox-explanation"/);
});

test('toolbox delegates stage geometry and responsive scaling to content ingest', () => {
  assert.doesNotMatch(css, /\.ki-toolbox-workspace|\.ki-toolbox-index-pane|\.ki-toolbox-detail-pane/);
  assert.match(css, /\.ki-shell-toolbox \.ki-ingest-list-pane\s*\{[^}]*--ki-list-width:/s);
  assert.match(css, /\.ki-shell-toolbox \.toolbox-detail-reader\s*\{[^}]*width:\s*100%/s);
});

test('calculator state is isolated from the shared navigation shell', () => {
  assert.match(page, /import \{[^}]*memo[^}]*useMemo[^}]*useState[^}]*\} from 'react'/);
  assert.match(page, /const ToolboxWorkspace = memo\(function ToolboxWorkspace/);
  assert.match(page, /<ToolboxWorkspace query=\{query\} \/>/);
});

test('toolbox inherits content-ingest brightness and pointer reveal without overrides', () => {
  assert.doesNotMatch(css, /\.ki-shell-toolbox \.dual-nav-demo__film/);
  assert.doesNotMatch(css, /\.ki-shell-toolbox \.ki-spotlight-row/);
  assert.doesNotMatch(css, /dual-nav-demo__reveal/);
  assert.doesNotMatch(page, /TOPIC_SPOTLIGHT_COLORS|spotlightColor=/);
});

test('toolbox reuses content-ingest detail tabs and only changes the column count', () => {
  assert.match(css, /\.toolbox-detail-tabs\s*\{[^}]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/s);
  assert.doesNotMatch(css, /\.toolbox-detail-tabs \.ingest-tab-trigger/);
});

test('toolbox detail keeps a compact continuous reading rhythm', () => {
  assert.match(css, /\.toolbox-reading-section\s*\{[^}]*padding:\s*8px 0 10px/s);
  assert.match(css, /\.toolbox-section-label\s*\{[^}]*margin-bottom:\s*8px/s);
  assert.match(css, /\.toolbox-primary-results\s*\{[^}]*gap:\s*16px[^}]*padding:\s*0 0 12px/s);
  assert.match(css, /\.toolbox-metric-list > span\s*\{[^}]*min-height:\s*24px[^}]*grid-template-columns:\s*minmax\(76px, 92px\) auto/s);
  assert.match(css, /\.toolbox-schedule span\s*\{[^}]*min-height:\s*24px/s);
  assert.match(css, /\.toolbox-comparison-path > div\s*\{[^}]*min-height:\s*26px/s);
});

test('toolbox fields keep hints inline and inputs on one baseline', () => {
  assert.match(page, /className="toolbox-section-heading"[\s\S]*className="toolbox-section-label">计算参数[\s\S]*className="toolbox-segment"/);
  assert.match(page, /className="toolbox-field-head"[\s\S]*<span>\{label\}<\/span>[\s\S]*\{hint && <small>\{hint\}<\/small>\}/);
  assert.doesNotMatch(page, /<input[^>]+\/>\s*\{hint && <small>/);
});
