import { Fragment, useMemo, useRef } from 'react';
import { Check, Loader2, RefreshCw, WandSparkles } from 'lucide-react';
import type { SegmentationTaskSnapshot } from '../../pages/EventDetailPage';
import { alignTranscriptGaps, type TranscriptGapAlignment } from './transcriptDiff';

interface TranscriptComparisonPanelProps {
  canSegment: boolean;
  source: string;
  task: SegmentationTaskSnapshot | null;
  segmenting: boolean;
  confirming: boolean;
  error: string;
  onStart: () => void;
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

export function TranscriptComparisonPanel({
  canSegment,
  source,
  task,
  segmenting,
  confirming,
  error,
  onStart,
  onRegenerate,
  onConfirm,
}: TranscriptComparisonPanelProps) {
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

  const status = task?.status;
  const taskError = task?.error_code ? failureCopy[task.error_code] || 'AI 分段失败，请重新生成。' : '';
  return <>
    <div className="transcript-comparison-content">
      {!task && canSegment && <div className="transcript-dialog-state transcript-segment-idle">
        <WandSparkles size={22} />
        <strong>按语义整理标点与段落</strong>
        <span>不会修改任何正文字符，生成后需人工确认。</span>
        <button type="button" className="is-primary" onClick={onStart} disabled={segmenting}>
          {segmenting ? <Loader2 size={14} className="animate-spin" /> : <WandSparkles size={14} />}
          开始语义分段
        </button>
      </div>}
      {!task && !canSegment && <div className="transcript-dialog-state">
        <strong>请先完成人工修正并保存</strong>
        <span>人工确认文字准确后，才能进行 AI 语义分段。</span>
      </div>}
      {status === 'processing' && <div className="transcript-dialog-state">
        <Loader2 size={22} className="animate-spin" />
        <strong>正在按语义调整标点与段落</strong>
        <span>已处理 {task?.completed_chunks || 0}/{task?.total_chunks || 0} 段</span>
      </div>}
      {status === 'failed' && <div className="transcript-dialog-state is-error">
        <strong>本次分段未生成可用结果</strong><span>{taskError}</span>
      </div>}
      {status === 'confirmed' && <div className="transcript-dialog-state">
        <Check size={22} />
        <strong>AI 分段版本已确认使用</strong>
        <span>该版本已加入修订记录。</span>
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
    <footer className="transcript-workspace-footer">
      <span>仅允许调整 Unicode 标点、空格和换行，正文字符保持不变。</span>
      <div>
        {(status === 'failed' || status === 'ready' || status === 'confirmed') && <button type="button"
          onClick={onRegenerate} disabled={segmenting || confirming || !canSegment}>
          {segmenting ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}重新生成
        </button>}
        {status === 'ready' && alignment && <button type="button" className="is-primary" onClick={onConfirm} disabled={confirming}>
          {confirming ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}确认使用
        </button>}
      </div>
    </footer>
  </>;
}
