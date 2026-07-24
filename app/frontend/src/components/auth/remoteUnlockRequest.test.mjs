import assert from 'node:assert/strict';
import test from 'node:test';
import {
  RemoteUnlockError,
  remoteUnlockErrorMessage,
  validateRemoteUnlockToken,
} from './remoteUnlockRequest.ts';

function response(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

test('healthy protected response validates the token without exposing it', async () => {
  const calls = [];
  await validateRemoteUnlockToken(' secret-token ', {
    endpoint: '/api/system/health',
    request: async (input, init) => {
      calls.push({ input, init });
      return response({ ok: true, database: { ok: true } });
    },
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].input, '/api/system/health');
  assert.equal(new Headers(calls[0].init.headers).get('Authorization'), 'Bearer secret-token');
  assert.equal(calls[0].init.timeoutMs, 10_000);
});

test('401 is classified as an invalid token', async () => {
  await assert.rejects(
    validateRemoteUnlockToken('wrong', { request: async () => response({}, 401) }),
    (error) => error instanceof RemoteUnlockError && error.kind === 'invalid-token',
  );
});

test('invalid JSON and unhealthy payload are rejected', async () => {
  await assert.rejects(
    validateRemoteUnlockToken('token', {
      request: async () => new Response('not-json', { status: 200 }),
    }),
    (error) => error instanceof RemoteUnlockError && error.kind === 'invalid-response',
  );
  await assert.rejects(
    validateRemoteUnlockToken('token', {
      request: async () => response({ ok: true, database: { ok: false } }),
    }),
    (error) => error instanceof RemoteUnlockError && error.kind === 'unhealthy',
  );
});

test('user messages remain stable and never include token values', () => {
  assert.equal(remoteUnlockErrorMessage(new RemoteUnlockError('invalid-token')), '访问令牌无效');
  assert.equal(remoteUnlockErrorMessage(new RemoteUnlockError('network')), '无法连接知几服务');
  assert.doesNotMatch(remoteUnlockErrorMessage(new Error('secret-token')), /secret-token/);
});
