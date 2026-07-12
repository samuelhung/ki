import test from 'node:test';
import assert from 'node:assert/strict';

import { buildChainGroups, filterChainGroups, getChainStats } from './chainWorkspace.mjs';

const nodes = [
  { id: 'a', chain: '光伏产业链', name: '硅料', node_type: '原材料' },
  { id: 'b', chain: '光伏产业链', name: '组件', node_type: '终端' },
  { id: 'c', chain: '芯片产业链', name: '晶圆', node_type: '中间品' },
];

test('buildChainGroups groups nodes without mutating source order', () => {
  const groups = buildChainGroups(nodes);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].name, '光伏产业链');
  assert.equal(groups[0].nodes.length, 2);
  assert.equal(nodes[0].id, 'a');
});

test('filterChainGroups matches chain and node names', () => {
  const groups = buildChainGroups(nodes);
  assert.deepEqual(filterChainGroups(groups, '晶圆').map((item) => item.name), ['芯片产业链']);
  assert.deepEqual(filterChainGroups(groups, '光伏').map((item) => item.name), ['光伏产业链']);
});

test('getChainStats reports chain node and coverage totals', () => {
  assert.deepEqual(getChainStats(buildChainGroups(nodes), 4, 2), {
    chains: 2, nodes: 3, hints: 4, suggestions: 2,
  });
});
