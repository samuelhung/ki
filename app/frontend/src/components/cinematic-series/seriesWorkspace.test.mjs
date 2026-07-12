import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildStage2Payload,
  getSeriesMemberCount,
  getSeriesStats,
  parseMemberIds,
} from './seriesWorkspace.mjs';

test('parseMemberIds accepts JSON arrays and comma separated ids', () => {
  assert.deepEqual(parseMemberIds('["a","b"]'), ['a', 'b']);
  assert.deepEqual(parseMemberIds('a,b, c'), ['a', 'b', 'c']);
  assert.deepEqual(parseMemberIds(''), []);
});

test('getSeriesMemberCount prefers hydrated members and falls back to member ids', () => {
  assert.equal(getSeriesMemberCount({ members: [{ id: 'a' }, { id: 'b' }], member_ids: '["x"]' }), 2);
  assert.equal(getSeriesMemberCount({ members: [], member_ids: '["x","y","z"]' }), 3);
});

test('getSeriesStats separates ready and processing topics', () => {
  assert.deepEqual(getSeriesStats([
    { status: 'ready' },
    { status: 'completed' },
    { status: 'published' },
    { status: 'processing' },
    { status: 'pending' },
  ]), { total: 5, ready: 3, processing: 2 });
});

test('buildStage2Payload deduplicates event ids and joins selected group names', () => {
  const payload = buildStage2Payload([
    { name: '宏观', event_ids: ['a', 'b'] },
    { name: '产业', event_ids: ['b', 'c'] },
  ]);
  assert.deepEqual(payload, { event_ids: ['a', 'b', 'c'], name_hint: '宏观、产业' });
});
