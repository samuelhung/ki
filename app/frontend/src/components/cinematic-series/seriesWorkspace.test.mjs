import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildStage2Payload,
  getSeriesMemberCount,
  getSeriesStats,
  filterSeriesItems,
  mergeEventPage,
  removeSeriesItem,
  syncSeriesItem,
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

test('syncSeriesItem updates list metadata from the authoritative detail', () => {
  const items = [
    { id: 'a', name: '旧标题', member_ids: '["1"]', members: [{ id: '1' }], status: 'draft' },
    { id: 'b', name: '保留项', member_ids: '[]', status: 'published' },
  ];
  const detail = {
    id: 'a',
    name: '新标题',
    description: '新描述',
    member_ids: '["1","2"]',
    members: [{ id: '1' }, { id: '2' }],
    status: 'published',
    updated_at: '2026-07-12 12:00:00',
    intro: '列表不需要的大字段',
  };

  assert.deepEqual(syncSeriesItem(items, detail), [
    {
      id: 'a',
      name: '新标题',
      description: '新描述',
      member_ids: '["1","2"]',
      members: [{ id: '1' }, { id: '2' }],
      status: 'published',
      updated_at: '2026-07-12 12:00:00',
    },
    items[1],
  ]);
});

test('removeSeriesItem selects the adjacent remaining series', () => {
  const items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  assert.deepEqual(removeSeriesItem(items, 'b'), {
    items: [{ id: 'a' }, { id: 'c' }],
    selectedId: 'c',
  });
  assert.deepEqual(removeSeriesItem(items, 'c'), {
    items: [{ id: 'a' }, { id: 'b' }],
    selectedId: 'b',
  });
});

test('filterSeriesItems matches query and status without mutating source items', () => {
  const items = [
    { id: 'a', name: '中国社会转型', description: '乡土重建', status: 'published' },
    { id: 'b', name: 'AI 监管', description: '模型治理', status: 'draft' },
  ];
  assert.deepEqual(filterSeriesItems(items, '社会', 'all'), [items[0]]);
  assert.deepEqual(filterSeriesItems(items, '', 'draft'), [items[1]]);
  assert.deepEqual(items.map((item) => item.id), ['a', 'b']);
});

test('mergeEventPage appends unique events and resets for a new query', () => {
  const existing = [{ id: 'a' }, { id: 'b' }];
  assert.deepEqual(mergeEventPage(existing, [{ id: 'b' }, { id: 'c' }], false), [
    { id: 'a' }, { id: 'b' }, { id: 'c' },
  ]);
  assert.deepEqual(mergeEventPage(existing, [{ id: 'c' }], true), [{ id: 'c' }]);
});
