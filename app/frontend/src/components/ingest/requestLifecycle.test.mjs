import assert from 'node:assert/strict';
import test from 'node:test';
import { RequestLifecycle, abortableDelay } from './requestLifecycle.ts';

test('starting a request aborts the previous owner', () => {
  const lifecycle = new RequestLifecycle();
  const first = lifecycle.start();
  const second = lifecycle.start();

  assert.equal(first.signal.aborted, true);
  assert.equal(second.signal.aborted, false);
  assert.equal(lifecycle.isCurrent(first.sequence), false);
  assert.equal(lifecycle.isCurrent(second.sequence), true);
});

test('aborting the lifecycle invalidates its current owner', () => {
  const lifecycle = new RequestLifecycle();
  const request = lifecycle.start();

  lifecycle.abort();

  assert.equal(request.signal.aborted, true);
  assert.equal(lifecycle.isCurrent(request.sequence), false);
});

test('abortable delay rejects immediately when its signal aborts', async () => {
  const controller = new AbortController();
  const waiting = abortableDelay(10_000, controller.signal);

  controller.abort();

  await assert.rejects(waiting, { name: 'AbortError' });
});
