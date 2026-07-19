import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const curtain = readFileSync(new URL('../../CurtainContext.tsx', import.meta.url), 'utf8');
const homeUrl = new URL('../../pages/CinematicHome.tsx', import.meta.url);
const home = existsSync(homeUrl) ? readFileSync(homeUrl, 'utf8') : '';
const homeCss = readFileSync(new URL('../../pages/CinematicHome.css', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../../pages/KiNavigationShell.tsx', import.meta.url), 'utf8');
const dockItems = readFileSync(new URL('../../pages/globalDockItems.ts', import.meta.url), 'utf8');
const dockOverlay = readFileSync(new URL('../../pages/GlobalDockOverlay.tsx', import.meta.url), 'utf8');
const dockAccessOverlay = readFileSync(new URL('../../pages/GlobalDockAccessOverlay.tsx', import.meta.url), 'utf8');
const demo = readFileSync(new URL('../../pages/DualNavigationDemo.tsx', import.meta.url), 'utf8');
const preview = readFileSync(new URL('../../pages/LegacyIngestShellPreview.tsx', import.meta.url), 'utf8');
const ingest = readFileSync(new URL('../../pages/Ingest.tsx', import.meta.url), 'utf8');
const gooey = readFileSync(new URL('./GooeyNav.tsx', import.meta.url), 'utf8');
const hero = readFileSync(new URL('../ModuleHeroTabs.tsx', import.meta.url), 'utf8');
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
const embeddedTabs = readFileSync(new URL('../ingest/EmbeddedIngestTopicTabs.tsx', import.meta.url), 'utf8');
const embeddedRow = readFileSync(new URL('../ingest/EmbeddedIngestRow.tsx', import.meta.url), 'utf8');
const embeddedConfig = readFileSync(new URL('../ingest/embeddedIngestConfig.ts', import.meta.url), 'utf8');
const ingestTypes = readFileSync(new URL('../cinematic-ingest/ingestTypes.ts', import.meta.url), 'utf8');

test('home keeps only the Today backdrop and center copy while the previous dashboard remains explicit', () => {
  assert.match(app, /const CinematicHome = lazy/);
  assert.match(app, /<Route index element=\{<CinematicHome \/>\}/);
  assert.match(app, /path="today-old" element=\{<Dashboard \/>\}/);
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
  assert.match(app, /path="ingest-previous" element=\{<CinematicIngest \/>\}/);
  assert.match(app, /path="ingest-old" element=\{<Ingest \/>\}/);
  assert.match(app, /path="demo\/ki-ingest" element=\{<Navigate to="\/ingest" replace \/>\}/);
});

test('the demo and preview share one global navigation shell', () => {
  assert.match(demo, /<KiNavigationShell/);
  assert.match(preview, /<KiNavigationShell/);
  assert.match(shell, /sceneVariant = 'ingest'/);
  assert.match(shell, /useCinematicBackdrop/);
  assert.match(shell, /<GooeyNav/);
  assert.match(shell, /<DualNavigationActionMenu/);
  assert.match(shell, /className="dual-nav-demo__gallery"/);
  assert.match(shell, /dual-nav-demo__brand-star-track/);
  assert.match(shell, /<TextType/);
});

test('legacy ingest preserves its implementation and only adds an embedded mode', () => {
  assert.match(preview, /<Ingest embedded \/>/);
  assert.match(ingest, /interface IngestProps/);
  assert.match(ingest, /embedded\?: boolean/);
  assert.match(ingest, /export default function Ingest\(\{ embedded = false, actionRequest = null \}: IngestProps\)/);
  assert.match(ingest, /legacy-ingest-root/);
  assert.match(ingest, /is-shell-embedded/);
  assert.match(ingest, /apiFetch/);
  assert.match(ingest, /handleDySubmit/);
  assert.match(ingest, /handleFileSubmit/);
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
  assert.match(dockAccessOverlay, /apiFetch\('\/api\/ingest\/douyin'/);
  assert.match(dockAccessOverlay, /apiFetch\('\/api\/ingest\/file'/);
  assert.doesNotMatch(preview, /handleGlobalAction|actionRequest/);
});

test('embedded ingest removes the legacy hero and moves search beside category tabs', () => {
  assert.match(hero, /compact\?: boolean/);
  assert.match(hero, /module-hero-tabs/);
  assert.match(hero, /is-compact/);
  assert.match(ingest, /\{!embedded && \(/);
  assert.match(ingest, /chips=\{embedded \? \[\] : \[/);
  assert.match(ingest, /actions=\{embedded \? \[\] : \[/);
  assert.match(ingest, /label: '处理队列'/);
  assert.match(ingest, /legacy-ingest-toolbar-search/);
  assert.match(shellCss, /\.module-hero-tabs\.is-compact/);
  assert.match(shellCss, /\.legacy-ingest-category-sub/);
});

test('embedded event rows are unframed while preserving subtle row separation', () => {
  assert.match(ingest, /legacy-ingest-list/);
  assert.match(ingest, /legacy-ingest-list-head/);
  assert.match(ingest, /legacy-ingest-list-row/);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded \.legacy-ingest-list\s*\{[^}]*border:\s*0[^}]*border-radius:\s*0[^}]*background:\s*transparent/s);
});

test('formal ingest composes a split list orbit and reusable detail workspace', () => {
  assert.match(ingest, /import \{ ContentDetailPanel \}/);
  assert.match(ingest, /useIngestDetailActions/);
  assert.match(ingest, /EmbeddedIngestWorkspace/);
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
  assert.match(ingest, /setActiveEventId\(eventId\)/);
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
  assert.match(detailActions, /if \(!activeEventId\) \{\s*setDetail\(null\);\s*return;\s*\}/s);
  assert.match(embeddedWorkspace, /<section className="ki-ingest-list-pane"[^>]*>[\s\S]*?<EmbeddedIngestTopicTabs[\s\S]*?\{list\}[\s\S]*?<\/section>/);
  assert.match(shellCss, /\.ki-ingest-list-pane\s*\{[^}]*--ki-list-width:\s*62%/s);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded\.cinematic-ingest \.ki-ingest-topic-orbit\s*\{[^}]*width:\s*var\(--ki-list-width\)[^}]*grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\)[^}]*border-bottom:/s);
  assert.doesNotMatch(shellCss, /ki-ingest-briefing/);
  assert.match(shellCss, /\.legacy-ingest-root\.is-shell-embedded\.cinematic-ingest \.ki-ingest-topic-orbit\s*\{[^}]*overflow:\s*visible\s*!important[^}]*scrollbar-width:\s*none/s);
  assert.match(shellCss, /\.ki-spotlight-row\s*\{[^}]*width:\s*var\(--ki-list-width\)/s);
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

test('spotlight rows use topic icons stay level and match the topic tab width', () => {
  assert.match(embeddedConfig, /TOPIC_LIST_ICONS/);
  assert.match(embeddedRow, /<TypeIcon/);
  assert.match(embeddedRow, /ki-ingest-list-type-icon/);
  assert.match(shellCss, /\.ki-ingest-event-list\s*\{[^}]*transform:\s*none/s);
  assert.match(shellCss, /\.ki-spotlight-row\s*\{[^}]*width:\s*var\(--ki-list-width\)[^}]*justify-self:\s*end/s);
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
  assert.match(ingest, /createPortal\(embeddedSearch, searchPortalTarget\)/);
  assert.doesNotMatch(ingest, /<small>\{historyTab === 'briefing'/);
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

test('vite dev automatically bootstraps a remote session before retrying protected api calls', () => {
  assert.match(vite, /'\/__ki_remote_session'/);
  assert.match(vite, /cookieDomainRewrite/);
  assert.match(vite, /rewrite:\s*\(\)\s*=>\s*'\/'/);
  assert.match(api, /bootstrapViteRemoteSession/);
  assert.match(api, /response\.status !== 401/);
  assert.match(api, /fetch\('\/__ki_remote_session'/);
});

test('formal ingest visual QA waits for the split workspace instead of retired cinematic modules', () => {
  assert.match(qaCore, /key: 'ingest',[\s\S]*markers: \['ki-shell-legacy-ingest', 'ki-ingest-split-stage', 'ingest-detail-reader', 'dual-nav-action-menu'\]/);
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
  assert.match(ingest, /const embeddedList = useMemo/);
  assert.match(ingest, /const embeddedSearch = useMemo/);
  assert.match(ingest, /const embeddedDetail = useMemo/);
  assert.match(ingest, /const embeddedStage = useMemo/);
});

test('embedded ingest expands its useful workspace at compact and large reference sizes', () => {
  assert.match(ingest, /max-w-\[1500px\]/);
  assert.match(shellCss, /\.ki-shell-legacy-ingest\s*\{[^}]*width:\s*min\(1580px,\s*calc\(100% \/ var\(--ki-workspace-scale\)\)\)/s);
  assert.match(shellCss, /\.ki-shell-content\s*\{[^}]*top:\s*clamp\(143px,\s*11\.2vh,\s*162px\)[^}]*bottom:\s*clamp\(231px,\s*19\.1vh,\s*275px\)/s);
  assert.match(shellCss, /@media \(max-width:\s*1180px\)[\s\S]*\.ki-shell-content\s*\{[^}]*top:\s*118px[^}]*bottom:\s*178px/s);
  assert.match(shellCss, /@media \(min-width:\s*1800px\)/);
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
  assert.match(vite, /'\/api':\s*\{[^}]*target:\s*remoteBackend/s);
});
