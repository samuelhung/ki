import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../../pages/KiNavigationShell.tsx', import.meta.url), 'utf8');
const packageJson = readFileSync(new URL('../../../package.json', import.meta.url), 'utf8');
const pageUrl = new URL('../../pages/CinematicBriefings.tsx', import.meta.url);
const cssUrl = new URL('../../pages/CinematicBriefings.css', import.meta.url);
const page = existsSync(pageUrl) ? readFileSync(pageUrl, 'utf8') : '';
const css = existsSync(cssUrl) ? readFileSync(cssUrl, 'utf8') : '';

test('briefing page uses the production shell and canonical route', () => {
  assert.equal(existsSync(pageUrl), true, 'CinematicBriefings.tsx should exist');
  assert.match(app, /const CinematicBriefings = lazy\(\(\) => import\('\.\/pages\/CinematicBriefings'\)\)/);
  assert.match(app, /path="briefings" element=\{<CinematicBriefings \/>\}/);
  assert.match(page, /<KiNavigationShell[\s\S]*className="ki-shell-ingest-preview ki-shell-briefings"[\s\S]*sceneVariant="ingest"/);
  assert.match(page, /className="ki-shell-content"/);
  assert.match(page, /className="ki-shell-legacy-ingest"/);
  assert.match(page, /className="legacy-ingest-root is-shell-embedded cinematic-ingest/);
  assert.match(page, /className="ki-ingest-split-stage briefing-split-stage"/);
});

test('navigation places briefing directly after ingestion and resolves active indexes', () => {
  assert.match(shell, /\{ label: '内容采集', href: '\/ingest' \},\s*\{ label: '即时快报', href: '\/briefings' \},\s*\{ label: '专题系列', href: '\/series' \}/);
  assert.match(shell, /pathname\.startsWith\('\/briefings'\)\) return 1/);
  assert.match(shell, /pathname\.startsWith\('\/series'\)\) return 2/);
  assert.match(shell, /pathname\.startsWith\('\/system'\)[\s\S]*return 6/);
});

test('briefings use full-screen layout and bypass the page entry curtain', () => {
  const skipExpression = app.match(/const skipInitialCurtain = ([^;]+);/)?.[1] || '';
  const fullScreenExpression = app.match(/const isCinematicFullScreen = ([^;]+);/)?.[1] || '';
  assert.match(skipExpression, /location\.pathname === '\/briefings'/);
  assert.match(fullScreenExpression, /location\.pathname === '\/briefings'/);
});

test('history and detail requests use independent abortable request lifecycles', () => {
  assert.match(page, /import \{ RequestLifecycle \} from/);
  assert.match(page, /import \{ fetchBriefingDetail, fetchBriefingHistory, generateQuickBriefing \} from/);
  assert.match(page, /listRequestLifecycleRef = useRef\(new RequestLifecycle\(\)\)/);
  assert.match(page, /detailRequestLifecycleRef = useRef\(new RequestLifecycle\(\)\)/);
  assert.match(page, /generateRequestLifecycleRef = useRef\(new RequestLifecycle\(\)\)/);
  assert.match(page, /fetchBriefingHistory\(\{ apiFetch, signal \}\)/);
  assert.match(page, /fetchBriefingDetail\(\{ apiFetch, signal, briefingId \}\)/);
  assert.match(page, /isCurrent\(sequence\)/);
  assert.match(page, /\.current\.abort\(\)/);
});

test('generation posts quick once, disables duplicates, refreshes history, and selects the returned briefing', () => {
  assert.match(page, /generateQuickBriefing\(\{ apiFetch, signal \}\)/);
  assert.match(page, /if \(generating\) return/);
  assert.match(page, /disabled=\{generating\}/);
  assert.match(page, /pendingPreferredIdRef\.current = generated\.id/);
  assert.match(page, /await loadBriefings\(\)/);
});

test('failed generated-history refresh retains the pending preferred id for retry', () => {
  assert.match(page, /pendingPreferredIdRef = useRef\(''\)/);
  assert.match(page, /pendingPreferredIdRef\.current = generated\.id/);
  assert.match(page, /resolveBriefingLoadSelection\(\{/);
  assert.match(page, /pendingPreferredId: pendingPreferredIdRef\.current/);
  assert.match(page, /succeeded: false/);
  assert.match(page, /pendingPreferredIdRef\.current = selection\.pendingPreferredId/);
  assert.match(page, /onClick=\{\(\) => void loadBriefings\(\)\}/);
});

test('briefing detail groups topic summaries and navigates referenced event buttons', () => {
  assert.match(page, /detail\.topics\.map\(\(topic/);
  assert.match(page, /topic\.summary/);
  assert.match(page, /topic\.events\.map\(\(event/);
  assert.match(page, /navigate\(`\/events\/\$\{event\.event_id\}`\)/);
  assert.match(page, /event\.highlight/);
  assert.match(page, /aria-pressed=\{item\.id === selectedId\}/);
});

test('list, detail, and generation errors stay retryable and metrics stay in the bottom status box', () => {
  assert.match(page, /listError[\s\S]*onClick=\{\(\) => void loadBriefings/);
  assert.match(page, /detailError[\s\S]*onClick=\{\(\) => void loadBriefingDetail/);
  assert.match(page, /generateError[\s\S]*onClick=\{handleGenerate\}/);
  assert.match(page, /const metrics = briefingMetrics\(detail\)/);
  assert.match(page, /className="briefing-status-box"/);
  assert.match(page, /metrics\.typeLabel/);
  assert.match(page, /metrics\.generatedAt/);
  assert.match(page, /metrics\.topicCount/);
  assert.match(page, /metrics\.eventCount/);
});

test('briefing workspace has responsive stable panes and no duplicate independent scene', () => {
  assert.equal(existsSync(cssUrl), true, 'CinematicBriefings.css should exist');
  assert.match(css, /\.briefing-split-stage\s*\{[^}]*grid-template-columns:/s);
  assert.match(css, /@media \(max-width: 1440px\)/);
  assert.match(css, /@media \(max-width: 1180px\)/);
  assert.match(css, /min-height:\s*0/);
  assert.match(css, /overflow:\s*hidden/);
  assert.doesNotMatch(page, /CinematicSceneCanvas|CinematicTemplatePage|CinematicLaserWorkspace|LaserFlow|useLaserRenderProfile|<canvas/);
});

test('briefing workspace stacks into bounded history and scrollable detail below 760px', () => {
  const narrowStart = css.indexOf('@media (max-width: 760px)');
  assert.notEqual(narrowStart, -1);
  const narrow = css.slice(narrowStart);
  assert.match(narrow, /\.briefing-split-stage\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)[^}]*grid-template-rows:/s);
  assert.match(narrow, /\.briefing-history-list\s*\{[^}]*max-height:[^}]*overflow:\s*auto/s);
  assert.match(narrow, /\.briefing-detail-pane\s*\{[^}]*min-height:\s*0/s);
  assert.match(narrow, /\.briefing-topic-stream\s*\{[^}]*overflow:\s*auto/s);
});

test('cinematic scene test script includes briefing helper and composition tests', () => {
  assert.match(packageJson, /src\/components\/cinematic-briefings\/briefingRequests\.test\.mjs/);
  assert.match(packageJson, /src\/components\/cinematic-briefings\/briefingWorkspace\.test\.mjs/);
  assert.match(packageJson, /src\/components\/cinematic-briefings\/briefingComposition\.test\.mjs/);
});
