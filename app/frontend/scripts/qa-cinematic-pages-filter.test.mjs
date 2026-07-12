import test from 'node:test';
import assert from 'node:assert/strict';

import { selectCinematicPages } from './qa-cinematic-pages-core.mjs';

test('selectCinematicPages returns only requested page keys', () => {
  assert.deepEqual(selectCinematicPages(['study']).map((page) => page.key), ['study']);
  assert.deepEqual(selectCinematicPages(['study', 'system']).map((page) => page.key), ['system', 'study']);
});

test('selectCinematicPages rejects unknown page keys', () => {
  assert.throws(() => selectCinematicPages(['missing']), /Unknown cinematic page key/);
});
