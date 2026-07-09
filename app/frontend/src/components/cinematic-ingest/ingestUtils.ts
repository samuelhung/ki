import type { ProgressStage, QueueItem, QueueStatusCounts } from './ingestTypes';
import { ingestCopy } from './ingestCopy';

export const EVENT_BATCH_SIZE = 20;
export const EVENT_WINDOW_LIMIT = 50;
export const TITLE_DISPLAY_LIMIT = 18;
export const QUEUE_DELETE_TOMBSTONE_TTL_MS = 60_000;
export const INDEX_ROW_PITCH = 37;
export const INDEX_DEPTH_OVERSCAN_ROWS = 3;

export function taskTypeLabel(ingestType: string): string {
  switch (ingestType) {
    case 'douyin_share': return '抖音分享';
    case 'video_file': return '视频文件';
    case 'audio_file': return '音频文件';
    case 'document': return '文档';
    default: return ingestType;
  }
}

export function taskTitle(task: QueueItem): string {
  if (task.title && task.title !== '待处理') return task.title;
  try {
    if (task.payload_json) {
      const payload = JSON.parse(task.payload_json);
      if (payload.content_text) {
        return payload.content_text.slice(0, 50) + (payload.content_text.length > 50 ? '...' : '');
      }
      if (payload.title) return payload.title;
      if (payload.filename) return payload.filename;
    }
  } catch (_) {
    // Keep queue rendering resilient if a legacy payload is malformed.
  }
  return taskTypeLabel(task.ingest_type);
}

export function compactIndexTitle(title: string): string {
  const chars = Array.from(title || '');
  if (chars.length <= TITLE_DISPLAY_LIMIT) return title;
  return `${chars.slice(0, TITLE_DISPLAY_LIMIT).join('')}...`;
}

export function sourceToneClass(sourceId: string): string {
  if (sourceId === 'douyin') return 'is-douyin';
  if (sourceId === 'user-upload') return 'is-upload';
  if (sourceId === 'user-concept') return 'is-concept';
  return 'is-source';
}

export function topicToneClass(topic: string): string {
  if (topic === '格局') return 'is-blue';
  if (topic === '财富') return 'is-gold';
  if (topic === '认知') return 'is-violet';
  if (topic === '前瞻') return 'is-cyan';
  return 'is-neutral';
}

export function stageLabel(status: ProgressStage['status']) {
  if (status === 'done') return '完成';
  if (status === 'active') return '运行';
  if (status === 'error') return '异常';
  return ingestCopy.queue.waiting;
}

export function visibleProgressStages(stages: ProgressStage[]): Array<ProgressStage & { isCurrent: boolean }> {
  if (stages.length === 0) return [];
  const activeIndex = stages.findIndex((stage) => stage.status === 'active' || stage.status === 'error');
  const nextIndex = stages.findIndex((stage) => stage.status !== 'done');
  const currentIndex = activeIndex >= 0 ? activeIndex : (nextIndex >= 0 ? nextIndex : stages.length - 1);
  const start = Math.max(0, currentIndex - 1);
  const end = Math.min(stages.length, currentIndex + 3);

  return stages.slice(start, end).map((stage, offset) => ({
    ...stage,
    isCurrent: start + offset === currentIndex,
  }));
}

export function processingTrackHint(
  running: QueueItem | null | undefined,
  pendingCount: number,
  errorCount: number,
): string {
  const stages = running?.progress_stages || [];
  const currentStage = stages.find((stage) => stage.status === 'active' || stage.status === 'error')
    || stages.find((stage) => stage.status !== 'done');

  if (currentStage?.status === 'error') return `${currentStage.label}失败 · 等待重试或清理`;
  if (running && currentStage) return `正在${currentStage.label} · ${visibleProgressStages(stages).length ? '局部流程同步推进' : '处理链路同步推进'}`;
  if (running) return '正在接入处理链路 · 节点状态回传中';
  if (errorCount > 0) return `${errorCount} 个异常任务 · 可重试或删除`;
  if (pendingCount > 0) return `${pendingCount} 个任务排队 · 等待资源调度`;
  return '无活动任务 · 处理轨道待命';
}

export function visibleIndexDepthRange(
  itemCount: number,
  scrollTop: number,
  viewportHeight: number,
  rowPitch = INDEX_ROW_PITCH,
  overscanRows = INDEX_DEPTH_OVERSCAN_ROWS,
): [number, number] {
  if (itemCount <= 0) return [0, -1];
  const first = Math.max(0, Math.floor(scrollTop / rowPitch) - overscanRows);
  const last = Math.min(itemCount - 1, Math.ceil((scrollTop + viewportHeight) / rowPitch) + overscanRows);
  return [first, last];
}

export function queueSignature(items: QueueItem[]): string {
  return items
    .map((item) => `${item.id}:${item.status}:${item.title || ''}:${item.error || ''}:${item.progress_stages?.map((stage) => `${stage.key}-${stage.status}`).join(',') || ''}`)
    .join('|');
}

export function queueCountsSignature(counts: QueueStatusCounts): string {
  return `${counts.pending}:${counts.running}:${counts.done}:${counts.error}`;
}

export function normalizeQueueStatusCounts(counts: Partial<QueueStatusCounts> | undefined): QueueStatusCounts {
  return {
    pending: Number(counts?.pending || 0),
    running: Number(counts?.running || 0),
    done: Number(counts?.done || 0),
    error: Number(counts?.error || 0),
  };
}

export function applyDeletedQueueCounts(
  counts: QueueStatusCounts,
  rawItems: QueueItem[],
  deletedTasks: Map<string, { status: QueueItem['status'] }>,
): QueueStatusCounts {
  const next = { ...counts };
  const rawItemIds = new Set(rawItems.map((item) => item.id));
  deletedTasks.forEach((task, taskId) => {
    if (!rawItemIds.has(taskId)) return;
    next[task.status] = Math.max(0, next[task.status] - 1);
  });
  return next;
}
