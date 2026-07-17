export interface RequestOwner {
  sequence: number;
  signal: AbortSignal;
}

export class RequestLifecycle {
  private sequence = 0;
  private controller: AbortController | null = null;

  start(): RequestOwner {
    this.controller?.abort();
    this.controller = new AbortController();
    return { sequence: ++this.sequence, signal: this.controller.signal };
  }

  isCurrent(sequence: number) {
    return sequence === this.sequence && !this.controller?.signal.aborted;
  }

  abort() {
    this.controller?.abort();
    this.controller = null;
    this.sequence += 1;
  }
}

export function abortableDelay(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const rejectAbort = () => reject(new DOMException('Aborted', 'AbortError'));
    if (signal.aborted) {
      rejectAbort();
      return;
    }

    const onAbort = () => {
      globalThis.clearTimeout(timer);
      signal.removeEventListener('abort', onAbort);
      rejectAbort();
    };
    const timer = globalThis.setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);

    signal.addEventListener('abort', onAbort, { once: true });
  });
}
