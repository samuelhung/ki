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
