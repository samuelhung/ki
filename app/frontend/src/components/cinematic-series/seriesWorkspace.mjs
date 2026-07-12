export function parseMemberIds(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (!value || typeof value !== 'string') return [];
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) return parsed.filter(Boolean);
  } catch {}
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

export function getSeriesMemberCount(series) {
  if (Array.isArray(series?.members) && series.members.length > 0) return series.members.length;
  return parseMemberIds(series?.member_ids).length;
}

export function getSeriesStats(series) {
  const items = Array.isArray(series) ? series : [];
  const ready = items.filter((item) => ['ready', 'completed', 'active', 'published'].includes(item?.status)).length;
  return { total: items.length, ready, processing: items.length - ready };
}

export function buildStage2Payload(groups) {
  const selected = Array.isArray(groups) ? groups : [];
  return {
    event_ids: [...new Set(selected.flatMap((group) => group?.event_ids || []))],
    name_hint: selected.map((group) => group?.name).filter(Boolean).join('、'),
  };
}

const SERIES_LIST_FIELDS = [
  'id', 'name', 'description', 'member_ids', 'members', 'status', 'created_at', 'updated_at',
];

export function syncSeriesItem(items, detail) {
  if (!detail?.id) return Array.isArray(items) ? items : [];
  const summary = Object.fromEntries(
    SERIES_LIST_FIELDS
      .filter((field) => detail[field] !== undefined)
      .map((field) => [field, detail[field]]),
  );
  return (Array.isArray(items) ? items : []).map((item) => (
    item.id === detail.id ? { ...item, ...summary } : item
  ));
}

export function removeSeriesItem(items, removedId) {
  const current = Array.isArray(items) ? items : [];
  const removedIndex = current.findIndex((item) => item.id === removedId);
  const nextItems = current.filter((item) => item.id !== removedId);
  const nextIndex = Math.min(Math.max(removedIndex, 0), nextItems.length - 1);
  return { items: nextItems, selectedId: nextItems[nextIndex]?.id || '' };
}

export function filterSeriesItems(items, query = '', status = 'all') {
  const normalizedQuery = query.trim().toLowerCase();
  return (Array.isArray(items) ? items : []).filter((item) => {
    if (status !== 'all' && item?.status !== status) return false;
    if (!normalizedQuery) return true;
    return `${item?.name || ''} ${item?.description || ''}`.toLowerCase().includes(normalizedQuery);
  });
}

export function mergeEventPage(existing, incoming, reset = false) {
  const source = reset ? [] : (Array.isArray(existing) ? existing : []);
  const result = [...source];
  const ids = new Set(source.map((item) => item?.id));
  for (const item of Array.isArray(incoming) ? incoming : []) {
    if (!item?.id || ids.has(item.id)) continue;
    ids.add(item.id);
    result.push(item);
  }
  return result;
}
