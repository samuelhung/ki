import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const curtain = readFileSync(new URL('../../CurtainContext.tsx', import.meta.url), 'utf8');
const homeUrl = new URL('../../pages/CinematicHome.tsx', import.meta.url);
const home = existsSync(homeUrl) ? readFileSync(homeUrl, 'utf8') : '';
const homeCss = readFileSync(new URL('../../pages/CinematicHome.css', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../../pages/KiNavigationShell.tsx', import.meta.url), 'utf8');
const dockItems = readFileSync(new URL('../../pages/globalDockItems.ts', import.meta.url), 'utf8');
const dockOverlay = readFileSync(new URL('../../pages/GlobalDockOverlay.tsx', import.meta.url), 'utf8');
const dockAccessOverlay = readFileSync(new URL('../../pages/GlobalDockAccessOverlay.tsx', import.meta.url), 'utf8');
const dockQueueOverlay = readFileSync(new URL('../../pages/GlobalDockQueueOverlay.tsx', import.meta.url), 'utf8');
const preview = readFileSync(new URL('../../pages/LegacyIngestShellPreview.tsx', import.meta.url), 'utf8');
const ingest = readFileSync(new URL('../../pages/Ingest.tsx', import.meta.url), 'utf8');
const ingestWorkspace = readFileSync(new URL('../cinematic-ingest/IngestWorkspaceContent.tsx', import.meta.url), 'utf8');
const ingestEvents = readFileSync(new URL('../cinematic-ingest/useIngestEvents.ts', import.meta.url), 'utf8');
const libraryPage = readFileSync(new URL('../../pages/CinematicLibrary.tsx', import.meta.url), 'utf8');
const gooey = readFileSync(new URL('./GooeyNav.tsx', import.meta.url), 'utf8');
const shellCss = readFileSync(new URL('../../pages/DualNavigationDemo.css', import.meta.url), 'utf8');
const api = readFileSync(new URL('../../api.ts', import.meta.url), 'utf8');
const vite = readFileSync(new URL('../../../vite.config.ts', import.meta.url), 'utf8');
const packageJson = readFileSync(new URL('../../../package.json', import.meta.url), 'utf8');
const qaCore = readFileSync(new URL('../../../scripts/qa-cinematic-pages-core.mjs', import.meta.url), 'utf8');
const gpuQa = readFileSync(new URL('../../../scripts/qa-cinematic-pages-gpu.mjs', import.meta.url), 'utf8');
const productionQaUrl = new URL('../../../scripts/qa-cinematic-pages-production.mjs', import.meta.url);
const productionQa = existsSync(productionQaUrl) ? readFileSync(productionQaUrl, 'utf8') : '';
const spotlightRow = readFileSync(new URL('./SpotlightListRow.tsx', import.meta.url), 'utf8');
const contentDetail = readFileSync(new URL('../cinematic-ingest/ContentDetailPanel.tsx', import.meta.url), 'utf8');
const detailActions = readFileSync(new URL('../cinematic-ingest/useIngestDetailActions.ts', import.meta.url), 'utf8');
const embeddedWorkspace = readFileSync(new URL('../ingest/EmbeddedIngestWorkspace.tsx', import.meta.url), 'utf8');
const embeddedList = readFileSync(new URL('../ingest/EmbeddedIngestList.tsx', import.meta.url), 'utf8');
const embeddedTabs = readFileSync(new URL('../ingest/EmbeddedIngestTopicTabs.tsx', import.meta.url), 'utf8');
const embeddedRow = readFileSync(new URL('../ingest/EmbeddedIngestRow.tsx', import.meta.url), 'utf8');
const embeddedConfig = readFileSync(new URL('../ingest/embeddedIngestConfig.ts', import.meta.url), 'utf8');
const ingestTypes = readFileSync(new URL('../cinematic-ingest/ingestTypes.ts', import.meta.url), 'utf8');
const ingestOverrides = readFileSync(new URL('../cinematic-ingest/cinematic-ingest-final-overrides.css', import.meta.url), 'utf8');

function readProductionTsx(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const child = new URL(`${entry.name}${entry.isDirectory() ? '/' : ''}`, directory);
      if (entry.isDirectory()) return readProductionTsx(child);
      return entry.name.endsWith('.tsx') ? [readFileSync(child, 'utf8')] : [];
    })
    .join('\n');
}

const productionTsx = readProductionTsx(new URL('../../', import.meta.url));

