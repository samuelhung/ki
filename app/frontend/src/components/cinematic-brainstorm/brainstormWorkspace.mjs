export function linkedEventCount(item) {
  try {
    const ids = JSON.parse(item?.answered_event_ids || '[]');
    return Array.isArray(ids) ? ids.length : 0;
  } catch { return 0; }
}

export function filterBrainstormQuestions(items, topic = '全部', query = '') {
  const normalized = query.trim().toLowerCase();
  return (Array.isArray(items) ? items : []).filter((item) => {
    if (topic !== '全部' && item.topic !== topic) return false;
    return !normalized || (item.question || '').toLowerCase().includes(normalized);
  });
}

export function getBrainstormStats(items) {
  const list = Array.isArray(items) ? items : [];
  return {
    total: list.length,
    open: list.filter((item) => item.status !== 'done').length,
    done: list.filter((item) => item.status === 'done').length,
    linked: list.reduce((sum, item) => sum + linkedEventCount(item), 0),
  };
}

export function removeBrainstormQuestion(items, removedId) {
  const list = Array.isArray(items) ? items : [];
  const index = list.findIndex((item) => item.id === removedId);
  const nextItems = list.filter((item) => item.id !== removedId);
  return { items: nextItems, selectedId: nextItems[Math.min(Math.max(index, 0), nextItems.length - 1)]?.id || '' };
}
