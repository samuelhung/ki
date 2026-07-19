export function selectBriefingId(items, requestedId) {
  const validItems = Array.isArray(items)
    ? items.filter((item) => item && typeof item.id === 'string' && item.id)
    : [];
  if (validItems.some((item) => item.id === requestedId)) return requestedId;
  return validItems[0]?.id ?? '';
}

export function resolveBriefingLoadSelection({
  items,
  currentId,
  pendingPreferredId,
  succeeded,
}) {
  const pendingId = typeof pendingPreferredId === 'string' ? pendingPreferredId : '';
  if (!succeeded) {
    return {
      selectedId: currentId || '',
      pendingPreferredId: pendingId,
    };
  }
  const pendingIsAvailable = Array.isArray(items)
    && items.some((item) => item && item.id === pendingId);
  if (pendingId && !pendingIsAvailable) {
    return {
      selectedId: selectBriefingId(items, currentId),
      pendingPreferredId: pendingId,
    };
  }
  return {
    selectedId: selectBriefingId(items, pendingId || currentId),
    pendingPreferredId: '',
  };
}

export function briefingMetrics(detail) {
  return {
    typeLabel: detail?.type === 'daily' ? '深度日报' : '即时快报',
    generatedAt: typeof detail?.created_at === 'string' ? detail.created_at : '',
    topicCount: Array.isArray(detail?.topics) ? detail.topics.length : 0,
    eventCount: Number.isFinite(detail?.events_used) ? detail.events_used : 0,
  };
}