test('home and ingest use the production navigation shell', () => {
  assert.match(app, /const CinematicHome = lazy/);
  assert.match(app, /<Route index element=\{<CinematicHome \/>\}/);
  assert.equal(existsSync(homeUrl), true);
  assert.match(home, /import KiNavigationShell from/);
  assert.match(home, /<KiNavigationShell[\s\S]*className="ki-shell-home cinematic-dashboard"[\s\S]*sceneVariant="today"[\s\S]*laserPrimary=\{false\}[\s\S]*showReveal=\{false\}/);
  assert.match(home, /topAccessory=\{[\s\S]*className="ki-ingest-list-search"/);
  assert.match(home, /placeholder="搜索内容标题"/);
  assert.match(home, /navigate\(`\/ingest\?search=\$\{encodeURIComponent\(query\)\}`\)/);
  assert.doesNotMatch(home, /cinematic-intro-wipe|introDone|intro-spark|intro-line/);
  assert.match(home, /className="cinematic-hero cinematic-home__hero"/);
  assert.match(home, /<span className="brand-title">知几<\/span>/);
  assert.match(home, /<span className="line3">其神乎 见微知著<\/span>/);
  assert.match(home, /真正的洞察，不在声势浩大处，而在一线微光/);
  assert.doesNotMatch(home, /apiFetch|CinematicDashboard|CinematicHud|summary|events|heatmap|taskStats/);
  assert.match(shell, /sceneVariant\?: CinematicSceneVariant/);
  assert.match(shell, /showReveal\?: boolean/);
  assert.match(shell, /topAccessory\?: ReactNode/);
  assert.match(shell, /id="ki-shell-top-accessory"[^>]*>\{topAccessory\}<\/div>/);
  assert.match(app, /CinematicBackdropProvider/);
  assert.match(shell, /useCinematicBackdrop/);
  assert.match(shell, /setBackdrop\(\{[\s\S]*variant:\s*sceneVariant,[\s\S]*laserPrimary,[\s\S]*focus:\s*0/);
  assert.doesNotMatch(shell, /<CinematicScene/);
  assert.match(shellCss, /\.cinematic-backdrop-host\.is-home-active > \.cinematic-scene-canvas\s*\{[^}]*animation:\s*cinematic-home-backdrop-light 1s cubic-bezier\(\.4, 0, \.2, 1\)/s);
  assert.match(home, /import '\.\/CinematicHome\.css'/);
  assert.match(homeCss, /\.cinematic-home__hero\s*\{[^}]*opacity:\s*0[^}]*clip-path:\s*inset\(0 100% 0 0\)[^}]*animation:\s*cinematic-home-copy-brush \.5s[^}]*1s/s);
  assert.match(homeCss, /\.cinematic-home__hero h1\s*\{[^}]*opacity:\s*1[^}]*clip-path:\s*none[^}]*animation:\s*none/s);
  assert.match(homeCss, /\.cinematic-home__hero h1::before,[\s\S]*\.cinematic-home__hero \.brand-title::after\s*\{[^}]*display:\s*none/s);
  assert.match(homeCss, /\.cinematic-home__hero::after\s*\{[^}]*animation:\s*cinematic-home-brush-line \.5s[^}]*1s/s);
  assert.match(homeCss, /@keyframes cinematic-home-backdrop-light/);
  assert.doesNotMatch(homeCss, /@keyframes cinematic-home-backdrop-light\s*\{[\s\S]*?52%\s*\{/);
  assert.match(homeCss, /@keyframes cinematic-home-copy-brush/);
  assert.match(homeCss, /@keyframes cinematic-home-brush-line/);
  assert.match(homeCss, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.cinematic-backdrop-host\.is-home-active > \.cinematic-scene-canvas,[\s\S]*\.cinematic-home__hero::after\s*\{[^}]*animation:\s*none/s);
  assert.match(ingest, /new URLSearchParams\(location\.search\)\.get\('search'\)/);
  assert.match(app, /const LegacyIngestShellPreview = lazy/);
  assert.match(app, /path="ingest" element=\{<LegacyIngestShellPreview \/>\}/);
  assert.match(app, /const skipInitialCurtain = location\.pathname === '\/' \|\| location\.pathname === '\/ingest'/);
  assert.match(app, /useState\(\(\) => !skipInitialCurtain\)/);
  assert.match(curtain, /function shouldBypassCurtain\(to: string \| number\)/);
  assert.match(curtain, /pathname === '\/ingest'/);
  assert.match(curtain, /if \(shouldBypassCurtain\(href\)\) \{[\s\S]*?navigate\(href\);[\s\S]*?return;[\s\S]*?\}/);
  assert.match(curtain, /if \(shouldBypassCurtain\(to\)\) \{\s*navigate\(to as string\);\s*return;/s);
});

test('the production ingest page uses the global navigation shell', () => {
  assert.match(preview, /<KiNavigationShell/);
  assert.match(shell, /sceneVariant = 'ingest'/);
  assert.match(shell, /useCinematicBackdrop/);
  assert.match(shell, /<GooeyNav/);
  assert.match(shell, /<DualNavigationActionMenu/);
  assert.match(shell, /className="dual-nav-demo__gallery"/);
  assert.match(shell, /dual-nav-demo__brand-star-track/);
  assert.match(shell, /<TextType/);
});

test('ingest exposes one embedded-only production interface', () => {
  assert.match(preview, /<Ingest \/>/);
  assert.equal([...productionTsx.matchAll(/<Ingest\s*\/>/g)].length, 1);
  assert.doesNotMatch(productionTsx, /<Ingest\b[^>]*\b(?:embedded|actionRequest)\b/);
  assert.match(ingest, /export default function Ingest\(\)/);
  assert.doesNotMatch(ingest, /\bIngestProps\b|\bIngestActionRequest\b|\bactionRequest\b|embedded\?:|if \(!?embedded\)|\{ embedded/);
  assert.match(ingest, /legacy-ingest-root/);
  assert.match(ingest, /is-shell-embedded/);
  assert.match(ingest, /apiFetch/);
  assert.match(ingest, /handleDySubmit/);
  assert.match(ingest, /handleFileSubmit/);
  assert.doesNotMatch(ingest, /\bTrash2\b/);
});

test('the embedded workspace stays between the top navigation and global dock', () => {
  assert.match(preview, /className="ki-shell-legacy-ingest"/);
  assert.match(shellCss, /\.ki-shell-content/);
  assert.match(shellCss, /\.ki-shell-legacy-ingest/);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded/);
  assert.match(shellCss, /bottom:\s*clamp\(231px,\s*19\.1vh,\s*275px\)/);
});

test('top navigation follows the current route and performs real router navigation', () => {
  assert.match(shell, /useLocation/);
  assert.match(shell, /useNavigate/);
  assert.match(shell, /activeIndex=\{activeTopIndex\}/);
  assert.match(shell, /onNavigate=\{handleNavigate\}/);
  for (const label of ['内容采集', '即时快报', '专题系列', '头脑风暴', '产业链', '工具箱', '系统中枢']) {
    assert.match(shell, new RegExp(`label: '${label}'`));
  }
  assert.doesNotMatch(shell.match(/const TOP_ITEMS:[\s\S]*?\n\];/)?.[0] || '', /事件列表|信息源/);
  assert.doesNotMatch(shell, /label: '首页'/);
  assert.match(shell, /pathname\.startsWith\('\/briefings'\)\) return 1/);
  assert.match(shell, /pathname\.startsWith\('\/series'\)\) return 2/);
  assert.match(shell, /pathname\.startsWith\('\/brainstorm'\)\) return 3/);
  assert.match(shell, /pathname\.startsWith\('\/industry'\)[^\n]*return 4/);
  assert.match(shell, /pathname\.startsWith\('\/toolbox'\)[^\n]*return 5/);
  assert.match(shell, /pathname\.startsWith\('\/system'\)[^\n]*return 6/);
  assert.match(gooey, /activeIndex\?: number/);
  assert.match(gooey, /onNavigate\?: \(item: GooeyNavItem, index: number\) => void/);
});

