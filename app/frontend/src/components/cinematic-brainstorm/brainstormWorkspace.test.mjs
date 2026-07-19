import test from 'node:test';
import assert from 'node:assert/strict';
import { filterBrainstormQuestions, getBrainstormStats, linkedEventCount, removeBrainstormQuestion, resolveBrainstormSelection } from './brainstormWorkspace.mjs';

const items = [
  { id: 'a', question: '全球供应链如何重构', topic: '格局', status: 'open', answered_event_ids: '["1","2"]' },
  { id: 'b', question: '复利的底层逻辑', topic: '财富', status: 'done', answered_event_ids: '[]' },
];

test('filterBrainstormQuestions combines topic and query', () => {
  assert.deepEqual(filterBrainstormQuestions(items, '格局', '供应链'), [items[0]]);
  assert.deepEqual(filterBrainstormQuestions(items, '全部', '复利'), [items[1]]);
});

test('brainstorm helpers report linked documents and status counts', () => {
  assert.equal(linkedEventCount(items[0]), 2);
  assert.deepEqual(getBrainstormStats(items), { total: 2, open: 1, done: 1, linked: 2 });
});

test('removeBrainstormQuestion selects the adjacent item', () => {
  assert.deepEqual(removeBrainstormQuestion(items, 'a'), { items: [items[1]], selectedId: 'b' });
});

test('resolveBrainstormSelection keeps deep links and falls back deterministically', () => {
  assert.equal(resolveBrainstormSelection(items, 'b', ''), 'b');
  assert.equal(resolveBrainstormSelection(items, '', 'a'), 'a');
  assert.equal(resolveBrainstormSelection(items, 'missing', 'b'), 'b');
  assert.equal(resolveBrainstormSelection([], 'a', 'b'), '');
});
