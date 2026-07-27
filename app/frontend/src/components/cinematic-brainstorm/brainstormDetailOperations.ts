import { isLatestRequest } from '../ingest/ingestRequestPolicy';
import { RequestLifecycle, type RequestOwner } from '../ingest/requestLifecycle';

export function createOperationGroup() {
  return {
    lifecycle: new RequestLifecycle(), latestSequence: 0, activeName: null as string | null,
    activeLoadingChange: null as ((loading: boolean) => void) | null,
  };
}

export function createOperationLifecycle(
  name: string,
  onLoadingChange: (loading: boolean) => void,
  group = createOperationGroup(),
) {
  function start() {
    const previousLoadingChange = group.activeLoadingChange;
    const owner = group.lifecycle.start();
    previousLoadingChange?.(false);
    group.latestSequence = owner.sequence;
    group.activeName = name;
    group.activeLoadingChange = onLoadingChange;
    onLoadingChange(true);
    return owner;
  }
  function isCurrent(owner: RequestOwner) {
    return group.activeName === name
      && group.lifecycle.isCurrent(owner.sequence)
      && isLatestRequest(owner.sequence, group.latestSequence);
  }
  function finish(owner: RequestOwner) {
    if (!isCurrent(owner)) return;
    group.activeName = null; group.activeLoadingChange = null; onLoadingChange(false);
  }
  function abort() {
    if (group.activeName !== name) return;
    group.lifecycle.abort(); group.latestSequence += 1;
    group.activeName = null; group.activeLoadingChange = null; onLoadingChange(false);
  }
  function isActive() {
    return group.activeName === name && group.lifecycle.isCurrent(group.latestSequence);
  }
  return { start, isCurrent, finish, abort, isActive };
}

export function recoverFailedFollowUp<Message extends { id: number }>(
  messages: Message[], pendingId: number, text: string, reason: unknown,
) {
  if (reason instanceof DOMException && reason.name === 'AbortError') return null;
  return {
    messages: messages.filter((message) => message.id !== pendingId),
    text,
    error: reason instanceof Error ? reason.message : '发送失败',
  };
}
