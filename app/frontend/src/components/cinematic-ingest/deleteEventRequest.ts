export const DELETE_FAILURE_FALLBACK = '删除失败，请稍后重试。';

type DeleteFetcher = (input: string, init: { method: 'DELETE' }) => Promise<Response>;

class DeleteEventRequestError extends Error {}

function safeDeleteText(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const message = value.trim();
  if (!message || message.length > 500 || /<[^>]+>|<!doctype|\n\s+at\s/i.test(message)) return null;
  return message;
}

function detailMessage(detail: unknown): string | null {
  const direct = safeDeleteText(detail);
  if (direct) return direct;
  if (!Array.isArray(detail)) return null;
  const messages = detail.slice(0, 5).map((item) => (
    item && typeof item === 'object' && 'msg' in item
      ? safeDeleteText((item as { msg?: unknown }).msg)
      : null
  )).filter((item): item is string => Boolean(item));
  return messages.length > 0 ? messages.join('；') : null;
}

export function deleteFailureMessage(reason: unknown): string {
  return reason instanceof Error
    ? safeDeleteText(reason.message) ?? DELETE_FAILURE_FALLBACK
    : DELETE_FAILURE_FALLBACK;
}

export async function deleteEventRequest(eventId: string, fetcher: DeleteFetcher): Promise<void> {
  try {
    const response = await fetcher(`/api/events/${eventId}`, { method: 'DELETE' });
    if (response.ok) return;
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const detail = payload && typeof payload === 'object' && 'detail' in payload
      ? (payload as { detail?: unknown }).detail
      : null;
    throw new DeleteEventRequestError(detailMessage(detail) ?? DELETE_FAILURE_FALLBACK);
  } catch (reason) {
    if (reason instanceof DeleteEventRequestError) throw reason;
    throw new DeleteEventRequestError(deleteFailureMessage(reason));
  }
}