test('the global dock opens the same real workspaces on every shell page', () => {
  assert.match(shell, /GLOBAL_DOCK_ITEMS/);
  assert.match(shell, /GlobalDockOverlay/);
  assert.match(dockItems, /key: 'access'/);
  assert.match(dockItems, /key: 'events'/);
  assert.match(dockItems, /key: 'sources'/);
  assert.match(dockItems, /key: 'queue'/);
  assert.match(dockOverlay, /GlobalDockAccessOverlay/);
  assert.match(dockOverlay, /GlobalDockQueueOverlay/);
  assert.match(dockAccessOverlay, /apiFetch\('\/api\/ingest\/douyin'/);
  assert.match(dockAccessOverlay, /apiFetch\('\/api\/ingest\/file'/);
  assert.match(dockQueueOverlay, /useIngestQueue/);
  assert.match(ingest, /onClick=\{\(\) => openModal\('douyin'\)\}/);
  assert.match(ingest, /onClick=\{\(\) => openModal\('file'\)\}/);
  assert.doesNotMatch(preview, /handleGlobalAction|actionRequest/);
});

test('retained douyin modal preserves the parent textarea sizing contract', () => {
  const douyinModal = ingest.match(/\{modalType === 'douyin'[\s\S]*?\n      \)\}/)?.[0] || '';
  assert.match(douyinModal, /<textarea[\s\S]*className="w-full h-32 px-3 py-2 text-sm bg-\[#0B0C10\] border border-\[#2A2B30\] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500\/50 resize-none"/);
  assert.doesNotMatch(douyinModal, /<textarea[^>]*\brows=/s);
});

test('ingest contains only the shell workspace and portal search, with no legacy standalone composition', () => {
  assert.doesNotMatch(`${ingest}\n${ingestWorkspace}`, /ModuleHeroTabs|WANXIANG_TABS|legacy-ingest-categories|legacy-ingest-list-head/);
  assert.match(ingestWorkspace, /EmbeddedIngestWorkspace/);
  assert.match(ingestWorkspace, /createPortal\(searchAccessory, searchPortalTarget\)/);
  assert.match(ingest, /legacy-ingest-root is-shell-embedded cinematic-ingest/);
});

test('embedded event rows remain in the extracted unframed list', () => {
  assert.match(ingestWorkspace, /<EmbeddedIngestList/);
  assert.match(embeddedList, /className="ki-ingest-event-list"/);
  assert.match(embeddedList, /<EmbeddedIngestRow/);
  assert.match(embeddedRow, /className="ki-ingest-list-row"/);
  assert.match(shellCss, /\.ki-ingest-list-row\s*\{[^}]*border:\s*0[^}]*background:\s*transparent/s);
});

