export function filterTasks(tasks, filters = {}) {
  const query = (filters.query || '').trim().toLowerCase();
  return tasks.filter((task) => {
    if (filters.status && filters.status !== 'all' && task.status !== filters.status) return false;
    if (filters.source && filters.source !== 'all' && task.source !== filters.source) return false;
    if (filters.priority && filters.priority !== 'all' && task.priority !== filters.priority) return false;
    if (!query) return true;
    return `${task.title || ''} ${task.description || ''} ${task.source_label || ''}`.toLowerCase().includes(query);
  });
}

export function getTaskStats(tasks, today = new Date().toISOString().slice(0, 10)) {
  return tasks.reduce((stats, task) => {
    stats.total += 1;
    if (task.status === 'todo') stats.todo += 1;
    if (task.status === 'in_progress') stats.inProgress += 1;
    if (task.status === 'done') stats.done += 1;
    if (task.status !== 'done' && task.due_date && task.due_date < today) stats.overdue += 1;
    return stats;
  }, { total: 0, todo: 0, inProgress: 0, done: 0, overdue: 0 });
}

export function mergeTaskSnapshot(localTasks, remoteTasks, deletedIds = new Set(), dirtyIds = new Set()) {
  const localById = new Map(localTasks.map((task) => [task.id, task]));
  return remoteTasks
    .filter((task) => !deletedIds.has(task.id))
    .map((task) => dirtyIds.has(task.id) && localById.has(task.id) ? localById.get(task.id) : task);
}

export function removeTask(tasks, removedId, selectedId) {
  const index = tasks.findIndex((task) => task.id === removedId);
  const nextTasks = tasks.filter((task) => task.id !== removedId);
  if (selectedId !== removedId) return { tasks: nextTasks, selectedId };
  return { tasks: nextTasks, selectedId: nextTasks[Math.min(index, nextTasks.length - 1)]?.id || '' };
}

export function resolveSelectedTask(visibleTasks, selectedId) {
  return visibleTasks.find((task) => task.id === selectedId) || visibleTasks[0] || null;
}

export function taskTiming(task, today = new Date().toISOString().slice(0, 10)) {
  if (task.status === 'done') return { tone: 'done', label: '已完成' };
  if (!task.due_date) return { tone: 'neutral', label: '无截止日' };
  const dayMs = 24 * 60 * 60 * 1000;
  const difference = Math.round((Date.parse(`${task.due_date}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / dayMs);
  if (difference < 0) return { tone: 'overdue', label: `逾期 ${Math.abs(difference)} 天` };
  if (difference === 0) return { tone: 'today', label: '今日到期' };
  return { tone: 'upcoming', label: `${difference} 天后到期` };
}
