export function filterStudyItems(items, subject = '全部', query = '') {
  const normalized = query.trim().toLowerCase();
  return (Array.isArray(items) ? items : []).filter((item) => {
    if (subject !== '全部' && item?.subject !== subject) return false;
    if (!normalized) return true;
    return `${item?.title || ''} ${item?.study_type || ''} ${item?.grade || ''}`.toLowerCase().includes(normalized);
  });
}

export function getStudyStats(items) {
  const list = Array.isArray(items) ? items : [];
  return {
    total: list.length,
    ready: list.filter((item) => item?.status === 'ready').length,
    reviewed: list.filter((item) => item?.status === 'reviewed').length,
    mistakes: list.filter((item) => item?.is_correct === 0).length,
  };
}

export function removeStudyItem(items, removedId) {
  const list = Array.isArray(items) ? items : [];
  const index = list.findIndex((item) => item.id === removedId);
  const nextItems = list.filter((item) => item.id !== removedId);
  const nextIndex = Math.min(Math.max(index, 0), nextItems.length - 1);
  return { items: nextItems, selectedId: nextItems[nextIndex]?.id || '' };
}
