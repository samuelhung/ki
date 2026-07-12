import test from 'node:test';
import assert from 'node:assert/strict';
import {
  filterTasks,
  getTaskStats,
  mergeTaskSnapshot,
  removeTask,
} from './taskWorkspace.mjs';

const tasks = [
  { id: 'a', title: '复盘产业链资料', description: '整理上游节点', status: 'todo', priority: 'high', source: 'series' },
  { id: 'b', title: '补充脑暴结论', description: '形成行动项', status: 'in_progress', priority: 'medium', source: 'brainstorm' },
  { id: 'c', title: '归档会议记录', description: '', status: 'done', priority: 'low', source: 'manual' },
];

test('filterTasks combines status, source, priority, and query', () => {
  assert.deepEqual(filterTasks(tasks, { status: 'todo', source: 'series', priority: 'high', query: '上游' }), [tasks[0]]);
  assert.deepEqual(filterTasks(tasks, { status: 'all', source: 'all', priority: 'all', query: '行动' }), [tasks[1]]);
});

test('getTaskStats reports lifecycle totals', () => {
  assert.deepEqual(getTaskStats(tasks), { total: 3, todo: 1, inProgress: 1, done: 1, overdue: 0 });
});

test('mergeTaskSnapshot preserves local mutations and deletion tombstones', () => {
  const local = [{ ...tasks[0], title: '本地已更新' }, tasks[1]];
  const remote = [tasks[0], tasks[1], tasks[2]];
  assert.deepEqual(
    mergeTaskSnapshot(local, remote, new Set(['c']), new Set(['a'])),
    [local[0], tasks[1]],
  );
});

test('removeTask selects the adjacent task without forcing another selection later', () => {
  assert.deepEqual(removeTask(tasks, 'b', 'b'), { tasks: [tasks[0], tasks[2]], selectedId: 'c' });
  assert.deepEqual(removeTask(tasks, 'b', 'a'), { tasks: [tasks[0], tasks[2]], selectedId: 'a' });
});
