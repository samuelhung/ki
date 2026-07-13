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
  assert.match(gallery, /const initialOffset = this\.medias\[0\]\.width \* items\.length/);
  assert.match(gallery, /this\.scroll\.current = initialOffset/);
  assert.match(gallery, /this\.scroll\.target = initialOffset/);
});
