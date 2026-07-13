import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/DualNavigationDemo.tsx', import.meta.url), 'utf8');
const pageCss = readFileSync(new URL('../../pages/DualNavigationDemo.css', import.meta.url), 'utf8');
const gooeyNav = readFileSync(new URL('./GooeyNav.tsx', import.meta.url), 'utf8');
const gooeyCss = readFileSync(new URL('./GooeyNav.css', import.meta.url), 'utf8');

test('dual navigation demo keeps the top and bottom menus independent', () => {
  assert.match(page, /<GooeyNav/);
  assert.match(page, /<CircularGallery/);
  assert.doesNotMatch(page, /activeIndex=.*CircularGallery/);
  assert.doesNotMatch(page, /onActiveChange=.*CircularGallery/);
});

test('dual navigation demo uses the approved reference parameters', () => {
  assert.match(page, /particleCount=\{15\}/);
  assert.match(page, /particleDistances=\{\[90, 10\]\}/);
  assert.match(page, /particleR=\{100\}/);
  assert.match(page, /animationTime=\{600\}/);
  assert.match(page, /timeVariance=\{300\}/);
  assert.match(page, /borderRadius=\{0\.1\}/);
  assert.match(page, /scrollSpeed=\{2\.7\}/);
  assert.match(page, /scrollEase=\{0\.12\}/);
  assert.match(page, /itemScale=\{0\.34\}/);
  assert.match(page, /dpr=\{1\.25\}/);
});

test('gooey nav prevents route changes and cleans up particle timers', () => {
  assert.match(gooeyNav, /event\.preventDefault\(\)/);
  assert.match(gooeyNav, /timerIdsRef/);
  assert.match(gooeyNav, /window\.clearTimeout/);
  assert.match(gooeyNav, /particle\.style\.setProperty\('--start-x'/);
  assert.match(gooeyNav, /particle\.style\.setProperty\('--time'/);
});

test('gooey nav replaces the browser focus outline with its own item focus style', () => {
  assert.match(gooeyCss, /\.gooey-nav a:focus\s*\{[^}]*outline:\s*none/);
  assert.match(gooeyCss, /focus-within:has\(:focus-visible\)/);
});

test('dual navigation demo is registered as an isolated full-screen route', () => {
  assert.match(app, /path="demo\/dual-nav"/);
  assert.match(app, /location\.pathname === '\/demo\/dual-nav'/);
});

test('top navigation leaves enough safe area for the 90px particle radius', () => {
  assert.match(pageCss, /top:\s*clamp\(96px,\s*8vh,\s*128px\)/);
  assert.match(pageCss, /top:\s*92px/);
});

test('dual navigation reuses the reduced cinematic Three.js background', () => {
  assert.match(page, /import CinematicScene from/);
  assert.match(page, /<CinematicScene focus=\{0\} variant="ingest" laserPrimary/);
  assert.match(page, /className="dual-nav-demo__film"/);
  assert.match(pageCss, /\.dual-nav-demo > \.cinematic-scene-canvas/);
  assert.match(pageCss, /\.dual-nav-demo__film/);
});

test('film layer reveals the live scene around the pointer', () => {
  assert.match(page, /style\.setProperty\('--reveal-x'/);
  assert.match(page, /style\.setProperty\('--reveal-y'/);
  assert.match(page, /'--reveal-x', '-9999px'/);
  assert.match(page, /onPointerMove=\{handlePointerMove\}/);
  assert.match(page, /onPointerLeave=\{handlePointerLeave\}/);
  assert.match(pageCss, /radial-gradient\(\s*circle at var\(--reveal-x\) var\(--reveal-y\)/);
  assert.match(pageCss, /-webkit-mask-image:/);
  assert.match(pageCss, /mask-image:/);
});

test('pointer reveal locally brightens the existing scene without another canvas', () => {
  assert.match(page, /className="dual-nav-demo__reveal"/);
  assert.match(pageCss, /\.dual-nav-demo__reveal/);
  assert.match(pageCss, /-webkit-backdrop-filter:\s*brightness\(2\.6\)/);
  assert.match(pageCss, /backdrop-filter:\s*brightness\(2\.6\)/);
  assert.doesNotMatch(page, /<canvas/);
});

test('dual navigation demo reuses the Today hero copy and typography', () => {
  assert.match(page, /className="cinematic-hero dual-nav-demo__hero"/);
  assert.match(page, /className="brand-title">知几</);
  assert.match(page, /className="line3">其神乎 见微知著</);
  assert.match(page, /真正的洞察，不在声势浩大处，而在一线微光/);
  assert.doesNotMatch(page, /Dual Navigation/);
  assert.match(pageCss, /\.dual-nav-demo__hero\s*\{[^}]*--cinematic-ui-scale:/s);
});

test('dual navigation uses a fixed ten-item non-interactive gallery', () => {
  const items = page.match(/const BOTTOM_ITEMS:[^=]+= \[([\s\S]*?)\n\];/)?.[1] || '';
  assert.equal((items.match(/image:/g) || []).length, 10);
  assert.match(page, /interactive=\{false\}/);
  assert.match(page, /STATIC \/ LOCKED/);
  assert.doesNotMatch(page, /LOOP 2\.7/);
});

test('pointer reveal coalesces updates and bounds the filtered area', () => {
  assert.match(page, /requestAnimationFrame/);
  assert.match(page, /cancelAnimationFrame/);
  assert.match(page, /revealFrameRef/);
  assert.match(pageCss, /\.dual-nav-demo__reveal\s*\{[^}]*width:\s*560px/s);
  assert.match(pageCss, /\.dual-nav-demo__reveal\s*\{[^}]*height:\s*560px/s);
  assert.match(pageCss, /transform:\s*translate3d\(/);
  assert.match(pageCss, /circle at center/);
});

test('demo previews six global modal actions in the gallery', () => {
  for (const label of ['抖音分享', '文件上传', '概念沉淀', '信息源扫描', '全局发现', '主题发现']) {
    assert.match(page, new RegExp(`text: '${label}'`));
  }
  assert.match(page, /onItemSelect=\{setActiveAction\}/);
  assert.match(page, /dual-nav-action-dialog/);
  assert.match(page, /role="dialog"/);
});