test('formal ingest composes a split list orbit and reusable detail workspace', () => {
  assert.match(ingestWorkspace, /import \{ ContentDetailPanel \}/);
  assert.match(ingest, /useIngestDetailActions/);
  assert.match(ingestWorkspace, /EmbeddedIngestWorkspace/);
  assert.match(embeddedWorkspace, /ki-ingest-split-stage/);
  assert.match(embeddedWorkspace, /ki-ingest-list-pane/);
  assert.match(embeddedWorkspace, /ki-ingest-detail-pane/);
  assert.match(embeddedTabs, /ingest-topic-orbit ki-ingest-topic-orbit/);
  assert.match(embeddedConfig, /Globe/);
  assert.match(embeddedConfig, /Sparkles/);
  assert.match(embeddedConfig, /Brain/);
  assert.match(embeddedConfig, /Radio/);
  assert.doesNotMatch(embeddedConfig, /Zap|briefing|即时快报/);
  assert.match(ingest, /activeEventId/);
  assert.match(ingestEvents, /setActiveEventId\(eventId\)/);
  assert.match(shellCss, /\.ki-ingest-split-stage\s*\{[^}]*grid-template-columns:/s);
  assert.match(shellCss, /\.ki-ingest-detail-pane \.ingest-detail-reader\s*\{[^}]*position:\s*relative !important/s);
  assert.match(shellCss, /\.ki-ingest-topic-orbit/);
});

test('topic tabs sit above the list with icon-over-label layout and no dots', () => {
  const topicConfig = embeddedConfig.match(/export const EMBEDDED_INGEST_TOPICS = \[([\s\S]*?)\] as const;/)?.[1] || '';
  assert.deepEqual(
    [...topicConfig.matchAll(/key: '([^']+)'/g)].map((match) => match[1]),
    ['格局', '财富', '认知', '前瞻'],
  );
  assert.match(ingestTypes, /export type TopicKey = '格局' \| '财富' \| '认知' \| '前瞻';/);
  for (const productionSource of [ingest, detailActions, contentDetail, embeddedWorkspace, embeddedTabs, embeddedRow, embeddedConfig]) {
    assert.doesNotMatch(productionSource, /briefing|Briefing|即时快报|\/api\/briefing\/latest/);
  }
  assert.doesNotMatch(detailActions, /historyTab|TopicKey/);
  for (const detailCaller of [ingest, libraryPage]) {
    assert.doesNotMatch(detailCaller, /useIngestDetailActions\(\{[^}]*historyTab/s);
  }
  assert.match(detailActions, /if \(!activeEventId\) \{\s*setDetail\(null\);\s*return;\s*\}/s);
  assert.match(embeddedWorkspace, /<section className="ki-ingest-list-pane"[^>]*>[\s\S]*?<EmbeddedIngestTopicTabs[\s\S]*?\{list\}[\s\S]*?<\/section>/);
  assert.match(shellCss, /\.ki-ingest-list-pane\s*\{[^}]*--ki-list-width:\s*62%/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded\.cinematic-ingest \.ki-ingest-topic-orbit\s*\{[^}]*width:\s*var\(--ki-list-width\)[^}]*grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\)[^}]*border-bottom:/s);
  assert.doesNotMatch(shellCss, /ki-ingest-briefing/);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded\.cinematic-ingest \.ki-ingest-topic-orbit\s*\{[^}]*overflow:\s*visible\s*!important[^}]*scrollbar-width:\s*none/s);
  assert.match(shellCss, /\.ki-ingest-event-list\s*\{[^}]*width:\s*var\(--ki-list-width\)[^}]*margin:\s*0 18px 0 auto[^}]*padding:\s*0 0 18px/s);
  assert.match(shellCss, /\.ki-spotlight-row\s*\{[^}]*width:\s*100%[^}]*justify-self:\s*stretch/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded \.ki-ingest-topic-orbit button span\s*\{[^}]*writing-mode:\s*horizontal-tb/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded \.ki-ingest-topic-orbit button\s*\{[^}]*border-bottom:\s*0\s*!important/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded \.ki-ingest-topic-orbit button\.is-active:after\s*\{[^}]*bottom:\s*-11px\s*!important/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded \.ki-ingest-topic-orbit button\.is-active:after\s*\{[^}]*height:\s*3px\s*!important/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded \.ki-ingest-topic-orbit button\.is-active:after\s*\{[^}]*background:\s*rgb\(167 139 250\)\s*!important/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded \.ki-ingest-topic-orbit button\.is-active:after\s*\{[^}]*content:\s*""\s*!important/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded \.ki-ingest-topic-orbit button\.is-active:after\s*\{[^}]*transform:\s*none\s*!important/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded \.ki-ingest-topic-orbit button\.is-active:after\s*\{[^}]*top:\s*auto\s*!important/s);
  assert.match(shellCss, /\.ki-ingest-list-pane\s*\{[^}]*padding:\s*18px[^}]*\}[\s\S]*\.ki-ingest-detail-pane\s*\{[^}]*padding:\s*18px/s);
});

