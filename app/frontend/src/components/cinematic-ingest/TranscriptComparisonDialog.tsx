import { Fragment, useMemo, useRef } from 'react';
import { Check, Loader2, RefreshCw, X } from 'lucide-react';
import type { SegmentationTaskSnapshot } from '../../pages/EventDetailPage';
import { alignTranscriptGaps, type TranscriptGapAlignment } from './transcriptDiff';

interface TranscriptComparisonDialogProps {
  open: boolean;
  source: string;
  task: SegmentationTaskSnapshot | null;
  confirming: boolean;
  error: string;
  onClose: () => void;
  onRegenerate: () => void;
  onConfirm: () => void;
}

const failureCopy: Record<string, string> = {
  body_character_mismatch: 'AI 结果修改了正文字符，已拒绝使用。',
  empty_output: 'AI 未返回可用结果，请重新生成。',
  task_expired: '分段结果已过期，请重新生成。',
};

function GapAlignedText({ alignment, side }: {
  alignment: TranscriptGapAlignment;
  side: 'before' | 'after';
}) {
  const gaps = side === 'before' ? alignment.beforeGaps : alignment.afterGaps;
  const changed = new Set(alignment.changes.map((change) => change.index));
  return <>{gaps.map((gap, index) => <Fragment key={`${side}-${index}`}>
    {gap && <mark className={changed.has(index) ? 'is-changed' : ''}>{gap}</mark>}
    {index < alignment.body.length && alignment.body[index]}
  </Fragment>)}</>;
}

export function TranscriptComparisonDialog({
  open,
  source,
  task,
  confirming,
  error,
  onClose,
  onRegenerate,
  onConfirm,
}: TranscriptComparisonDialogProps) {
  const beforeRef = useRef<HTMLDivElement>(null);
  const afterRef = useRef<HTMLDivElement>(null);
  const syncingScroll = useRef(false);
  const alignment = useMemo(() => {
    if (!task?.preview) return null;
    try {
      return alignTranscriptGaps(source, task.preview);
    } catch {
      return null;
    }
  }, [source, task?.preview]);

  function syncScroll(sourcePane: HTMLDivElement, targetPane: HTMLDivElement | null) {
    if (!targetPane || syncingScroll.current) return;
    const sourceRange = sourcePane.scrollHeight - sourcePane.clientHeight;
    const targetRange = targetPane.scrollHeight - targetPane.clientHeight;
    syncingScroll.current = true;
    targetPane.scrollTop = sourceRange > 0 ? (sourcePane.scrollTop / sourceRange) * targetRange : 0;
    requestAnimationFrame(() => { syncingScroll.current = false; });
  }

  if (!open) return null;
  const status = task?.status || 'processing';
  const taskError = task?.error_code ? failureCopy[task.error_code] || 'AI 分段失败，请重新生成。' : '';
  return <div className="transcript-dialog-backdrop">
    <section className="transcript-dialog transcript-comparison-dialog" role="dialog" aria-modal="true" aria-labelledby="transcript-comparison-title">
      <header>
        <div><span>SEMANTIC SEGMENTATION</span><h2 id="transcript-comparison-title">AI 分段预览</h2></div>
        <button type="button" className="transcript-dialog-close" onClick={onClose} disabled={confirming} aria-label="关闭">
          <X size={18} />
        </button>
      </header>
      <div className="transcript-dialog-body">
        {status === 'processing' && <div className="transcript-dialog-state">
          <Loader2 size={22} className="animate-spin" />
          <strong>正在按语义调整标点与段落</strong>
          <span>已处理 {task?.completed_chunks || 0}/{task?.total_chunks || 0} 段</span>
        </div>}
        {status === 'failed' && <div className="transcript-dialog-state is-error">
          <strong>本次分段未生成可用结果</strong><span>{taskError}</span>
        </div>}
        {status === 'ready' && alignment && <div className="transcript-comparison-grid">
          <section><h3>人工修正版</h3><div ref={beforeRef} className="transcript-comparison-pane custom-scrollbar"
            onScroll={(event) => syncScroll(event.currentTarget, afterRef.current)}>
            <GapAlignedText alignment={alignment} side="before" />
          </div></section>
          <section><h3>AI 分段预览</h3><div ref={afterRef} className="transcript-comparison-pane custom-scrollbar"
            onScroll={(event) => syncScroll(event.currentTarget, beforeRef.current)}>
            <GapAlignedText alignment={alignment} side="after" />
          </div></section>
        </div>}
        {status === 'ready' && !alignment && <div className="transcript-dialog-state is-error">
          <strong>分段结果校验失败</strong><span>正文字符不一致，已禁止确认使用。</span>
        </div>}
        {error && <p className="transcript-dialog-error">{error}</p>}
      </div>
      <footer>
        <span>仅允许调整 Unicode 标点、空格和换行，正文字符保持不变。</span>
        <div>
          <button type="button" onClick={onClose} disabled={confirming}>取消</button>
          {(status === 'failed' || status === 'ready') && <button type="button" onClick={onRegenerate} disabled={confirming}>
            <RefreshCw size={14} />重新生成
          </button>}
          {status === 'ready' && alignment && <button type="button" className="is-primary" onClick={onConfirm} disabled={confirming}>
            {confirming ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}确认使用
          </button>}
        </div>
      </footer>
    </section>
  </div>;
}
