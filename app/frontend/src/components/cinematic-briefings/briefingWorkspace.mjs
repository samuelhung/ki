export function selectBriefingId(items, requestedId) {
  const validItems = Array.isArray(items)
    ? items.filter((item) => item && typeof item.id === 'string' && item.id)
    : [];
  if (validItems.some((item) => item.id === requestedId)) return requestedId;
  return validItems[0]?.id ?? '';
}

export function briefingMetrics(detail) {
  return {
    typeLabel: detail?.type === 'daily' ? '深度日报' : '即时快报',
    generatedAt: typeof detail?.created_at === 'string' ? detail.created_at : '',
    topicCount: Array.isArray(detail?.topics) ? detail.topics.length : 0,
    eventCount: Number.isFinite(detail?.events_used) ? detail.events_used : 0,
  };
}
