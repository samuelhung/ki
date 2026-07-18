import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/DualNavigationDemo.tsx', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../../pages/KiNavigationShell.tsx', import.meta.url), 'utf8');
const pageCss = readFileSync(new URL('../../pages/DualNavigationDemo.css', import.meta.url), 'utf8');
const homeCss = readFileSync(new URL('../../pages/CinematicHome.css', import.meta.url), 'utf8');
const variants = readFileSync(new URL('../../pages/DualNavigationActionMenu.tsx', import.meta.url), 'utf8');
const gooeyNav = readFileSync(new URL('./GooeyNav.tsx', import.meta.url), 'utf8');
const gooeyCss = readFileSync(new URL('./GooeyNav.css', import.meta.url), 'utf8');

test('dual navigation demo keeps the top and bottom menus independent', () => {
  assert.match(page, /<KiNavigationShell/);
  assert.match(shell, /<GooeyNav/);
  assert.match(shell, /<DualNavigationActionMenu/);
  assert.doesNotMatch(shell, /activeIndex=.*DualNavigationActionMenu/);
  assert.doesNotMatch(shell, /onActiveChange=.*DualNavigationActionMenu/);
});

test('dual navigation demo keeps the approved gooey navigation parameters', () => {
  assert.match(shell, /particleCount=\{15\}/);
  assert.match(shell, /const GOOEY_PARTICLE_DISTANCES: \[number, number\] = \[90, 10\]/);
  assert.match(shell, /particleDistances=\{GOOEY_PARTICLE_DISTANCES\}/);
  assert.match(shell, /particleR=\{100\}/);
  assert.match(shell, /animationTime=\{600\}/);
  assert.match(shell, /timeVariance=\{300\}/);
});

test('the primary navigation exposes the formal chinese information architecture', () => {
  const items = shell.match(/const TOP_ITEMS:[^=]+= \[([\s\S]*?)\n\];/)?.[1] || '';
  assert.equal((items.match(/label:/g) || []).length, 7);
  assert.doesNotMatch(items, /label: '首页'/);
  assert.match(items, /label: '内容采集', href: '\/ingest'/);
  assert.match(items, /label: '事件列表', href: '\/events'/);
  assert.match(items, /label: '信息源', href: '\/sources'/);
  assert.doesNotMatch(items, /label: 'INGEST'/);
});

test('the enlarged cinematic brand replaces home and navigates to the dashboard', () => {
  assert.match(shell, /className="dual-nav-demo__brand"[^>]*onClick=\{\(\) => navigate\('\/'\)\}/);
  assert.match(shell, /<span className="dual-nav-demo__brand-title">知几<\/span>/);
  assert.match(shell, /import TextType from/);
  assert.match(shell, /dual-nav-demo__brand-star-track[^>]*><i \/><\/span>/);
  assert.match(shell, /<TextType[\s\S]*className="dual-nav-demo__brand-tagline"[\s\S]*text="其神乎 见微知著"[\s\S]*showCursor=\{false\}/);
  assert.match(pageCss, /\.dual-nav-demo__brand-title\s*\{[^}]*font-size:\s*60px/s);
  assert.match(pageCss, /\.dual-nav-demo__brand-tagline\s*\{[^}]*color:\s*#fff[^}]*font-size:\s*12px[^}]*font-style:\s*normal/s);
  assert.doesNotMatch(pageCss, /\.dual-nav-demo__brand-title:(?:before|after)/);
  assert.match(pageCss, /\.dual-nav-demo__brand-star-track i\s*\{[^}]*animation:\s*dual-nav-brand-star-travel 4\.5s/s);
  assert.match(pageCss, /@keyframes dual-nav-brand-star-travel/);
  assert.match(pageCss, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.dual-nav-demo__brand-star-track i\s*\{[^}]*animation:\s*none/s);
  assert.match(pageCss, /\.dual-nav-demo__primary\s*\{[^}]*display:\s*flex[^}]*gap:\s*clamp\(20px,\s*2vw,\s*36px\)/s);
});

