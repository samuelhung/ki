export type DialogTone = 'default' | 'danger';
export type ConfirmActionResult = 'completed' | 'cancelled' | 'failed';

export type AlertOptions = {
  title: string;
  message: string;
  acknowledgeLabel?: string;
  tone?: DialogTone;
};

export type ConfirmActionOptions = {
  title: string;
  message: string;
  action: () => Promise<void>;
  errorTitle: string;
  errorFallback: string;
  confirmLabel?: string;
  cancelLabel?: string;
  pendingLabel?: string;
  acknowledgeLabel?: string;
  tone?: DialogTone;
};

export type SystemDialogSnapshot = null | {
  kind: 'alert' | 'confirm';
  title: string;
  message: string;
  tone: DialogTone;
  pending: boolean;
  confirmLabel: string;
  cancelLabel: string;
  pendingLabel: string;
  acknowledgeLabel: string;
};

export type SystemDialogController = {
  getSnapshot: () => SystemDialogSnapshot;
  subscribe: (listener: () => void) => () => void;
  alert: (options: AlertOptions) => Promise<void>;
  confirmAction: (options: ConfirmActionOptions) => Promise<ConfirmActionResult>;
  confirm: () => Promise<void>;
  cancel: () => void;
  acknowledge: () => void;
  destroy: () => void;
};

type AlertRequest = {
  type: 'alert';
  options: AlertOptions;
  resolve: () => void;
};

type ConfirmRequest = {
  type: 'confirm';
  options: ConfirmActionOptions;
  resolve: (result: ConfirmActionResult) => void;
  phase: 'ready' | 'pending' | 'failed';
  error?: unknown;
};

type DialogRequest = AlertRequest | ConfirmRequest;

const defaultLabels = {
  confirm: '确认',
  cancel: '取消',
  pending: '处理中...',
  acknowledge: '知道了',
};

function safeErrorMessage(reason: unknown, fallback: string) {
  if (!(reason instanceof Error)) return fallback;
  const message = reason.message.trim();
  if (!message || message.length > 500) return fallback;
  if (/<[^>]*>|<!doctype/i.test(message)) return fallback;
  if (/(?:^|\n)\s*at\s+/.test(message)) return fallback;
  return message;
}

export function createSystemDialogController(): SystemDialogController {
  let active: DialogRequest | null = null;
  const queue: DialogRequest[] = [];
  const listeners = new Set<() => void>();
  let destroyed = false;

  const notify = () => {
    for (const listener of listeners) listener();
  };

  const promote = () => {
    active = queue.shift() ?? null;
    notify();
  };

  const finishActive = () => {
    active = null;
    promote();
  };

  const enqueue = (request: DialogRequest) => {
    if (active) {
      queue.push(request);
      return;
    }
    active = request;
    notify();
  };

  const getSnapshot = (): SystemDialogSnapshot => {
    if (!active) return null;
    if (active.type === 'alert') {
      return {
        kind: 'alert',
        title: active.options.title,
        message: active.options.message,
        tone: active.options.tone ?? 'default',
        pending: false,
        confirmLabel: '',
        cancelLabel: '',
        pendingLabel: '',
        acknowledgeLabel: active.options.acknowledgeLabel ?? defaultLabels.acknowledge,
      };
    }
    if (active.phase === 'failed') {
      return {
        kind: 'alert',
        title: active.options.errorTitle,
        message: safeErrorMessage(active.error, active.options.errorFallback),
        tone: active.options.tone ?? 'danger',
        pending: false,
        confirmLabel: '',
        cancelLabel: '',
        pendingLabel: '',
        acknowledgeLabel: active.options.acknowledgeLabel ?? defaultLabels.acknowledge,
      };
    }
    return {
      kind: 'confirm',
      title: active.options.title,
      message: active.options.message,
      tone: active.options.tone ?? 'danger',
      pending: active.phase === 'pending',
      confirmLabel: active.options.confirmLabel ?? defaultLabels.confirm,
      cancelLabel: active.options.cancelLabel ?? defaultLabels.cancel,
      pendingLabel: active.options.pendingLabel ?? defaultLabels.pending,
      acknowledgeLabel: active.options.acknowledgeLabel ?? defaultLabels.acknowledge,
    };
  };

  return {
    getSnapshot,
    subscribe(listener) {
      if (destroyed) return () => {};
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    alert(options) {
      if (destroyed) return Promise.resolve();
      return new Promise((resolve) => enqueue({ type: 'alert', options, resolve }));
    },
    confirmAction(options) {
      if (destroyed) return Promise.resolve('cancelled');
      return new Promise((resolve) => enqueue({ type: 'confirm', options, resolve, phase: 'ready' }));
    },
    async confirm() {
      if (destroyed || !active || active.type !== 'confirm' || active.phase !== 'ready') return;
      const request = active;
      request.phase = 'pending';
      notify();
      try {
        await request.options.action();
        if (destroyed || active !== request || request.phase !== 'pending') return;
        request.resolve('completed');
        finishActive();
      } catch (reason) {
        if (destroyed || active !== request || request.phase !== 'pending') return;
        request.error = reason;
        request.phase = 'failed';
        notify();
      }
    },
    cancel() {
      if (destroyed || !active || active.type !== 'confirm' || active.phase !== 'ready') return;
      active.resolve('cancelled');
      finishActive();
    },
    acknowledge() {
      if (destroyed || !active) return;
      if (active.type === 'alert') active.resolve();
      else if (active.phase === 'failed') active.resolve('failed');
      else return;
      finishActive();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      if (active?.type === 'alert') active.resolve();
      if (active?.type === 'confirm') active.resolve('cancelled');
      for (const request of queue) {
        if (request.type === 'alert') request.resolve();
        else request.resolve('cancelled');
      }
      active = null;
      queue.length = 0;
      listeners.clear();
    },
  };
}
