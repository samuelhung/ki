import test from 'node:test';
import assert from 'node:assert/strict';
import { filterLibraryEvents, filterSources, getLibraryStats, getSourceStats, resolveVisibleItem } from './libraryWorkspace.mjs';

const events = [
  { id: 'e1', title: '全球供应链重构', title_cn: '全球供应链重构', source_id: 'douyin', topic: '格局', status: 'ready' },
  { id: 'e2', title: '复利与现金流', source_id: 'user-upload', topic: '财富', status: 'processing' },
];
const sources = [
  { id: 's1', name: 'Reuters World', type: 'rss', topic: 'world', priority: 'high', enabled: 1, last_error: null },
  { id: 's2', name: 'BBC Technology', type: 'rss', topic: 'technology', priority: 'medium', enabled: 0, last_error: 'timeout' },
];

test('filterLibraryEvents combines topic status source and query', () => {
  assert.deepEqual(filterLibraryEvents(events, { topic: '格局', status: 'ready', source: 'douyin', query: '供应链' }), [events[0]]);
  assert.deepEqual(filterLibraryEvents(events, { topic: 'all', status: 'all', source: 'all', query: '现金流' }), [events[1]]);
});

test('filterSources matches state and text without mutating the source list', () => {
  assert.deepEqual(filterSources(sources, { state: 'error', query: 'BBC' }), [sources[1]]);
  assert.deepEqual(filterSources(sources, { state: 'enabled', query: '' }), [sources[0]]);
});

test('library and source statistics expose operator-level counts', () => {
  assert.deepEqual(getLibraryStats(events), { total: 2, ready: 1, processing: 1, errors: 0 });
  assert.deepEqual(getSourceStats(sources), { total: 2, enabled: 1, paused: 1, errors: 1 });
});

test('resolveVisibleItem moves selection to a visible adjacent item', () => {
  assert.equal(resolveVisibleItem(events, 'e2')?.id, 'e2');
  assert.equal(resolveVisibleItem([events[0]], 'e2')?.id, 'e1');
  assert.equal(resolveVisibleItem([], 'e2'), null);
});
