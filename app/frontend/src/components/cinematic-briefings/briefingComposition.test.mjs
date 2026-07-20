import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const curtain = readFileSync(new URL('../../CurtainContext.tsx', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../../pages/KiNavigationShell.tsx', import.meta.url), 'utf8');
const packageJson = readFileSync(new URL('../../../package.json', import.meta.url), 'utf8');
const qaCore = readFileSync(new URL('../../../scripts/qa-cinematic-pages-core.mjs', import.meta.url), 'utf8');
const qaJourney = readFileSync(new URL('../../../scripts/qa-cinematic-user-path.mjs', import.meta.url), 'utf8');
const pageUrl = new URL('../../pages/CinematicBriefings.tsx', import.meta.url);
const cssUrl = new URL('../../pages/CinematicBriefings.css', import.meta.url);
const sharedShellCss = readFileSync(new URL('../../pages/DualNavigationDemo.css', import.meta.url), 'utf8');
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
  assert.match(curtain, /pathname === '\/briefings'/);
});

test('briefing workspace reuses the content-ingest split and detail reader hierarchy', () => {
  assert.match(page, /className="ki-ingest-split-stage briefing-split-stage"/);
  assert.match(page, /className="ki-ingest-list-pane briefing-history-pane"/);
  assert.match(page, /className="ingest-topic-orbit ki-ingest-topic-orbit briefing-history-head"/);
  const leftPane = page.slice(page.indexOf('aria-label="快报历史"'), page.indexOf('aria-label="快报详情"'));
  assert.doesNotMatch(leftPane, /briefing-generate-button/);
  assert.match(page, /className="ingest-detail-reader briefing-detail-surface"/);
  assert.match(page, /className="briefing-detail-actions"[\s\S]*className="briefing-generate-button"/);
  assert.match(page, /className="ingest-detail-tabs briefing-detail-metrics"/);
  assert.match(page, /className="detail-scroll-shell"/);
  assert.match(page, /className="detail-scroll briefing-topic-stream"/);
  assert.doesNotMatch(page, /className="briefing-status-box"/);

  const desktopCss = css.slice(0, css.indexOf('@media (max-width: 760px)'));
  assert.doesNotMatch(desktopCss, /\.briefing-split-stage\s*\{[^}]*grid-template-columns:/s);
  assert.doesNotMatch(desktopCss, /\.briefing-history-pane\s*\{[^}]*--ki-list-width:/s);
  assert.doesNotMatch(desktopCss, /\.briefing-history-list\s*\{[^}]*padding-top:/s);
  assert.doesNotMatch(desktopCss, /\.briefing-history-list\s+\.ki-spotlight-row\s*\{[^}]*width:/s);
  assert.doesNotMatch(desktopCss, /\.briefing-detail-header\s*>\s*span\s*\{/s);
  assert.match(desktopCss, /\.briefing-history-row\s*\{[^}]*min-height:\s*84px/s);
  assert.doesNotMatch(desktopCss, /\.briefing-history-head\s*\{[^}]*grid-template-columns:/s);
  assert.match(desktopCss, /\.briefing-detail-header\s*\{[^}]*position:\s*relative/s);
  assert.match(desktopCss, /\.briefing-detail-actions\s*\{[^}]*position:\s*absolute[^}]*top:\s*0[^}]*right:\s*12px/s);
  assert.match(desktopCss, /\.ki-shell-briefings\s+\.briefing-detail-pane\s+\.briefing-detail-surface\s*\{[^}]*position:\s*relative\s*!important[^}]*width:\s*100%\s*!important[^}]*height:\s*100%\s*!important[^}]*animation:\s*none/s);
  assert.match(desktopCss, /\.briefing-detail-metrics\s*\{[^}]*grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\)/s);
  assert.match(desktopCss, /\.briefing-detail-metrics\s*>\s*span\s*\{[^}]*height:\s*clamp\(42px, 4\.8vh, 56px\)/s);
  assert.match(desktopCss, /\.briefing-event-references\s*>\s*button\s*\{[^}]*border:\s*0[^}]*background:\s*transparent/s);
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

test('list, detail, and generation errors stay retryable and metrics stay below the detail title', () => {
  assert.match(page, /listError[\s\S]*onClick=\{\(\) => void loadBriefings/);
  assert.match(page, /detailError[\s\S]*onClick=\{\(\) => void loadBriefingDetail/);
  assert.match(page, /generateError[\s\S]*onClick=\{handleGenerate\}/);
  assert.match(page, /const metrics = briefingMetrics\(detail\)/);
  assert.match(page, /className="ingest-detail-tabs briefing-detail-metrics"/);
  assert.match(page, /metrics\.typeLabel/);
  assert.match(page, /metrics\.generatedAt/);
  assert.match(page, /metrics\.topicCount/);
  assert.match(page, /metrics\.eventCount/);
});

test('history, detail, and metric timestamps use the shared Beijing formatter', () => {
  assert.match(page, /import \{ formatTimeBeijing \} from '\.\.\/utils'/);
  assert.doesNotMatch(page, /function formatTime\(/);
  assert.match(page, /formatTimeBeijing\(item\.created_at\)/);
  assert.match(page, /formatTimeBeijing\(detail\.created_at \|\| selectedItem\?\.created_at \|\| ''\)/);
  assert.match(page, /formatTimeBeijing\(metrics\.generatedAt\)/);
});

test('briefing workspace has responsive stable panes and no duplicate independent scene', () => {
  assert.equal(existsSync(cssUrl), true, 'CinematicBriefings.css should exist');
  assert.match(sharedShellCss, /\.ki-ingest-split-stage\s*\{[^}]*grid-template-columns:\s*minmax\(320px, 38%\) minmax\(0, 1fr\)[^}]*column-gap:\s*72px/s);
  assert.match(sharedShellCss, /@media \(max-width: 1280px\)[\s\S]*\.ki-ingest-split-stage\s*\{[^}]*grid-template-columns:\s*minmax\(260px, 34%\) minmax\(0, 1fr\)[^}]*column-gap:\s*58px/s);
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

test('briefing QA waits for loaded history and detail terminal states', () => {
  for (const qaSource of [qaCore, qaJourney]) {
    assert.match(qaSource, /快报历史加载中/);
    assert.match(qaSource, /快报详情加载中/);
    assert.match(qaSource, /\.briefing-history-row/);
    assert.match(qaSource, /\.briefing-detail-header/);
    assert.match(qaSource, /暂无快报/);
    assert.match(qaSource, /\.is-error/);
    assert.match(qaSource, /Briefing QA failed: history error/);
    assert.match(qaSource, /Briefing QA failed: detail error/);
    assert.match(qaSource, /historyLoaded\s*&&\s*detailLoaded/);
    assert.match(qaSource, /historyEmpty\s*&&\s*detailEmpty/);
    assert.match(qaSource, /exceptionDetails\.exception\?\.description/);
  }
  assert.match(qaCore, /readyState:\s*'briefings'/);
  assert.match(qaJourney, /briefing_workspace_ready/);
  assert.match(qaJourney, /waitFor\(cdp, 'briefing generation',[\s\S]*await waitForBriefingTerminalState\(cdp, 120000\)/);
});
