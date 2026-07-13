import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/CircularGalleryDemo.tsx', import.meta.url), 'utf8');
const gallery = readFileSync(new URL('./CircularGallery.tsx', import.meta.url), 'utf8');

test('demo uses the reusable OGL circular gallery with requested parameters', () => {
  assert.match(page, /CircularGallery/);
  assert.match(page, /borderRadius=\{0\.1\}/);
  assert.match(page, /scrollSpeed=\{2\.7\}/);
  assert.match(page, /scrollEase=\{0\.12\}/);
});

test('demo is registered as a full-screen route', () => {
  assert.match(app, /path="demo\/circular-gallery"/);
  assert.match(app, /location\.pathname === '\/demo\/circular-gallery'/);
});

test('labels use scene coordinates so card scaling does not hide them', () => {
  assert.match(gallery, /this\.label\.setParent\(scene\)/);
  assert.match(gallery, /this\.label\.position\.x = this\.plane\.position\.x/);
});

test('gallery item scaling changes cards and spacing proportionally', () => {
  assert.match(gallery, /itemScale = 1/);
  assert.match(gallery, /this\.plane\.scale\.y = .* \* this\.itemScale/);
  assert.match(gallery, /this\.plane\.scale\.x = .* \* this\.itemScale/);
  assert.match(gallery, /2 \* this\.itemScale/);
});

test('gallery starts from the second loop so items frame both sides', () => {
  assert.match(gallery, /interactive \? items\.length : \(items\.length - 1\) \/ 2/);
  assert.match(gallery, /this\.scroll\.current = initialOffset/);
  assert.match(gallery, /this\.scroll\.target = initialOffset/);
});

test('gallery supports a page-specific pixel ratio cap', () => {
  assert.match(gallery, /dpr = 2/);
  assert.match(gallery, /Math\.min\(window\.devicePixelRatio \|\| 1, dpr\)/);
});

test('gallery supports a static non-interactive render mode', () => {
  assert.match(gallery, /interactive = true/);
  assert.match(gallery, /interactive \? \[\.\.\.items, \.\.\.items\] : items/);
  assert.match(gallery, /if \(this\.interactive\) this\.addEvents\(\)/);
  assert.match(gallery, /if \(this\.interactive\) this\.update\(\); else this\.renderFrame\(\)/);
  assert.match(gallery, /tabIndex=\{interactive \? 0 : -1\}/);
  assert.match(gallery, /interactive \? '循环图片画廊，可使用滚轮、拖拽或方向键浏览' : '静态循环图片画廊'/);
});

test('static gallery centers one copy of the supplied items', () => {
  assert.match(gallery, /items\.length - 1\) \/ 2/);
  assert.match(gallery, /if \(!this\.interactive\) return/);
  assert.match(gallery, /requestRender/);
});

test('static gallery reduces geometry and recenters after resize', () => {
  assert.match(gallery, /heightSegments:\s*interactive \? 50 : 24/);
  assert.match(gallery, /widthSegments:\s*interactive \? 100 : 48/);
  assert.match(gallery, /if \(!this\.interactive && this\.medias\[0\]\)/);
  assert.match(gallery, /this\.scroll\.current = staticOffset/);
});

test('static gallery can expose stable item selection hit targets', () => {
  assert.match(gallery, /onItemSelect\?: \(item: CircularGalleryItem, index: number\) => void/);
  assert.match(gallery, /circular-gallery__actions/);
  assert.match(gallery, /onClick=\{\(\) => onItemSelect\(item, index\)\}/);
  assert.match(gallery, /aria-label=\{item\.text\}/);
});