test('compact topic tabs remain fully legible instead of inheriting the dim legacy state', () => {
  assert.match(shellCss, /@media \(max-width:\s*1500px\), \(max-height:\s*920px\)[\s\S]*\.ki-ingest-topic-orbit button:not\(\.is-active\)\s*\{[^}]*opacity:\s*1\s*!important[^}]*brightness\(1\.08\)/s);
  assert.match(shellCss, /\.ki-ingest-topic-orbit button\.is-blue:not\(\.is-active\)\s*\{\s*color:\s*rgb\(174 211 255\)\s*!important/);
  assert.match(shellCss, /\.ki-ingest-topic-orbit button\.is-gold:not\(\.is-active\)\s*\{\s*color:\s*rgb\(255 202 74\)\s*!important/);
  assert.match(shellCss, /\.ki-ingest-topic-orbit button\.is-violet:not\(\.is-active\)\s*\{\s*color:\s*rgb\(204 190 255\)\s*!important/);
  assert.match(shellCss, /\.ki-ingest-topic-orbit button\.is-cyan:not\(\.is-active\)\s*\{\s*color:\s*rgb\(121 237 249\)\s*!important/);
  assert.doesNotMatch(shellCss, /\.ki-ingest-topic-orbit button\.is-rose/);
});

test('compact detail tabs preserve the full chinese labels', () => {
  assert.match(shellCss, /@media \(max-width:\s*1280px\)[\s\S]*\.ki-ingest-detail-pane \.ingest-tab-trigger\s*\{[^}]*grid-template-columns:\s*14px minmax\(0, 1fr\)[^}]*gap:\s*0 2px[^}]*padding:\s*7px 3px/s);
  assert.match(shellCss, /@media \(max-width:\s*1280px\)[\s\S]*\.ki-ingest-detail-pane \.ingest-tab-trigger b\s*\{[^}]*font-size:\s*12px[^}]*letter-spacing:\s*0/s);
  assert.match(shellCss, /@media \(max-width:\s*1280px\)[\s\S]*\.ki-ingest-detail-pane \.ingest-tab-trigger span\s*\{[^}]*display:\s*none !important/s);
});

test('workspace keeps balanced clearance between navigation and dock', () => {
  assert.match(shellCss, /\.ki-shell-content\s*\{[^}]*top:\s*clamp\(143px,\s*11\.2vh,\s*162px\)[^}]*bottom:\s*clamp\(231px,\s*19\.1vh,\s*275px\)/s);
  assert.match(shellCss, /@media \(max-width:\s*1180px\)[\s\S]*\.ki-shell-content\s*\{[^}]*top:\s*118px[^}]*bottom:\s*178px/s);
  assert.match(shellCss, /@media \(max-height:\s*760px\)[\s\S]*\.ki-shell-content\s*\{[^}]*top:\s*122px[^}]*bottom:\s*206px/s);
  assert.match(shellCss, /@media \(max-width:\s*1180px\) and \(max-height:\s*760px\)[\s\S]*\.ki-shell-content\s*\{[^}]*top:\s*123px[^}]*bottom:\s*183px/s);
});

test('formal ingest list uses compact spotlight rows without React pointer state', () => {
  assert.match(embeddedRow, /import SpotlightListRow/);
  assert.match(embeddedRow, /<SpotlightListRow/);
  assert.match(spotlightRow, /--spotlight-x/);
  assert.match(spotlightRow, /--spotlight-y/);
  assert.match(spotlightRow, /style\.setProperty/);
  assert.doesNotMatch(spotlightRow, /useState/);
  assert.match(shellCss, /\.ki-spotlight-row::before\s*\{[^}]*radial-gradient/s);
  assert.match(shellCss, /\.ki-ingest-list-row\s*\{[^}]*min-height:\s*84px/s);
});

