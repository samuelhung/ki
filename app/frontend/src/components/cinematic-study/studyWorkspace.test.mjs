import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildStudyCreatePayload,
  buildStudyUploadFields,
  createStudyDetailCache,
  filterStudyItems,
  getStudyStats,
  mergeStudyReview,
  removeStudyItem,
} from './studyWorkspace.mjs';

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

test('buildStudyCreatePayload keeps category separate from exercise type', () => {
  assert.deepEqual(buildStudyCreatePayload({
    subject: '数学', category: '单项训练', type: '应用题', title: '行程题',
    raw_content: '题目正文', grade: '四年级', textbook: '',
  }), {
    subject: '数学', study_type: '应用题', title: '行程题', raw_content: '题目正文',
    grade: '四年级', textbook: '',
  });
  assert.equal(buildStudyCreatePayload({ category: '期中试卷', type: '应用题' }).study_type, '期中试卷');
});

test('buildStudyUploadFields preserves textbook category and linked type', () => {
  assert.deepEqual(buildStudyUploadFields({
    subject: '语文', category: '教材/课本', type: '阅读理解', grade: '四年级', title: '语文下册',
  }), {
    category: '教材/课本', subject: '语文', study_type: '阅读理解', grade: '四年级', title: '语文下册',
  });
});

test('mergeStudyReview marks a material reviewed and updates mistake tags', () => {
  assert.deepEqual(mergeStudyReview({ id: 'a', status: 'ready', is_correct: null, mistake_tags: [] }, {
    is_correct: 0, score: 62, mistake_tags: ['审题', '计算'], review_content: '先找数量关系',
  }), {
    id: 'a', status: 'reviewed', is_correct: 0, score: 62,
    mistake_tags: ['审题', '计算'], review_content: '先找数量关系',
  });
});

test('createStudyDetailCache reuses loaded detail and evicts oldest entries', () => {
  const cache = createStudyDetailCache(2);
  cache.set('a', { id: 'a' });
  cache.set('b', { id: 'b' });
  assert.equal(cache.get('a').id, 'a');
  cache.set('c', { id: 'c' });
  assert.equal(cache.get('b'), undefined);
  assert.equal(cache.get('a').id, 'a');
  assert.equal(cache.get('c').id, 'c');
});
