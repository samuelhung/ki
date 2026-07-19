async function responseError(response, fallback) {
  try {
    const payload = await response.json();
    return payload?.detail || payload?.message || fallback;
  } catch {
    return fallback;
  }
}

export async function fetchBriefingHistory({ apiFetch, signal }) {
  const response = await apiFetch('/api/briefing?limit=30&offset=0', { signal });
  if (!response.ok) throw new Error(await responseError(response, '快报历史加载失败'));
  const payload = await response.json();
  const items = (Array.isArray(payload?.items) ? payload.items : [])
    .filter((item) => item && typeof item.id === 'string' && item.id)
    .sort((left, right) => {
      const timeOrder = String(right.created_at || '').localeCompare(String(left.created_at || ''));
      return timeOrder || right.id.localeCompare(left.id);
    });
  return {
    items,
    total: Number.isFinite(payload?.total) ? payload.total : items.length,
  };
}

export async function fetchBriefingDetail({ apiFetch, signal, briefingId }) {
  const response = await apiFetch(`/api/briefing/${briefingId}`, { signal });
  if (!response.ok) throw new Error(await responseError(response, '快报详情加载失败'));
  return response.json();
}

export async function generateQuickBriefing({ apiFetch, signal }) {
  const response = await apiFetch('/api/briefing/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'quick' }),
    signal,
  });
  if (!response.ok) throw new Error(await responseError(response, '即时快报生成失败'));
  const payload = await response.json();
  if (typeof payload?.id !== 'string' || !payload.id.trim()) {
    throw new Error('生成结果缺少有效快报 ID');
  }
  return { ...payload, id: payload.id.trim() };
}
