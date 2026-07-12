import test from 'node:test';
import assert from 'node:assert/strict';

import { filterStudyItems, getStudyStats, removeStudyItem } from './studyWorkspace.mjs';

test('filterStudyItems combines subject and title query', () => {
  const items = [
    { id: 'a', subject: '语文', title: '乡下人家阅读理解' },
    { id: 'b', subject: '数学', title: '行程问题' },
  ];
  assert.deepEqual(filterStudyItems(items, '语文', '乡下'), [items[0]]);
  assert.deepEqual(filterStudyItems(items, '全部', '问题'), [items[1]]);
});

test('getStudyStats reports ready reviewed and mistakes', () => {
  assert.deepEqual(getStudyStats([
    { status: 'ready', is_correct: null },
    { status: 'reviewed', is_correct: 1 },
    { status: 'reviewed', is_correct: 0 },
    { status: 'draft', is_correct: null },
  ]), { total: 4, ready: 1, reviewed: 2, mistakes: 1 });
});

test('removeStudyItem selects the adjacent remaining item', () => {
  assert.deepEqual(removeStudyItem([{ id: 'a' }, { id: 'b' }, { id: 'c' }], 'b'), {
    items: [{ id: 'a' }, { id: 'c' }],
    selectedId: 'c',
  });
});
