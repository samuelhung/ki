import assert from 'node:assert/strict';
import test from 'node:test';

import { createSystemDialogController } from './systemDialogRuntime.ts';

const confirmOptions = (overrides = {}) => ({
  title: '删除专题',
  message: '删除后无法恢复',
  action: async () => {},
  errorTitle: '无法删除',
  errorFallback: '操作失败，请稍后重试',
  ...overrides,
});

test('alert 保持可见，确认后完成并清空快照', async () => {
  const controller = createSystemDialogController();
  let settled = false;
  const result = controller.alert({ title: '提示', message: '已保存' }).then(() => { settled = true; });

  assert.deepEqual(controller.getSnapshot(), {
    kind: 'alert', title: '提示', message: '已保存', tone: 'default', pending: false,
    confirmLabel: '', cancelLabel: '', pendingLabel: '', acknowledgeLabel: '知道了',
  });
  await Promise.resolve();
  assert.equal(settled, false);
  controller.acknowledge();
  await result;
  assert.equal(controller.getSnapshot(), null);
});

test('confirmAction pending 时锁定，重复确认只执行一次并在成功后关闭', async () => {
  const controller = createSystemDialogController();
  let calls = 0;
  let release;
  const result = controller.confirmAction(confirmOptions({
    action: () => new Promise((resolve) => { calls += 1; release = resolve; }),
  }));

  const firstConfirm = controller.confirm();
  const secondConfirm = controller.confirm();
  assert.equal(typeof firstConfirm.then, 'function');
  assert.equal(calls, 1);
  assert.equal(controller.getSnapshot()?.pending, true);
  release();
  await Promise.all([firstConfirm, secondConfirm]);
  assert.equal(await result, 'completed');
  assert.equal(controller.getSnapshot(), null);
});

test('action 失败后原确认原位转为 alert，确认后返回 failed', async () => {
  const controller = createSystemDialogController();
  const result = controller.confirmAction(confirmOptions({
    action: async () => { throw new Error('内容仍被 2 个专题引用'); },
  }));

  controller.confirm();
  await Promise.resolve();
  await Promise.resolve();
  assert.deepEqual(controller.getSnapshot(), {
    kind: 'alert', title: '无法删除', message: '内容仍被 2 个专题引用', tone: 'danger', pending: false,
    confirmLabel: '', cancelLabel: '', pendingLabel: '', acknowledgeLabel: '知道了',
  });
  controller.acknowledge();
  assert.equal(await result, 'failed');
});

test('默认四类标签明确可用，所有快照标签均为字符串', async () => {
  const controller = createSystemDialogController();
  const alert = controller.alert({ title: '提示', message: '消息' });
  assert.deepEqual(controller.getSnapshot(), {
    kind: 'alert', title: '提示', message: '消息', tone: 'default', pending: false,
    confirmLabel: '', cancelLabel: '', pendingLabel: '', acknowledgeLabel: '知道了',
  });
  controller.acknowledge();
  await alert;

  const confirmation = controller.confirmAction(confirmOptions());
  assert.deepEqual(controller.getSnapshot(), {
    kind: 'confirm', title: '删除专题', message: '删除后无法恢复', tone: 'danger', pending: false,
    confirmLabel: '确认', cancelLabel: '取消', pendingLabel: '处理中...', acknowledgeLabel: '知道了',
  });
  controller.cancel();
  await confirmation;
});

test('不安全或不可用的 action 错误消息使用 fallback', async () => {
  const controller = createSystemDialogController();
  const unsafeReasons = [
    'not-an-error',
    new Error('<strong>内部错误</strong>'),
    new Error('Error: boom\n    at remove (runtime.ts:1:1)'),
    new Error('x'.repeat(501)),
  ];

  for (const reason of unsafeReasons) {
    const result = controller.confirmAction(confirmOptions({
      action: async () => { throw reason; },
      errorFallback: '安全提示',
    }));
    await controller.confirm();
    assert.equal(controller.getSnapshot()?.kind, 'alert');
    assert.equal(controller.getSnapshot()?.message, '安全提示');
    controller.acknowledge();
    assert.equal(await result, 'failed');
  }
});

test('cancel 返回 cancelled 且不会执行 action', async () => {
  const controller = createSystemDialogController();
  let calls = 0;
  const result = controller.confirmAction(confirmOptions({ action: async () => { calls += 1; } }));

  controller.cancel();
  assert.equal(await result, 'cancelled');
  assert.equal(calls, 0);
  assert.equal(controller.getSnapshot(), null);
});

test('两个 alert 按 FIFO 串行且 Promise 均正常结算', async () => {
  const controller = createSystemDialogController();
  let firstDone = false;
  let secondDone = false;
  const first = controller.alert({ title: '一', message: 'first' }).then(() => { firstDone = true; });
  const second = controller.alert({ title: '二', message: 'second' }).then(() => { secondDone = true; });

  assert.equal(controller.getSnapshot()?.title, '一');
  controller.acknowledge();
  await first;
  assert.equal(firstDone, true);
  assert.equal(secondDone, false);
  assert.equal(controller.getSnapshot()?.title, '二');
  controller.acknowledge();
  await second;
  assert.equal(secondDone, true);
  assert.equal(controller.getSnapshot(), null);
});

test('pending 忽略 cancel，destroy 结算所有请求且迟到 action 不会恢复快照', async () => {
  const controller = createSystemDialogController();
  let release;
  const active = controller.confirmAction(confirmOptions({
    action: () => new Promise((resolve) => { release = resolve; }),
  }));
  const queued = controller.alert({ title: '稍后', message: 'queued' });

  controller.confirm();
  controller.cancel();
  assert.equal(controller.getSnapshot()?.pending, true);
  controller.destroy();
  assert.equal(await active, 'cancelled');
  await queued;
  assert.equal(controller.getSnapshot(), null);
  release();
  await Promise.resolve();
  assert.equal(controller.getSnapshot(), null);
  await controller.alert({ title: '已销毁', message: 'ignored' });
  assert.equal(await controller.confirmAction(confirmOptions()), 'cancelled');
});
