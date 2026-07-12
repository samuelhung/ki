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