test('spotlight rows use topic icons and share the topic rail alignment axis', () => {
  assert.match(embeddedConfig, /TOPIC_LIST_ICONS/);
  assert.match(embeddedRow, /<TypeIcon/);
  assert.match(embeddedRow, /ki-ingest-list-type-icon/);
  assert.match(shellCss, /\.ki-ingest-event-list\s*\{[^}]*transform:\s*none/s);
  assert.match(shellCss, /\.ki-ingest-event-list\s*\{[^}]*width:\s*var\(--ki-list-width\)[^}]*margin:\s*0 18px 0 auto/s);
  assert.match(shellCss, /\.ki-spotlight-row\s*\{[^}]*width:\s*100%[^}]*justify-self:\s*stretch/s);
  assert.match(shellCss, /@media \(max-width:\s*760px\)[\s\S]*\.ki-ingest-event-list\s*\{[^}]*width:\s*100%[^}]*margin-right:\s*0/s);
  assert.match(shellCss, /\.ki-ingest-list-row\s*\{[^}]*grid-template-columns:\s*24px minmax\(0, 1fr\)/s);
});

test('spotlight cards use a three-line topic title and source hierarchy', () => {
  assert.match(embeddedConfig, /TOPIC_LABELS/);
  assert.match(embeddedRow, /ki-ingest-list-topic/);
  assert.match(embeddedRow, /<TypeIcon/);
  assert.match(shellCss, /\.ki-ingest-list-row\s*\{[^}]*grid-template-rows:\s*auto auto auto/s);
  assert.match(shellCss, /\.ki-ingest-list-topic\s*\{[^}]*display:\s*inline-flex/s);
  assert.match(shellCss, /\.ki-ingest-list-row \.ki-ingest-list-meta\s*\{[^}]*color:\s*rgba\(255, 255, 255, \.58\)/s);
  assert.match(shellCss, /\.ki-spotlight-row\s*\{[^}]*min-height:\s*84px/s);
});

test('ingest shell promotes brand and search while keeping the stage transparent', () => {
  assert.match(shell, /className="dual-nav-demo__brand"/);
  assert.match(shell, /dual-nav-demo__brand-star-track/);
  assert.match(shell, /<span className="dual-nav-demo__brand-title">知几<\/span>/);
  assert.match(shell, /<TextType[\s\S]*className="dual-nav-demo__brand-tagline"[\s\S]*text="其神乎 见微知著"/);
  assert.match(shell, /id="ki-shell-top-accessory"/);
  assert.doesNotMatch(shell, /NAV \/ 01|PRIMARY/);
  assert.match(ingestWorkspace, /createPortal\(searchAccessory, searchPortalTarget\)/);
  assert.doesNotMatch(`${ingest}\n${ingestWorkspace}\n${ingestEvents}`, /<small>\{historyTab === 'briefing'/);
  assert.match(shellCss, /\.ki-ingest-list-search\s*\{[^}]*grid-template-columns:\s*18px minmax\(0, 1fr\)/s);
  assert.doesNotMatch(shellCss, /\.ki-ingest-list-search\s*\{[^}]*grid-template-columns:[^;}]*auto/s);
  assert.match(shellCss, /\.dual-nav-demo__brand-title\s*\{[^}]*font-family:\s*"Songti SC"[^}]*font-style:\s*italic[^}]*font-weight:\s*900/s);
  assert.doesNotMatch(shellCss, /\.dual-nav-demo__brand-title:(?:before|after)/);
  assert.match(shellCss, /\.dual-nav-demo__brand-star-track i\s*\{[^}]*animation:\s*dual-nav-brand-star-travel 4\.5s/s);
  assert.match(shellCss, /\.dual-nav-demo__brand-tagline\s*\{[^}]*color:\s*#fff[^}]*font-size:\s*12px[^}]*font-style:\s*normal/s);
  assert.match(shellCss, /\.dual-nav-demo__top-accessory\s*\{[^}]*position:\s*absolute[^}]*right:\s*0[^}]*width:\s*clamp\(170px,\s*12vw,\s*240px\)/s);
  assert.match(shellCss, /\.ki-shell-legacy-ingest\s*\{[^}]*background:\s*transparent[^}]*box-shadow:\s*none[^}]*backdrop-filter:\s*none/s);
  assert.match(shellCss, /\.ki-ingest-list-topic\s*\{[^}]*font-size:\s*11px/s);
  assert.match(shellCss, /\.ki-ingest-list-type-icon svg\s*\{[^}]*width:\s*11px[^}]*height:\s*11px/s);
});

