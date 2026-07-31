import type { EventDetailData } from '../../pages/EventDetailPage';

type RequestFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type EventDetailResponse = EventDetailData & { chain_analysis?: string };

export async function fetchEventDetail(
  request: RequestFn,
  eventId: string,
  signal: AbortSignal,
) {
  const response = await request(`/api/events/${eventId}`, { signal });
  if (!response.ok) throw new Error('刷新内容失败');
  return response.json() as Promise<EventDetailResponse>;
}

export async function transcriptSummaryIsStale(
  request: RequestFn,
  eventId: string,
  signal: AbortSignal,
) {
  const response = await request(`/api/events/${eventId}/transcript`, { signal });
  if (!response.ok) return false;
  const snapshot = await response.json() as { summary_stale?: boolean };
  return snapshot.summary_stale === true;
}

export async function summaryRefreshIsComplete(
  request: RequestFn,
  eventId: string,
  signal: AbortSignal,
  previousSummary: string,
  waitForFreshLineage: boolean,
) {
  const detail = await fetchEventDetail(request, eventId, signal);
  if (!detail.ai_summary) return null;
  if (!waitForFreshLineage && detail.ai_summary !== previousSummary) return detail;
  if (waitForFreshLineage && !await transcriptSummaryIsStale(request, eventId, signal)) {
    return detail;
  }
  return null;
}