test('top brand and search align to the ingest workspace edges', () => {
  assert.match(pageCss, /\.dual-nav-demo__top\s*\{[^}]*width:\s*min\(1536px,[^}]*transform:\s*translateX\(calc\(-50% \+ var\(--ki-center-shift\)\)\)/s);
  assert.match(pageCss, /\.dual-nav-demo__primary\s*\{[^}]*position:\s*absolute[^}]*left:\s*calc\(14\.44% - 18px\)/s);
  assert.match(pageCss, /\.dual-nav-demo__top-accessory\s*\{[^}]*position:\s*absolute[^}]*right:\s*0/s);
});

test('top workspace and dock share the viewport center axis', () => {
  assert.match(pageCss, /\.dual-nav-demo\s*\{[^}]*--ki-center-shift:\s*clamp\(-102px,\s*calc\(-5vw - 7px\),\s*-79px\)/s);
  assert.match(pageCss, /\.dual-nav-demo__top\s*\{[^}]*transform:\s*translateX\(calc\(-50% \+ var\(--ki-center-shift\)\)\)/s);
  assert.match(pageCss, /\.ki-shell-content\s*\{[^}]*transform:\s*translateX\(var\(--ki-center-shift\)\)/s);
  assert.match(pageCss, /\.dual-nav-action-menu\.is-dock\s*\{[^}]*inset:\s*auto 50%[^}]*transform:\s*translateX\(-50%\)/s);
});

