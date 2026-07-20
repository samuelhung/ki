import type { Task } from '../TaskViews';

interface TaskFilters {
  status?: string;
  source?: string;
  priority?: string;
  query?: string;
}

export function filterTasks(tasks: Task[], filters?: TaskFilters): Task[];
export function getTaskStats(tasks: Task[], today?: string): { total: number; todo: number; inProgress: number; done: number; overdue: number };
export function mergeTaskSnapshot(localTasks: Task[], remoteTasks: Task[], deletedIds?: Set<string>, dirtyIds?: Set<string>): Task[];
export function removeTask(tasks: Task[], removedId: string, selectedId: string): { tasks: Task[]; selectedId: string };
export function resolveSelectedTask(tasks: Task[], selectedId: string): Task | null;
export function taskTiming(task: Task, today?: string): { tone: string; label: string };
