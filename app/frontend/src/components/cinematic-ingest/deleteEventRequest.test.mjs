import assert from 'node:assert/strict';
import test from 'node:test';

import { deleteEventRequest, deleteFailureMessage } from './deleteEventRequest.ts';

test('successful deletion issues exactly one request', async () => {
  const calls = [];
  await deleteEventRequest('evt-1', async (input, init) => {
    calls.push({ input, init });
    return new Response('{"ok":true}', { status: 200 });
  });
  assert.deepEqual(calls, [{ input: '/api/events/evt-1', init: { method: 'DELETE' } }]);
});

test('string backend detail is preserved', async () => {
  await assert.rejects(
    deleteEventRequest('evt-1', async () => new Response('{"detail":"内容仍被专题引用"}', { status: 409, headers: { 'Content-Type': 'application/json' } })),
    { message: '内容仍被专题引用' },
  );
});

test('validation details are reduced to readable messages', async () => {
  const response = new Response(JSON.stringify({ detail: [{ msg: '事件编号无效' }, { msg: '请求已过期' }] }), { status: 422 });
  await assert.rejects(deleteEventRequest('evt-1', async () => response), { message: '事件编号无效；请求已过期' });
});

test('unsafe or malformed errors use the stable fallback', async () => {
  assert.equal(deleteFailureMessage(new Error('<html>proxy failure</html>')), '删除失败，请稍后重试。');
  assert.equal(deleteFailureMessage(new Error('Traceback (most recent call last):\n  File "api.py", line 8\nSECRET_KEY=top-secret')), '删除失败，请稍后重试。');
  assert.equal(deleteFailureMessage(new Error('Authorization: Bearer sensitive-token')), '删除失败，请稍后重试。');
  await assert.rejects(deleteEventRequest('evt-1', async () => new Response('<html>failure</html>', { status: 500 })), { message: '删除失败，请稍后重试。' });
});

test('short network errors stay readable', () => {
  assert.equal(deleteFailureMessage(new Error('网络连接已中断')), '网络连接已中断');
});