test('vite dev authenticates remote api calls without exposing a session endpoint', () => {
  assert.doesNotMatch(vite, /__ki_remote_session|cookieDomainRewrite/);
  assert.match(vite, /KI_REMOTE_API_TOKEN/);
  assert.match(vite, /proxyReq\.setHeader\('Authorization'/);
  assert.doesNotMatch(api, /bootstrapViteRemoteSession|__ki_remote_session/);
});

test('formal ingest visual QA waits for the split workspace instead of retired cinematic modules', () => {
  assert.match(qaCore, /key: 'ingest',[\s\S]*markers: \['ki-shell-legacy-ingest', 'ki-ingest-split-stage', 'ingest-detail-reader', 'dual-nav-action-menu'\]/);
});

test('the transparent dock gallery does not block the last ingest row at compact widths', () => {
  assert.match(shellCss, /\.dual-nav-demo__gallery\s*\{[^}]*pointer-events:\s*none/s);
  assert.match(shellCss, /\.dual-nav-action-menu\.is-dock\s*\{[^}]*pointer-events:\s*auto/s);
});

test('homepage visual QA waits for the hero reveal before taking its screenshot', () => {
  assert.match(qaCore, /key: 'today',[\s\S]*screenshotSettleMs: 1800/);
  assert.match(qaCore, /const readyMs = Math\.round\(performance\.now\(\) - startedAt\);[\s\S]*if \(page\.screenshotSettleMs\) await wait\(page\.screenshotSettleMs\);[\s\S]*Page\.captureScreenshot/);
  assert.match(qaCore, /return \{[\s\S]*readyMs,[\s\S]*durationMs:/);
});

test('performance qa records browser frame long-task resource and renderer metrics', () => {
  assert.match(qaCore, /collectRuntimePerformance/);
  assert.match(qaCore, /frameDurationP95Ms/);
  assert.match(qaCore, /longTaskCount/);
  assert.match(qaCore, /resourceTransferBytes/);
  assert.match(qaCore, /rendererCalls/);
  assert.match(qaCore, /rendererFps/);
  assert.match(qaCore, /rendererQualityScale/);
  assert.match(qaCore, /rendererPixelRatio/);
  assert.match(qaCore, /rendererShaderOctaves/);
  assert.match(qaCore, /gpuRenderer/);
  assert.match(qaCore, /gpuVendor/);
  assert.match(qaCore, /Performance\.getMetrics/);
});

test('performance qa records named interaction samples for the primary cinematic pages', () => {
  assert.match(qaCore, /collectInteractionPerformance/);
  assert.match(qaCore, /buildInteractionScenarioNames/);
  assert.match(qaCore, /const names = \['idle'\]/);
  assert.match(qaCore, /names\.push\('pointer'\)/);
  assert.match(qaCore, /names\.push\('scroll', 'modal'\)/);
  assert.match(qaCore, /names\.push\('series-switch', 'series-scroll', 'series-knowledge'\)/);
  assert.match(qaCore, /interactionPerformance/);
  assert.match(qaCore, /performanceSettleMs = 5000/);
  assert.match(qaCore, /await wait\(performanceSettleMs\)/);
});

test('performance qa can run a reproducible Apple Metal profile separately from SwiftShader', () => {
  assert.match(qaCore, /gpuMode = 'swiftshader'/);
  assert.match(qaCore, /gpuMode === 'metal'/);
  assert.match(qaCore, /--use-angle=metal/);
  assert.match(qaCore, /gpuMode,/);
  assert.match(qaCore, /Emulation\.setDeviceMetricsOverride/);
  assert.match(gpuQa, /viewportArg/);
  assert.match(gpuQa, /width:\s*Number/);
  assert.match(gpuQa, /height:\s*Number/);
});

test('performance qa starts Chrome blank before the controlled cold navigation', () => {
  assert.match(qaCore, /const chrome = spawn\(chromePath,[\s\S]*'about:blank',[\s\S]*\], \{ stdio:/);
});

test('production qa builds previews and records cold route and warm cache visits', () => {
  assert.match(packageJson, /"qa:cinematic-pages:production"/);
  assert.match(vite, /preview:\s*\{[\s\S]*proxy:\s*apiProxy/);
  assert.match(productionQa, /runCinematicPagesQa/);
  assert.match(productionQa, /revisitFirstPage:\s*true/);
  assert.match(productionQa, /gpuMode:\s*'metal'/);
});

test('embedded ingest memoizes stable list detail and workspace render boundaries', () => {
  assert.match(contentDetail, /import React, \{ memo/);
  assert.match(contentDetail, /export const ContentDetailPanel = memo/);
  assert.match(embeddedWorkspace, /import \{ memo/);
  assert.match(embeddedWorkspace, /export const EmbeddedIngestWorkspace = memo/);
  assert.match(ingest, /const handleEmbeddedSummarize = useCallback/);
  assert.match(ingest, /const handleEmbeddedSearchChange = useCallback/);
  assert.match(ingestWorkspace, /const list = useMemo/);
  assert.match(ingestWorkspace, /const searchAccessory = useMemo/);
  assert.match(ingestWorkspace, /const detail = useMemo/);
  assert.match(ingestWorkspace, /<EmbeddedIngestWorkspace/);
});

test('content ingest keeps attached video visible above every detail tab', () => {
  assert.match(ingestTypes, /video_path\?: string;\s+video_url\?: string;/);
  assert.match(contentDetail, /import \{ backendUrl \} from '\.\.\/\.\.\/api';/);
  assert.match(contentDetail, /const mediaUrl = detail\?\.video_url \? backendUrl\(detail\.video_url\) : '';/);
  assert.match(contentDetail, /<\/header>\s*\{mediaUrl && \(\s*<video controls playsInline preload="metadata" className="ingest-detail-video" src=\{mediaUrl\}>[\s\S]*?<\/video>\s*\)\}\s*\{detailTabs\}/);
  assert.doesNotMatch(contentDetail, /\bvideo_path\b|createObjectURL|response\.blob\(\)/);
  assert.match(ingestOverrides, /\.cinematic-ingest \.ingest-detail-video\s*\{[^}]*width:\s*100%\s*!important;[^}]*max-height:\s*clamp\([^;]+\)\s*!important;[^}]*flex:\s*0 0 auto\s*!important;[^}]*aspect-ratio:\s*16 \/ 9;[^}]*background:\s*#000;[^}]*object-fit:\s*contain;/s);
});

test('embedded ingest expands its useful workspace at compact and large reference sizes', () => {
  assert.match(ingest, /max-w-\[1500px\]/);
  assert.match(shellCss, /\.ki-shell-legacy-ingest\s*\{[^}]*width:\s*min\(1580px,\s*calc\(100% \/ var\(--ki-workspace-scale\)\)\)/s);
  assert.match(shellCss, /\.ki-shell-content\s*\{[^}]*top:\s*clamp\(143px,\s*11\.2vh,\s*162px\)[^}]*bottom:\s*clamp\(231px,\s*19\.1vh,\s*275px\)/s);
  assert.match(shellCss, /@media \(max-width:\s*1180px\)[\s\S]*\.ki-shell-content\s*\{[^}]*top:\s*118px[^}]*bottom:\s*178px/s);
  assert.match(shellCss, /@media \(min-width:\s*1800px\)/);
});

test('embedded ingest stacks list and detail at phone width so transcript actions remain usable', () => {
  assert.match(ingest, /legacy-ingest-root is-shell-embedded cinematic-ingest is-content-ingest/);
  assert.match(shellCss, /@media \(max-width:\s*760px\)[\s\S]*\.legacy-ingest-root\.is-content-ingest\.is-shell-embedded \.ki-ingest-split-stage\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)[^}]*grid-template-rows:\s*minmax\(150px,\s*34%\) minmax\(0,\s*1fr\)[^}]*row-gap:\s*12px[^}]*column-gap:\s*0/s);
  assert.doesNotMatch(shellCss, /@media \(max-width:\s*760px\)\s*\{\s*\.ki-ingest-split-stage\s*\{/s);
});

