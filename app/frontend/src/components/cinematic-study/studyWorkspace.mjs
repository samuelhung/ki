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

export function buildStudyCreatePayload(form = {}) {
  return {
    subject: form.subject || '语文',
    study_type: form.category === '单项训练' ? (form.type || '') : (form.category || ''),
    title: (form.title || '').trim() || '未命名',
    raw_content: (form.raw_content || '').trim(),
    grade: form.grade || '',
    textbook: form.textbook || '',
  };
}

export function buildStudyUploadFields(form = {}) {
  return {
    category: form.category || '单项训练',
    subject: form.subject || '语文',
    study_type: form.type || '',
    grade: form.grade || '',
    title: (form.title || '').trim(),
  };
}

export function mergeStudyReview(material, result = {}) {
  return {
    ...material,
    ...result,
    status: 'reviewed',
    is_correct: result.is_correct ?? material?.is_correct ?? 0,
    mistake_tags: Array.isArray(result.mistake_tags) ? result.mistake_tags : (material?.mistake_tags || []),
  };
}

export function createStudyDetailCache(limit = 12) {
  const entries = new Map();
  return {
    get(id) {
      const value = entries.get(id);
      if (value === undefined) return undefined;
      entries.delete(id);
      entries.set(id, value);
      return value;
    },
    set(id, value) {
      entries.delete(id);
      entries.set(id, value);
      while (entries.size > limit) entries.delete(entries.keys().next().value);
    },
    delete(id) { entries.delete(id); },
    clear() { entries.clear(); },
  };
}
