import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import type { DeletedQueueTask, QueueItem, QueueStatusCounts } from './ingestTypes';
import {
  applyDeletedQueueCounts,
  normalizeQueueStatusCounts,
  QUEUE_DELETE_TOMBSTONE_TTL_MS,
  queueCountsSignature,
  queueSignature,
} from './ingestUtils';

type ToastMessage = { text: string; type: 'success' | 'info' };

interface UseIngestQueueOptions {
  setToast: (toast: ToastMessage) => void;
}

export function useIngestQueue({ setToast }: UseIngestQueueOptions) {
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const [queueStatusCounts, setQueueStatusCounts] = useState<QueueStatusCounts>({
    pending: 0,
    running: 0,
    done: 0,
    error: 0,
  });
  const queueSignatureRef = useRef('');
  const queueCountsSignatureRef = useRef('');
  const queueItemsRef = useRef<QueueItem[]>([]);
  const queueStatusCountsRef = useRef<QueueStatusCounts>({
    pending: 0,
    running: 0,
    done: 0,
    error: 0,
  });
  const deletedQueueTaskIdsRef = useRef<Map<string, DeletedQueueTask>>(new Map());

  const queueGroups = useMemo(() => {
    const runningItem = queueItems.find((item) => item.status === 'running');
    const pendingItems = queueItems.filter((item) => item.status === 'pending');
    const errorItems = queueItems.filter((item) => item.status === 'error');
    const doneItems = queueItems.filter((item) => item.status === 'done');
    const visibleItems = [
      ...(runningItem ? [runningItem] : []),
      ...errorItems,
      ...pendingItems,
    ].slice(0, 5);

    return {
      running: runningItem,
      pending: pendingItems,
      errors: errorItems,
      done: doneItems,
      visibleQueueItems: visibleItems,
      recentDoneItems: doneItems.slice(0, 3),
    };
  }, [queueItems]);

  const queueVisible = queueStatusCounts.running + queueStatusCounts.pending + queueStatusCounts.error > 0;
  const queueStats = useMemo(() => [
    { label: '活跃', value: queueStatusCounts.pending + queueStatusCounts.error + queueStatusCounts.running },
    { label: '排队', value: queueStatusCounts.pending },
    { label: '异常', value: queueStatusCounts.error },
  ], [queueStatusCounts]);

  const loadQueue = useCallback(async () => {
    try {
      const response = await apiFetch('/api/ingest/queue?limit=30');
      const data = await response.json();
      const rawItems: QueueItem[] = data.items || [];
      const now = Date.now();
      deletedQueueTaskIdsRef.current.forEach((task, taskId) => {
        if (now - task.deletedAt > QUEUE_DELETE_TOMBSTONE_TTL_MS) {
          deletedQueueTaskIdsRef.current.delete(taskId);
        }
      });
      const nextItems = rawItems.filter((item) => !deletedQueueTaskIdsRef.current.has(item.id));
      const nextCounts = applyDeletedQueueCounts(
        normalizeQueueStatusCounts(data.status_counts),
        rawItems,
        deletedQueueTaskIdsRef.current,
      );
      const nextSignature = queueSignature(nextItems);
      const nextCountsSignature = queueCountsSignature(nextCounts);
      queueItemsRef.current = nextItems;
      queueStatusCountsRef.current = nextCounts;
      if (nextSignature !== queueSignatureRef.current) {
        queueSignatureRef.current = nextSignature;
        setQueueItems(nextItems);
      }
      if (nextCountsSignature !== queueCountsSignatureRef.current) {
        queueCountsSignatureRef.current = nextCountsSignature;
        setQueueStatusCounts(nextCounts);
      }
    } catch (_) {
      // Queue should not blank the whole console.
    }
  }, []);

  const retryQueueTask = useCallback(async (taskId: string) => {
    try {
      await apiFetch(`/api/ingest/queue/${taskId}/retry`, { method: 'POST' });
      loadQueue();
    } catch (_) {
      setToast({ text: '重试失败', type: 'info' });
    }
  }, [loadQueue, setToast]);

  const deleteQueueTask = useCallback(async (taskId: string) => {
    const deletedTask = queueItemsRef.current.find((item) => item.id === taskId);
    const deletedStatus = deletedTask?.status || 'error';
    deletedQueueTaskIdsRef.current.set(taskId, { deletedAt: Date.now(), status: deletedStatus });
    setQueueItems((prev) => {
      const nextItems = prev.filter((item) => item.id !== taskId);
      queueItemsRef.current = nextItems;
      queueSignatureRef.current = queueSignature(nextItems);
      return nextItems;
    });
    setQueueStatusCounts((prev) => {
      const nextCounts = { ...prev, [deletedStatus]: Math.max(0, prev[deletedStatus] - 1) };
      queueStatusCountsRef.current = nextCounts;
      queueCountsSignatureRef.current = queueCountsSignature(nextCounts);
      return nextCounts;
    });

    try {
      const response = await apiFetch(`/api/ingest/queue/${taskId}`, { method: 'DELETE' });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || '删除队列任务失败');
      }
    } catch (_) {
      deletedQueueTaskIdsRef.current.delete(taskId);
      loadQueue();
      setToast({ text: '删除队列任务失败', type: 'info' });
    }
  }, [loadQueue, setToast]);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;

    const schedule = () => {
      if (cancelled) return;
      if (document.hidden) {
        timer = window.setTimeout(schedule, 10000);
        return;
      }
      const counts = queueStatusCountsRef.current;
      const hasActiveQueue = counts.running + counts.pending + counts.error > 0;
      timer = window.setTimeout(async () => {
        await loadQueue();
        schedule();
      }, hasActiveQueue ? 3000 : 12000);
    };

    const handleVisibility = () => {
      window.clearTimeout(timer);
      if (!document.hidden) loadQueue();
      schedule();
    };

    loadQueue().finally(schedule);
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [loadQueue]);

  return {
    queueItems,
    queueStatusCounts,
    ...queueGroups,
    queueVisible,
    queueStats,
    loadQueue,
    retryQueueTask,
    deleteQueueTask,
  };
}