test('gooey nav prevents route changes and cleans up particle timers', () => {
  assert.match(gooeyNav, /event\.preventDefault\(\)/);
  assert.match(gooeyNav, /timerIdsRef/);
  assert.match(gooeyNav, /window\.clearTimeout/);
  assert.match(gooeyNav, /particle\.style\.setProperty\('--start-x'/);
  assert.match(gooeyNav, /particle\.style\.setProperty\('--time'/);
  assert.match(gooeyNav, /useEffect\(\(\) => \{[\s\S]*if \(filterRef\.current\) makeParticlesRef\.current\(filterRef\.current\)/);
});

test('top navigation lets the gooey particles start before route navigation unmounts them', () => {
  assert.match(gooeyNav, /navigationDelay\?: number/);
  assert.match(gooeyNav, /setPendingActiveIndex\(index\)/);
  assert.match(gooeyNav, /window\.setTimeout\(\(\) => onNavigate\?\.\(items\[index\], index\), navigationDelay\)/);
  assert.match(shell, /navigationDelay=\{480\}/);
});

test('gooey nav replaces the browser focus outline with its own item focus style', () => {
  assert.match(gooeyCss, /\.gooey-nav a:focus\s*\{[^}]*outline:\s*none/);
  assert.match(gooeyCss, /focus-within:has\(:focus-visible\)/);
});

test('dual navigation demo is registered as an isolated full-screen route', () => {
  assert.match(app, /path="demo\/dual-nav"/);
  assert.match(app, /location\.pathname === '\/demo\/dual-nav'/);
});

test('three brand lockups are available in an isolated comparison demo', () => {
  const demoUrl = new URL('../../pages/BrandLockupDemo.tsx', import.meta.url);
  const demoCssUrl = new URL('../../pages/BrandLockupDemo.css', import.meta.url);
  assert.equal(existsSync(demoUrl), true);
  assert.equal(existsSync(demoCssUrl), true);
  const brandDemo = readFileSync(demoUrl, 'utf8');
  const brandDemoCss = readFileSync(demoCssUrl, 'utf8');
  assert.match(app, /const BrandLockupDemo = lazy/);
  assert.match(app, /path="demo\/brand-lockups" element=\{<BrandLockupDemo \/>\}/);
  assert.match(app, /location\.pathname === '\/demo\/brand-lockups'/);
  assert.match(brandDemo, /variant="signature"/);
  assert.match(brandDemo, /variant="offset"/);
  assert.match(brandDemo, /variant="quiet"/);
  assert.match(brandDemo, /<GooeyNav/);
  assert.match(brandDemo, /const DEMO_HREF = '\/demo\/brand-lockups'/);
  assert.doesNotMatch(brandDemo, /label: '事件列表', href: '\/events'/);
  assert.match(brandDemo, /placeholder="搜索内容标题"/);
  assert.match(brandDemoCss, /\.brand-lockup-demo__row/);
  assert.match(brandDemoCss, /\.brand-lockup-demo__brand--signature/);
  assert.match(brandDemoCss, /\.brand-lockup-demo__brand--offset/);
  assert.match(brandDemoCss, /\.brand-lockup-demo__brand--quiet/);
});

test('the spatial brand demo keeps only the approved dark-gold and white TextType aperture lockup', () => {
  const demoUrl = new URL('../../pages/BrandDepthDemo.tsx', import.meta.url);
  const demoCssUrl = new URL('../../pages/BrandDepthDemo.css', import.meta.url);
  const textTypeUrl = new URL('./TextType.jsx', import.meta.url);
  assert.equal(existsSync(demoUrl), true);
  assert.equal(existsSync(demoCssUrl), true);
  assert.equal(existsSync(textTypeUrl), true);
  const depthDemo = readFileSync(demoUrl, 'utf8');
  const depthDemoCss = readFileSync(demoCssUrl, 'utf8');
  assert.match(app, /const BrandDepthDemo = lazy/);
  assert.match(app, /path="demo\/brand-depth" element=\{<BrandDepthDemo \/>\}/);
  assert.match(app, /location\.pathname === '\/demo\/brand-depth'/);
  assert.match(depthDemo, /brand-depth-demo__brand--aperture/);
  assert.match(depthDemo, /import TextType from/);
  assert.doesNotMatch(depthDemo, /GradientText/);
  assert.match(depthDemo, /<TextType[\s\S]*text="其神乎 见微知著"[\s\S]*typingSpeed=\{75\}[\s\S]*pauseDuration=\{1500\}[\s\S]*deletingSpeed=\{50\}[\s\S]*showCursor=\{false\}[\s\S]*cursorCharacter="\|"/);
  assert.doesNotMatch(depthDemo, /variant="planes"/);
  assert.doesNotMatch(depthDemo, /variant="rail"/);
  assert.match(depthDemo, /<GooeyNav/);
  assert.match(depthDemoCss, /\.brand-depth-demo__brand--aperture/);
  assert.doesNotMatch(depthDemoCss, /\.brand-depth-demo__brand--planes/);
  assert.doesNotMatch(depthDemoCss, /\.brand-depth-demo__brand--rail/);
  assert.match(depthDemoCss, /perspective:/);
  assert.match(depthDemoCss, /translateZ\(/);
  const apertureTitleRule = depthDemoCss.match(/\.brand-depth-demo__brand--aperture \.brand-depth-demo__title\s*\{[^}]*\}/s)?.[0] || '';
  assert.match(apertureTitleRule, /color:\s*#f0c976/);
  assert.match(apertureTitleRule, /opacity:\s*1/);
  assert.match(apertureTitleRule, /mix-blend-mode:\s*normal/);
  assert.match(apertureTitleRule, /transform:\s*none/);
  assert.doesNotMatch(apertureTitleRule, /rgba\(0, 0, 0, \.94\)/);
  assert.match(depthDemoCss, /\.brand-depth-demo__brand--aperture:hover \.brand-depth-demo__title\s*\{[^}]*transform:\s*none/s);
  assert.match(depthDemoCss, /\.brand-depth-demo__brand--aperture \.brand-depth-demo__motto\s*\{[^}]*z-index:\s*4[^}]*top:\s*70px[^}]*left:\s*66px[^}]*opacity:\s*1[^}]*translateZ\(40px\)/s);
  assert.doesNotMatch(depthDemoCss, /\.brand-depth-demo__brand--aperture \.brand-depth-demo__motto::before/);
  assert.match(depthDemoCss, /\.brand-depth-demo__brand--aperture \.brand-depth-demo__motto\s*\{[^}]*color:\s*#fff[^}]*-webkit-text-fill-color:\s*#fff/s);
  assert.match(depthDemo, /brand-depth-demo__aperture-track[^>]*><i \/><\/span>/);
  assert.doesNotMatch(depthDemo, /brand-depth-demo__aperture-lines/);
  assert.doesNotMatch(depthDemoCss, /\.brand-depth-demo__title::after/);
  assert.match(depthDemoCss, /\.brand-depth-demo__aperture-track\s*\{[^}]*linear-gradient\([^}]*rgba\(240, 201, 118, \.54\)/s);
  assert.match(depthDemoCss, /\.brand-depth-demo__aperture-track i\s*\{[^}]*animation:\s*brand-depth-star-travel 4\.5s/s);
  assert.match(depthDemoCss, /@keyframes brand-depth-star-travel/);
  assert.match(depthDemoCss, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.brand-depth-demo__aperture-track i\s*\{[^}]*animation:\s*none/s);
});

test('top navigation uses the reduced viewport inset', () => {
  assert.match(pageCss, /top:\s*clamp\(48px,\s*4vh,\s*64px\)/);
  assert.match(pageCss, /top:\s*46px/);
});

test('dual navigation reuses the reduced cinematic Three.js background', () => {
  assert.match(app, /CinematicBackdropProvider/);
  assert.match(shell, /useCinematicBackdrop/);
  assert.match(shell, /sceneVariant = 'ingest'/);
  assert.match(shell, /laserPrimary = true/);
  assert.match(shell, /setBackdrop\(\{[\s\S]*variant: sceneVariant,[\s\S]*laserPrimary,[\s\S]*focus: 0/);
  assert.doesNotMatch(shell, /<CinematicScene/);
  assert.match(shell, /sceneVariant === 'today' \? 'cinematic-film' : 'dual-nav-demo__film'/);
  assert.match(pageCss, /\.cinematic-backdrop-host > \.cinematic-scene-canvas/);
  assert.match(pageCss, /\.cinematic-backdrop-host\s*\{[^}]*z-index:\s*1/s);
  assert.match(pageCss, /\.dual-nav-demo__film\s*\{[^}]*z-index:\s*2/s);
  assert.match(shell, /is-\$\{sceneVariant\}-backdrop-active/);
  assert.match(pageCss, /\.cinematic-backdrop-host\.is-ingest-backdrop-active > \.cinematic-scene-canvas\s*\{[^}]*opacity:\s*1[^}]*brightness\(1\.16\)/s);
  assert.match(pageCss, /\.ki-shell-ingest-preview \.dual-nav-demo__reveal\s*\{[^}]*radial-gradient[^}]*backdrop-filter:\s*none/s);
  assert.match(pageCss, /\.ki-shell-ingest-preview \.dual-nav-demo__film\s*\{[^}]*mask-image:\s*none/s);
  assert.match(pageCss, /\.dual-nav-demo__film/);
});

test('film layer reveals the live scene around the pointer', () => {
  assert.match(shell, /style\.setProperty\('--reveal-x'/);
  assert.match(shell, /style\.setProperty\('--reveal-y'/);
  assert.match(shell, /'--reveal-x', '-9999px'/);
  assert.match(shell, /addEventListener\('pointermove', handlePointerMove, \{ passive: true \}\)/);
  assert.match(shell, /addEventListener\('pointerleave', handlePointerLeave\)/);
  assert.match(shell, /removeEventListener\('pointermove', handlePointerMove\)/);
  assert.doesNotMatch(shell, /onPointerMove=/);
  assert.match(pageCss, /radial-gradient\(\s*circle at var\(--reveal-x\) var\(--reveal-y\)/);
  assert.match(pageCss, /-webkit-mask-image:/);
  assert.match(pageCss, /mask-image:/);
});

test('pointer reveal locally brightens the existing scene without another canvas', () => {
  assert.match(shell, /className="dual-nav-demo__reveal"/);
  assert.match(pageCss, /\.dual-nav-demo__reveal/);
  assert.match(pageCss, /-webkit-backdrop-filter:\s*brightness\(2\.6\)/);
  assert.match(pageCss, /backdrop-filter:\s*brightness\(2\.6\)/);
  assert.doesNotMatch(shell, /<canvas/);
});

test('gooey navigation portals the original filter outside transformed navigation ancestors', () => {
  const filter = gooeyCss.match(/\.gooey-nav__filter\s*\{([^}]*)\}/s)?.[1] || '';
  assert.match(gooeyNav, /import \{ createPortal \} from 'react-dom'/);
  assert.match(gooeyNav, /closest\('main'\)/);
  assert.match(gooeyNav, /const hostRect = effectHost\.getBoundingClientRect\(\)/);
  assert.match(gooeyNav, /left: `\$\{itemRect\.left - hostRect\.left\}px`/);
  assert.match(gooeyNav, /createPortal\([\s\S]*effectHost/);
  assert.match(filter, /filter:\s*blur\(7px\) contrast\(100\) blur\(0\)/);
  assert.match(filter, /mix-blend-mode:\s*lighten/);
  assert.match(gooeyCss, /\.gooey-nav__filter::before\s*\{[^}]*inset:\s*-75px[^}]*background:\s*#000/s);
  assert.match(gooeyCss, /--gooey-color-1:[^;]+;[\s\S]*--gooey-color-4:/);
  assert.doesNotMatch(gooeyNav, /<feGaussianBlur|<feColorMatrix|<feBlend/);
});

test('gooey particles keep the original pill and particle timing', () => {
  assert.match(gooeyCss, /animation:\s*gooey-nav-pill \.3s ease both/);
  assert.match(gooeyCss, /@keyframes gooey-nav-pill\s*\{[\s\S]*to\s*\{\s*opacity:\s*1;/);
});

test('home backdrop uses opacity reveal instead of a full-canvas css filter', () => {
  const activeCanvas = pageCss.match(/\.cinematic-backdrop-host\.is-home-active > \.cinematic-scene-canvas\s*\{([^}]*)\}/s)?.[1] || '';
  const lightKeyframes = homeCss.match(/@keyframes cinematic-home-backdrop-light\s*\{([\s\S]*?)\n\}/)?.[1] || '';
  assert.match(activeCanvas, /filter:\s*none/);
  assert.match(activeCanvas, /animation:\s*cinematic-home-backdrop-light 1s/);
  assert.match(lightKeyframes, /opacity:/);
  assert.doesNotMatch(lightKeyframes, /filter:/);
});

test('ingest pointer reveal uses a lightweight radial glow instead of backdrop filtering', () => {
  const ingestReveal = pageCss.match(/\.ki-shell-ingest-preview \.dual-nav-demo__reveal\s*\{([^}]*)\}/s)?.[1] || '';
  assert.match(ingestReveal, /radial-gradient/);
  assert.match(ingestReveal, /backdrop-filter:\s*none/);
  assert.match(ingestReveal, /mask-image:\s*none/);
  assert.doesNotMatch(ingestReveal, /mix-blend-mode/);
  assert.match(pageCss, /\.dual-nav-demo__reveal\s*\{[^}]*translate3d/s);
});

test('dual navigation demo reuses the Today hero copy and typography', () => {
  assert.match(page, /className="cinematic-hero dual-nav-demo__hero"/);
  assert.match(page, /className="brand-title">知几</);
  assert.match(page, /className="line3">其神乎 见微知著</);
  assert.match(page, /真正的洞察，不在声势浩大处，而在一线微光/);
  assert.doesNotMatch(page, /Dual Navigation/);
  assert.match(pageCss, /\.dual-nav-demo__hero\s*\{[^}]*--cinematic-ui-scale:/s);
});

test('dual navigation uses one fixed ten-item semantic dock', () => {
  const items = shell.match(/const GLOBAL_ACTIONS:[^=]+= \[([\s\S]*?)\n\];/)?.[1] || '';
  assert.equal((items.match(/text:/g) || []).length, 10);
  assert.match(items, /key: 'queue'/);
  assert.doesNotMatch(items, /key: 'study'/);
  assert.match(shell, /DOCK \/ LOCKED/);
  assert.doesNotMatch(shell, /LOOP 2\.7/);
});

test('pointer reveal coalesces updates and bounds the filtered area', () => {
  assert.match(shell, /requestAnimationFrame/);
  assert.match(shell, /cancelAnimationFrame/);
  assert.match(shell, /revealFrameRef/);
  assert.match(pageCss, /\.dual-nav-demo__reveal\s*\{[^}]*width:\s*560px/s);
  assert.match(pageCss, /\.dual-nav-demo__reveal\s*\{[^}]*height:\s*560px/s);
  assert.match(pageCss, /transform:\s*translate3d\(/);
  assert.match(pageCss, /circle at center/);
  assert.match(shell, /matchMedia\('\(pointer: fine\)'\)/);
  assert.match(shell, /matchMedia\('\(prefers-reduced-motion: reduce\)'\)/);
});

test('demo previews six global modal actions in the gallery', () => {
  for (const label of ['抖音分享', '文件上传', '概念沉淀', '信息源扫描', '全局发现', '主题发现']) {
    assert.match(shell, new RegExp(`text: '${label}'`));
  }
  assert.match(shell, /onSelect=\{handleActionSelect\}/);
  assert.match(shell, /dual-nav-action-dialog/);
  assert.match(shell, /role="dialog"/);
});

test('demo keeps only the selected curved semantic dock', () => {
  assert.match(shell, /<DualNavigationActionMenu/);
  assert.doesNotMatch(shell, /ACTION_MENU_VARIANTS|actionMenuVariant|setActionMenuVariant/);
  assert.doesNotMatch(variants, /ActionMenuVariant|variant ===|--spotlight/);
  assert.doesNotMatch(pageCss, /is-spotlight|is-reel|dual-nav-variant-switcher/);
});

test('dock keeps semantic labels icons colors and modal actions in one data source', () => {
  assert.match(variants, /item\.icon/);
  assert.match(variants, /item\.text/);
  assert.match(variants, /onSelect\(item\)/);
  assert.match(variants, /--action-accent/);
  assert.match(variants, /aria-label=\{item\.text\}/);
  assert.match(shell, /code: 'DOUYIN SHARE'/);
  assert.match(shell, /activeAction\.description/);
  assert.doesNotMatch(shell, /ACTION_META/);
});

test('semantic dock is memoized while the page keeps a stable selection callback', () => {
  assert.match(variants, /export default memo\(DualNavigationActionMenu\)/);
  assert.match(shell, /const handleActionSelect = useCallback/);
  assert.match(pageCss, /\.dual-nav-action-menu\.is-dock/);
  assert.match(pageCss, /prefers-reduced-motion/);
});

test('semantic dock follows a shallow circular gallery arc without losing hover focus', () => {
  assert.match(pageCss, /\.dual-nav-action-menu\.is-dock \.dual-nav-action-item\s*\{[^}]*translateY\(calc\(var\(--action-distance\) \* 4px\)\)[^}]*rotateZ\(calc\(var\(--action-offset\) \* \.8deg\)\)[^}]*scale\(calc\(1 - var\(--action-distance\) \* \.018\)\)/s);
  assert.match(pageCss, /\.dual-nav-action-menu\.is-dock \.dual-nav-action-item:hover\s*\{[^}]*translateY\(calc\(var\(--action-distance\) \* 4px - 10px\)\)[^}]*scale\(1\.16\)/s);
  assert.match(pageCss, /\.dual-nav-action-menu\.is-dock::before\s*\{[^}]*display:\s*none/s);
  assert.doesNotMatch(pageCss, /\.is-dock[^}]*rotateZ\(calc\(var\(--action-offset\) \* -/s);
});

test('the stage uses a fading planetary horizon instead of crosshair lines', () => {
  assert.doesNotMatch(pageCss, /\.dual-nav-demo::before/);
  assert.doesNotMatch(pageCss, /\.dual-nav-demo__gallery\s*\{[^}]*border-top:/s);
  assert.match(pageCss, /\.dual-nav-demo__gallery::before\s*\{[^}]*width:\s*min\(1040px,\s*calc\(100vw - 80px\)\)[^}]*height:\s*60px[^}]*border-top:[^}]*border-radius:\s*50%/s);
  assert.match(pageCss, /\.dual-nav-demo__gallery::before\s*\{[^}]*mask-image:\s*linear-gradient\(90deg,\s*transparent/s);
  assert.doesNotMatch(pageCss, /\.dual-nav-demo__gallery::before\s*\{[^}]*width:\s*72px/s);
});

test('the planetary horizon stays below the dock at compact and wide sizes', () => {
  assert.match(pageCss, /\.dual-nav-demo__gallery::before\s*\{[^}]*top:\s*clamp\(150px,\s*18vh,\s*280px\)/s);
  assert.match(pageCss, /@media \(min-width:\s*1800px\)[\s\S]*\.dual-nav-demo__gallery::before\s*\{[^}]*top:\s*clamp\(240px,\s*18vh,\s*280px\)/s);
  assert.doesNotMatch(pageCss, /\.dual-nav-demo__gallery::before\s*\{[^}]*clip-path:/s);
});
