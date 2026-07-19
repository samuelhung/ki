import test from 'node:test';
import assert from 'node:assert/strict';

import { createChainDetailCache } from './chainDetailCache.mjs';

test('chain detail cache keeps chat history isolated by chain', () => {
  const cache = createChainDetailCache();
  const messages = [{ role: 'user', content: '上游风险是什么？' }];

  cache.setChat('光伏产业链', messages);
  messages.push({ role: 'assistant', content: '外部 mutation' });

  assert.deepEqual(cache.getChat('光伏产业链'), [{ role: 'user', content: '上游风险是什么？' }]);
  assert.deepEqual(cache.getChat('芯片产业链'), []);
});

test('chain detail cache retains report metadata across chain switches', () => {
  const cache = createChainDetailCache();

  cache.setReport('光伏产业链', { report: 'report-a', cached: true });
  cache.setReport('芯片产业链', { report: 'report-b', cached: false });

  assert.deepEqual(cache.getReport('光伏产业链'), { report: 'report-a', cached: true });
  assert.deepEqual(cache.getReport('芯片产业链'), { report: 'report-b', cached: false });
});

test('clearing one chain chat does not evict reports or other chains', () => {
  const cache = createChainDetailCache();
  cache.setChat('光伏产业链', [{ role: 'user', content: 'a' }]);
  cache.setChat('芯片产业链', [{ role: 'user', content: 'b' }]);
  cache.setReport('光伏产业链', { report: 'report-a', cached: true });

  cache.clearChat('光伏产业链');

  assert.deepEqual(cache.getChat('光伏产业链'), []);
  assert.equal(cache.getChat('芯片产业链').length, 1);
  assert.equal(cache.getReport('光伏产业链')?.report, 'report-a');
});
