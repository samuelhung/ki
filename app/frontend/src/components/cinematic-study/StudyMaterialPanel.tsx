import type { ReactNode } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { formatTimeBeijing } from '../../utils';
import {
  FORMATS,
  mdToHtml,
  type FormatTab,
  type StudyMaterial,
  type VersionTab,
} from './studyDetailFormat';

interface ReviewForm { child_answer: string; correct_answer: string; }
interface StudyMaterialPanelProps {
  material: StudyMaterial;
  embedded: boolean;
  version: VersionTab;
  format: FormatTab | null;
  generating: boolean;
  deleting: boolean;
  reviewing: boolean;
  mutationLocked: boolean;
  previewUrl: string;
  reviewOpen: boolean;
  reviewForm: ReviewForm;
  isReady: boolean;
  isTextbook: boolean;
  showTabs: boolean;
  hasLessons: boolean;
  showVersionTabs: boolean;
  lessonCount: number;
  genLabel: string;
  emptyLabel: string;
  mdSource: string;
  lessonPanel: ReactNode;
  onBack: () => void;
  onGenerate: () => void;
  onDelete: () => void;
  onReview: () => void;
  onVersionChange: (version: VersionTab) => void;
  onFormatChange: (format: FormatTab) => void;
  onReviewOpenChange: (open: boolean) => void;
  onReviewFormChange: (form: ReviewForm) => void;
}

export default function StudyMaterialPanel(props: StudyMaterialPanelProps) {
  const {
    material, embedded, version, format, generating, deleting, reviewing, mutationLocked, previewUrl,
    reviewOpen, reviewForm, isReady, isTextbook, showTabs, hasLessons, showVersionTabs,
    lessonCount, genLabel, emptyLabel, mdSource, lessonPanel,
  } = props;
  return <div className={`${embedded ? 'study-detail-legacy-embedded is-ready' : 'flex-1 bg-[#0B0C10]'} text-white flex flex-col h-full overflow-hidden`}>
    <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
      <div className="max-w-[1080px] mx-auto">
        <button onClick={props.onBack} className="study-detail-back flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 mb-3 transition-colors">
          <ArrowLeft size={14} /> 辅导中心
        </button>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#1A1B20] border border-[#2A2B30] flex items-center justify-center text-lg font-medium shrink-0">
                {material.subject === '语文' ? '语' : material.subject === '数学' ? '数' : 'E'}
              </div>
              <div className="min-w-0">
                <h1 className="text-xl font-bold truncate">{material.title}</h1>
                <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-500">
                  <span className={`px-1.5 py-0.5 rounded ${material.subject === '语文' ? 'text-blue-400 bg-blue-500/10' : material.subject === '数学' ? 'text-amber-400 bg-amber-500/10' : 'text-emerald-400 bg-emerald-500/10'}`}>{material.subject}</span>
                  <span>{material.study_type}</span>
                  {material.grade && <span>{material.grade}</span>}
                  {hasLessons && <span className="text-amber-400">{lessonCount} 课</span>}
                  <span>{formatTimeBeijing(material.created_at)}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={props.onGenerate} disabled={mutationLocked} className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors flex items-center gap-1.5 disabled:opacity-50">
              {generating ? <Loader2 size={14} className="animate-spin" /> : isReady ? <RefreshCw size={14} /> : <Sparkles size={14} />}
              <span className="hidden sm:inline">{isReady ? '重新生成' : genLabel}</span>
            </button>
            <button onClick={props.onDelete} disabled={mutationLocked} className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20 transition-colors flex items-center gap-1.5 disabled:opacity-50">
              {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}<span className="hidden sm:inline">删除</span>
            </button>
          </div>
        </div>

        {showVersionTabs && <div className="border-b border-[#2A2B30] mb-3">
          <div className="flex gap-6">
            {([['child', '👦 孩子版'], ['parent', '👨‍🏫 家长版']] as [VersionTab, string][]).map(([versionId, label]) => <button key={versionId} onClick={() => props.onVersionChange(versionId)} className={`pb-3 text-xs font-medium transition-colors relative ${version === versionId ? 'text-amber-400' : 'text-gray-500 hover:text-gray-300'}`}>
              {label}
              {version === versionId && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-500" />}
            </button>)}
          </div>
        </div>}

        {!isTextbook && <section className="study-review-strip">
          <button onClick={() => props.onReviewOpenChange(!reviewOpen)} className="study-review-trigger">
            <CheckCircle2 size={14} /><span>{material.status === 'reviewed' ? '更新错题复盘' : '错题复盘'}</span>
            {material.mistake_tags?.slice(0, 3).map((tag) => <em key={tag}>{tag}</em>)}
          </button>
          {reviewOpen && <div className="study-review-form">
            <label><span>孩子答案</span><textarea value={reviewForm.child_answer} onChange={(event) => props.onReviewFormChange({ ...reviewForm, child_answer: event.target.value })} /></label>
            <label><span>正确答案</span><textarea value={reviewForm.correct_answer} onChange={(event) => props.onReviewFormChange({ ...reviewForm, correct_answer: event.target.value })} /></label>
            <button onClick={props.onReview} disabled={mutationLocked || !reviewForm.child_answer.trim() || !reviewForm.correct_answer.trim()}>{reviewing ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}生成复盘</button>
          </div>}
        </section>}

        {showTabs && <div className="border-b border-[#2A2B30]">
          <div className="flex gap-4">
            {FORMATS.filter((item) => {
              if (item.id === 'original') return isTextbook && material.source_type === 'pdf';
              if (item.id === 'lessons') return hasLessons;
              return isReady;
            }).map((item) => <button key={item.id} onClick={() => props.onFormatChange(item.id)} className={`inline-flex items-center gap-1.5 pb-3 text-xs font-medium transition-colors relative ${format === item.id ? 'text-amber-400' : 'text-gray-500 hover:text-gray-300'}`}>
              {item.icon}{item.label}
              {format === item.id && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-500" />}
            </button>)}
          </div>
        </div>}
      </div>
    </div>

    <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
      <div className="max-w-[1080px] mx-auto pt-4">
        {!showTabs ? <div className="text-center text-gray-600 py-16">
          <Sparkles size={48} className="mx-auto mb-4 opacity-40" />
          <p className="text-sm">{emptyLabel}</p>
          <p className="text-xs mt-1 text-gray-700">点击上方「{genLabel}」开始 AI 生成</p>
        </div> : format === 'lessons' ? lessonPanel : <>
          {format === 'md' && <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-6" dangerouslySetInnerHTML={{ __html: mdToHtml(mdSource || '加载中...') }} />}
          {(format === 'html' || format === 'pdf' || format === 'original') && <div className="study-preview-frame bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden" style={{ height: 'calc(100vh - 220px)' }}>
            {previewUrl ? <iframe src={previewUrl} className="w-full h-full border-0" title={`${format} Preview`} sandbox={format === 'html' ? 'allow-same-origin' : undefined} /> : <div className="grid h-full place-items-center text-xs text-gray-500"><Loader2 size={18} className="animate-spin" /></div>}
          </div>}
        </>}
      </div>
    </div>
  </div>;
}