test('the shared shell exposes a continuous middle-workspace scale', () => {
  assert.match(shell, /import \{ useCinematicWorkspaceScale \} from '\.\/useCinematicWorkspaceScale'/);
  assert.match(shell, /const workspaceScale = useCinematicWorkspaceScale\(\)/);
  assert.match(shell, /'--ki-workspace-scale': workspaceScale/);
  assert.match(shell, /style=\{shellStyle\}/);
  assert.match(shellCss, /\.ki-shell-legacy-ingest\s*\{[^}]*width:\s*min\(1580px,\s*calc\(100% \/ var\(--ki-workspace-scale\)\)\)[^}]*height:\s*calc\(100% \/ var\(--ki-workspace-scale\)\)[^}]*transform:\s*translateX\(-50%\) scale\(var\(--ki-workspace-scale\)\)[^}]*transform-origin:\s*top center/s);
});

test('embedded ingest is constrained by the scaled workspace instead of the viewport', () => {
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded\s*\{[^}]*height:\s*100%[^}]*min-height:\s*0/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded > \.flex-1\s*\{[^}]*min-height:\s*0/s);
  assert.match(shellCss, /\.ki-ingest-event-list\s*\{[^}]*flex:\s*1/s);
});

test('vite previews keep api requests same-origin so port 5188 uses the 9120 proxy', () => {
  assert.match(api, /const isViteDev = import\.meta\.env\.DEV/);
  assert.match(api, /const DEFAULT_BACKEND = sameOrigin \|\| isViteDev \? '' : 'http:\/\/127\.0\.0\.1:9120'/);
  assert.match(vite, /const remoteBackend = 'http:\/\/10\.8\.0\.105:9120'/);
  assert.match(vite, /const protectedProxy:[\s\S]*?target:\s*remoteBackend/);
  assert.match(vite, /'\/api': protectedProxy/);
  assert.match(vite, /'\/ingest': protectedProxy/);
  assert.match(vite, /'\/releases': protectedProxy/);
  assert.match(vite, /preview:\s*\{\s*proxy: apiProxy/s);
});
