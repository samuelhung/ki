import { useEffect, useRef, useState, type CSSProperties } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  ListChecks,
  Loader2,
  RefreshCw,
  RotateCcw,
  Trash2,
  X,
} from 'lucide-react';
import type { QueueItem } from '../components/cinematic-ingest/ingestTypes';
import { queueProgressStages, stageLabel } from '../components/cinematic-ingest/ingestUtils';
import { useIngestQueue } from '../components/cinematic-ingest/useIngestQueue';
import KiMagicBentoFrame from '../components/react-bits/KiMagicBentoFrame';
import { formatTimeBeijing } from '../utils';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import './GlobalDockQueueOverlay.css';

const STATUS_META: Record<QueueItem['status'], { label: string; icon: typeof Clock3 }> = {
  running: { label: '运行中', icon: Loader2 },
  pending: { label: '等待中', icon: Clock3 },
  error: { label: '异常', icon: AlertTriangle },
  done: { label: '已完成', icon: CheckCircle2 },
};

function QueueProgressTrack({ item }: { item: QueueItem }) {
  const stages = queueProgressStages(item);
  const current = stages.find((stage) => stage.status === 'active' || stage.status === 'error');
  const currentStageRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = currentStageRef.current;
    if (!node || !window.matchMedia('(max-width: 760px)').matches) return;
    node.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }, [current?.key, current?.status]);

  if (stages.length === 0) return null;

  const currentLabel = current ? `${current.label}，${stageLabel(current.status)}` : '等待更新';

  return (
    <div
      className="global-dock-queue-progress"
      aria-label={currentLabel}
      tabIndex={0}
      style={{ '--queue-progress-stage-count': stages.length } as CSSProperties}
    >
      {stages.map((stage, index) => {
        const label = stage.label;
        const statusLabel = stageLabel(stage.status);
        const isCurrent = current === stage;
        return (
          <div
            key={`${stage.key}-${index}`}
            className={`is-${stage.status}${isCurrent ? ' is-current' : ''}`}
            ref={isCurrent ? currentStageRef : undefined}
            title={`${label} · ${statusLabel}`}
            aria-label={`${label}，${statusLabel}`}
          >
            <b>{label}</b>
            <small>{statusLabel}</small>
          </div>
        );
      })}
    </div>
  );
}

export default function GlobalDockQueueOverlay({ action, onClose }: { action: DualNavigationActionItem; onClose: () => void }) {
  const [notice, setNotice] = useState<{ text: string; type: 'success' | 'info' } | null>(null);
  const { queueItems, queueStatusCounts, loadQueue, retryQueueTask, deleteQueueTask } = useIngestQueue({ setToast: setNotice });

  return (
    <div className="dual-nav-action-backdrop global-dock-backdrop global-dock-queue-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="global-dock-queue-stage">
        <KiMagicBentoFrame className="global-dock-queue-frame" cardClassName="global-dock-queue-card">
          <section className="global-dock-queue-dialog" role="dialog" aria-modal="true" aria-label={action.text}>
            <button className="global-dock-queue-close" type="button" aria-label="关闭" onClick={onClose} data-bento-suspend><X /></button>

            <header className="global-dock-queue-header">
              <span>{action.code}</span>
              <div><ListChecks /><h2>{action.text}</h2></div>
              <p>{action.description}</p>
            </header>

            <div className="global-dock-queue-metrics" aria-label="队列状态摘要">
              <div className="is-running"><Loader2 /><span>运行</span><strong>{queueStatusCounts.running}</strong></div>
              <div className="is-pending"><Clock3 /><span>排队</span><strong>{queueStatusCounts.pending}</strong></div>
              <div className="is-error"><AlertTriangle /><span>异常</span><strong>{queueStatusCounts.error}</strong></div>
              <div className="is-done"><CheckCircle2 /><span>完成</span><strong>{queueStatusCounts.done}</strong></div>
            </div>

            <div className="global-dock-queue-toolbar">
              <span>PROCESS TRACK / {queueItems.length}</span>
              <button type="button" onClick={() => void loadQueue()} data-bento-suspend><RefreshCw />刷新</button>
            </div>

            <div className="global-dock-queue-list">
              {queueItems.map((item) => {
                const status = STATUS_META[item.status];
                const StatusIcon = status.icon;
                const title = item.title || item.ingest_type || '处理任务';
                return (
                  <article key={item.id} className={`is-${item.status}`}>
                    <StatusIcon className={item.status === 'running' ? 'animate-spin' : ''} />
                    <span className="global-dock-queue-task">
                      <b>{title}</b>
                      <small>{item.error || status.label}</small>
                    </span>
                    <em>{formatTimeBeijing(item.created_at) || '--'}</em>
                    <span className="global-dock-queue-state">{status.label}</span>
                    <div className="global-dock-queue-actions">
                      {item.status === 'error' && (
                        <button type="button" onClick={() => void retryQueueTask(item.id)} aria-label={`重试 ${title}`} title="重试" data-bento-suspend><RotateCcw /></button>
                      )}
                      <button type="button" onClick={() => void deleteQueueTask(item.id)} aria-label={`删除 ${title}`} title="删除" data-bento-suspend><Trash2 /></button>
                    </div>
                    <QueueProgressTrack item={item} />
                  </article>
                );
              })}

              {queueItems.length === 0 && (
                <div className="global-dock-queue-empty"><ListChecks /><b>当前没有处理任务</b><span>新的接入内容会自动出现在这里</span></div>
              )}
            </div>

            {notice && <p className={`global-dock-queue-notice is-${notice.type}`} role="status">{notice.text}</p>}
          </section>
        </KiMagicBentoFrame>
      </div>
    </div>
  );
}
