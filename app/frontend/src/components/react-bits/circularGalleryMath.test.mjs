import test from 'node:test';
import assert from 'node:assert/strict';
import { arcTransform, lerp, snapTarget, wrapOffset } from './circularGalleryMath.mjs';

test('lerp approaches the target using the configured ease', () => {
  assert.equal(lerp(0, 10, 0.12), 1.2);
  assert.equal(lerp(10, 10, 0.12), 10);
});

test('snapTarget aligns scroll to the nearest media width', () => {
  assert.equal(snapTarget(5.1, 2), 6);
  assert.equal(snapTarget(-3.1, 2), -4);
});

test('wrapOffset moves media across the full loop only after it exits', () => {
  assert.equal(wrapOffset(-8, 1, 4, 20, 'right'), -20);
  assert.equal(wrapOffset(8, 1, 4, 20, 'left'), 20);
  assert.equal(wrapOffset(0, 1, 4, 20, 'right'), 0);
});

test('arcTransform bends edge media away from the center', () => {
  assert.deepEqual(arcTransform(0, 10, 3), { y: 0, rotation: 0 });
  const edge = arcTransform(5, 10, 3);
  assert.ok(edge.y < 0);
  assert.ok(edge.rotation < 0);
});
