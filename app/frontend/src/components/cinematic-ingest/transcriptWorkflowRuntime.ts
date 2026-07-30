import type {
  SegmentationTaskSnapshot,
  TranscriptRevisionMeta,
  TranscriptSnapshot,
} from '../../pages/EventDetailPage';

type RequestFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type SelectionOwner = { selectedId?: string; sequence: number };

export function createTranscriptApi(request: RequestFn) {
  async function send<T>(url: string, init?: RequestInit): Promise<T> {
    const response = await request(url, init);
    if (!response.ok) {
      throw Object.assign(new Error('Transcript request failed'), { status: response.status });
    }
    return response.json() as Promise<T>;
  }
  const jsonInit = (method: string, body: object): RequestInit => ({
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return {
    load: (eventId: string, signal: AbortSignal) => send<TranscriptSnapshot>(
      `/api/events/${eventId}/transcript`, { signal },
    ),
    loadRevision: (eventId: string, revisionId: string, signal: AbortSignal) => (
      send<TranscriptRevisionMeta & { content: string }>(
        `/api/events/${eventId}/transcript/revisions/${revisionId}`, { signal },
      )
    ),
    saveManual: (eventId: string, content: string, baseRevisionId: string) => (
      send<TranscriptSnapshot>(
        `/api/events/${eventId}/transcript/manual`,
        jsonInit('PUT', { content, base_revision_id: baseRevisionId }),
      )
    ),
    startSegmentation: (eventId: string, baseRevisionId: string) => (
      send<SegmentationTaskSnapshot>(
        `/api/events/${eventId}/transcript/segment`,
        jsonInit('POST', { base_revision_id: baseRevisionId }),
      )
    ),
    loadTask: (eventId: string, taskId: string, signal: AbortSignal) => (
      send<SegmentationTaskSnapshot>(
        `/api/events/${eventId}/transcript/segment/${taskId}`, { signal },
      )
    ),
    confirmSegmentation: (eventId: string, taskId: string) => (
      send<TranscriptSnapshot & { confirmed_revision_id: string }>(
        `/api/events/${eventId}/transcript/segment/${taskId}/confirm`,
        { method: 'POST' },
      )
    ),
    restoreRevision: (eventId: string, revisionId: string, baseRevisionId: string) => (
      send<TranscriptSnapshot>(
        `/api/events/${eventId}/transcript/revisions/${revisionId}/restore`,
        jsonInit('POST', { base_revision_id: baseRevisionId }),
      )
    ),
  };
}

export function createTranscriptSelectionOwner(initialSelectedId?: string) {
  let selectedId = initialSelectedId;
  let sequence = 0;
  const capture = (): SelectionOwner => ({ selectedId, sequence });
  return {
    capture,
    select(nextSelectedId?: string) {
      if (nextSelectedId !== selectedId) {
        selectedId = nextSelectedId;
        sequence += 1;
      }
      return capture();
    },
    isCurrent(owner: SelectionOwner) {
      return owner.selectedId === selectedId && owner.sequence === sequence;
    },
  };
}

export function createSegmentGuard() {
  const active = new Set<string>();
  return {
    begin(eventId: string) {
      if (active.has(eventId)) return false;
      active.add(eventId);
      return true;
    },
    end(eventId: string) { active.delete(eventId); },
  };
}

export function conflictMessage(status: number) {
  if (status === 410) {
    return { message: '分段结果已过期，请重新生成', refreshRequired: false };
  }
  return status === 409
    ? { message: '原文已更新，请刷新后重试', refreshRequired: true }
    : { message: '操作失败，请稍后重试', refreshRequired: false };
}

export function isTranscriptAbortError(reason: unknown) {
  if (reason instanceof DOMException && reason.name === 'AbortError') return true;
  return Boolean(
    reason
    && typeof reason === 'object'
    && 'name' in reason
    && reason.name === 'AbortError'
    && (!('kind' in reason) || reason.kind === 'cancelled'),
  );
}

export function segmentationPollDelay(now: number, expiresAt: number) {
  return Math.max(0, Math.min(1000, expiresAt - now));
}
