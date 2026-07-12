export function filterLibraryEvents(events, filters = {}) {
  const query = (filters.query || '').trim().toLowerCase();
  return events.filter((event) => {
    if (filters.topic && filters.topic !== 'all' && event.topic !== filters.topic) return false;
    if (filters.status && filters.status !== 'all' && event.status !== filters.status) return false;
    if (filters.source && filters.source !== 'all' && event.source_id !== filters.source) return false;
    if (!query) return true;
    return `${event.title_cn || ''} ${event.title || ''} ${event.raw_summary || ''}`.toLowerCase().includes(query);
  });
}

export function filterSources(sources, filters = {}) {
  const query = (filters.query || '').trim().toLowerCase();
  return sources.filter((source) => {
    if (filters.state === 'enabled' && !source.enabled) return false;
    if (filters.state === 'paused' && source.enabled) return false;
    if (filters.state === 'error' && !source.last_error) return false;
    if (!query) return true;
    return `${source.name || ''} ${source.url || ''} ${source.topic || ''} ${source.type || ''}`.toLowerCase().includes(query);
  });
}

export function getLibraryStats(events) {
  return events.reduce((stats, event) => {
    stats.total += 1;
    if (['ready', 'done', 'completed', 'digest'].includes(event.status)) stats.ready += 1;
    if (event.status === 'processing') stats.processing += 1;
    if (['error', 'failed'].includes(event.status)) stats.errors += 1;
    return stats;
  }, { total: 0, ready: 0, processing: 0, errors: 0 });
}

export function getSourceStats(sources) {
  return sources.reduce((stats, source) => {
    stats.total += 1;
    if (source.enabled) stats.enabled += 1;
    else stats.paused += 1;
    if (source.last_error) stats.errors += 1;
    return stats;
  }, { total: 0, enabled: 0, paused: 0, errors: 0 });
}

export function resolveVisibleItem(items, selectedId) {
  return items.find((item) => item.id === selectedId) || items[0] || null;
}
