import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Bell, Check, Layers, ListPlus, Loader2, Plus, RefreshCw, Sparkles, Trash2 } from 'lucide-react';
import Modal from '../components/Modal';
import SeriesMemberPanel from '../components/cinematic-series/SeriesMemberPanel';
import SeriesSummaryPanel from '../components/cinematic-series/SeriesSummaryPanel';
import { getTopicColor, STATUS_LABEL } from '../components/cinematic-series/seriesDetailFormat';
import { useSeriesDetail } from '../components/cinematic-series/useSeriesDetail';
import { formatTimeBeijing } from '../utils';

export interface SeriesMember {
  id: string;
  title: string;
  overview?: string;
  url: string;
  topic: string;
  source_id: string;
  status: string;
  created_at: string;
}

export interface SeriesDetailData {
  id: string;
  name: string;
  description: string | null;
  member_ids: string;
  sort_order: string | null;
  status: string;
  intro?: string;
  summary?: string;
  paper?: string;
  created_at: string;
  updated_at?: string;
  members: SeriesMember[];
}

interface SeriesDetailProps {
  embedded?: boolean;
  seriesId?: string;
  initialSeries?: SeriesDetailData | null;
  onSeriesChange?: (series: SeriesDetailData) => void;
  onDeleted?: (seriesId: string) => void;
}

export default function SeriesDetail({ embedded = false, seriesId, initialSeries = null, onSeriesChange, onDeleted }: SeriesDetailProps) {
  const { id: routeId } = useParams<{ id: string }>();
  const id = seriesId || routeId;
  const navigate = useNavigate();
  const detail = useSeriesDetail({ id, embedded, initialSeries, navigate, onSeriesChange, onDeleted });
  const {
    series, loading, loadError, operationError, introGenerating, summaryGenerating, paperGenerating,
    deleting, confirmDelete, setConfirmDelete, panelId, tab, suggestions, showSuggestions,
    setShowSuggestions, selectedIds, batchAdding, showProgress, setShowProgress, progressStage,
    refreshing, allProcessed, suggestionsLoaded, contentRef, handleContentScroll, selectTab,
    togglePanel, handleGenerateIntro, handleGenerateSummary, handleGeneratePaper, handleDelete,
    toggleSelect, toggleSelectAll, handleBatchAdd, handleBatchDismiss, handleRefresh,
  } = detail;

  function handleRefClick(reference: number) {
    if (!series) return;
    const member = series.members[reference - 1];
    if (member) navigate(`/events/${member.id}`);
  }
  function handleOpenMember(memberId: string) { navigate(`/events/${memberId}`); }

  if (loading) {
    if (embedded) return <div className="series-detail-legacy-embedded is-loading text-white flex items-center justify-center">
      <Loader2 size={24} className="animate-spin text-gray-600" />
    </div>;
    return <div className="flex-1 bg-[#0B0C10] text-white flex items-center justify-center"><Loader2 size={24} className="animate-spin text-gray-600" /></div>;
  }
  if (loadError || !series) {
    return <div className={`${embedded ? 'series-detail-legacy-embedded is-error' : 'flex-1 bg-[#0B0C10] p-8'} text-white`}>
      <div className="max-w-[1080px] mx-auto py-16 text-center">
        <p className="text-sm text-red-400">{loadError || '专题不存在'}</p>
        <button onClick={() => navigate('/series')} className="mt-4 px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">返回专题列表</button>
      </div>
    </div>;
  }

  const members = series.members || [];
  return <div className={`${embedded ? 'series-detail-legacy-embedded' : 'flex-1 bg-[#0B0C10] p-4 md:p-8 overflow-y-auto custom-scrollbar'} text-white`}>
    <div ref={contentRef} onScroll={handleContentScroll} className={embedded ? 'series-detail-legacy-content' : 'max-w-[1080px] mx-auto'}>
      <div className={`flex items-center mb-6${embedded ? ' series-legacy-breadcrumb' : ''}`}>
        <button onClick={() => navigate('/series')} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"><ArrowLeft size={14} /> 专题系列</button>
      </div>

      <div className="mb-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <Layers size={24} className="text-purple-400 shrink-0" />
              <h1 className="text-xl font-bold">{series.name}</h1>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#1A1B20] text-gray-500">{STATUS_LABEL[series.status] || series.status}</span>
            </div>
            {series.description && <p className="text-sm text-gray-400">{series.description}</p>}
            <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-600 flex-wrap">
              <span>{members.length} 条内容</span>
              <button onClick={handleRefresh} disabled={refreshing} className="series-scan-action flex items-center gap-1 text-gray-500 hover:text-violet-300 transition-colors" title="按需扫描新内容">
                {refreshing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}{refreshing ? '扫描中' : '扫描新内容'}
              </button>
              {suggestions.length > 0 && <button onClick={() => setShowSuggestions(true)} className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 transition-colors"><Bell size={10} /> 待确认 ({suggestions.length})</button>}
              {suggestionsLoaded && suggestions.length === 0 && allProcessed && <span className="text-emerald-500/60">暂无新增建议</span>}
              <span>创建于 {formatTimeBeijing(series.created_at)}</span>
              {series.updated_at && <span>更新于 {formatTimeBeijing(series.updated_at)}</span>}
            </div>
          </div>
          <div className="series-detail-header-actions flex items-center gap-1.5 sm:gap-2 shrink-0 flex-wrap">
            {!embedded && <>
              <button onClick={handleGenerateIntro} disabled={introGenerating || members.length < 2} className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {introGenerating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}<span className="hidden sm:inline">{series.intro ? '重新生成导言' : 'AI 生成导言'}</span>
              </button>
              <button onClick={handleGenerateSummary} disabled={summaryGenerating || members.length < 2} className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {summaryGenerating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}<span className="hidden sm:inline">{series.summary ? '重新生成总结' : 'AI 生成总结'}</span>
              </button>
              <button onClick={handleGeneratePaper} disabled={paperGenerating || members.length < 2} className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {paperGenerating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}<span className="hidden sm:inline">{series.paper ? '重新生成深度分析' : 'AI 深度分析'}</span>
              </button>
            </>}
            <button onClick={() => navigate(`/tasks?source=series&source_id=${id}&source_label=来自专题：${series.name || ''}`)}
              className={embedded ? 'series-header-action series-header-task-action' : 'px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/30 transition-colors flex items-center gap-1.5'} aria-label="添加待办" title="添加待办">
              {embedded ? <ListPlus size={15} /> : <Plus size={14} />}{!embedded && <span className="hidden sm:inline">添加待办</span>}
            </button>
            {embedded ? <button type="button" className="series-header-action series-header-delete-action" aria-label="删除专题" title="删除专题" onClick={() => setConfirmDelete(true)}><Trash2 size={15} /></button>
              : <button onClick={() => setConfirmDelete(true)} className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium text-red-400 bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 transition-colors flex items-center gap-1.5"><Trash2 size={14} /></button>}
          </div>
        </div>
        {(introGenerating || summaryGenerating || paperGenerating || operationError) && <div className={`series-operation-state${operationError ? ' is-error' : ''}`}>
          {operationError || (introGenerating ? '正在生成专题导言' : summaryGenerating ? '正在生成结构化速览' : '正在生成深度分析')}
          <span>{operationError ? '请检查服务状态后重试' : '内容完成后会自动同步到左侧列表与底部状态盒'}</span>
        </div>}
      </div>

      <SeriesSummaryPanel series={series} embedded={embedded} tab={tab} memberCount={members.length}
        introGenerating={introGenerating} summaryGenerating={summaryGenerating} paperGenerating={paperGenerating}
        onSelectTab={selectTab} onGenerateIntro={handleGenerateIntro} onGenerateSummary={handleGenerateSummary}
        onGeneratePaper={handleGeneratePaper} onReferenceClick={handleRefClick} />
      <SeriesMemberPanel tab={tab} members={members} panelId={panelId} onToggleMember={togglePanel} onOpenMember={handleOpenMember} />

      <Modal open={showSuggestions} onClose={() => setShowSuggestions(false)} title={`待确认建议（${suggestions.length}）`} maxWidth="2xl">
        {suggestions.length === 0 ? <p className="text-sm text-gray-500 text-center py-8">暂无待确认的建议</p> : <>
          <div className="space-y-1.5 max-h-[60vh] overflow-y-auto custom-scrollbar">
            {suggestions.map((suggestion) => <div key={suggestion.id}
              onClick={(event) => { if ((event.target as HTMLElement).tagName !== 'INPUT') toggleSelect(suggestion.id); }}
              className={`bg-[#0B0C10] border rounded-lg px-3 py-2.5 transition-colors cursor-pointer ${selectedIds.includes(suggestion.id) ? 'border-violet-500/40 bg-violet-500/5' : 'border-[#2A2B30] hover:border-[#3A3B40]'}`}>
              <div className="flex items-center gap-3">
                <input type="checkbox" checked={selectedIds.includes(suggestion.id)} onChange={() => toggleSelect(suggestion.id)} className="w-4 h-4 rounded accent-violet-500 shrink-0 cursor-pointer" />
                <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 ${getTopicColor(suggestion.topic)} bg-white/5`}>{suggestion.topic || '未分类'}</span>
                <span className="flex-1 min-w-0 text-sm text-white truncate">{suggestion.title}</span>
              </div>
              {suggestion.reason && <p className="mt-1 ml-7 text-[11px] text-gray-500 line-clamp-2">{suggestion.reason}</p>}
            </div>)}
          </div>
          <div className="flex items-center gap-3 mt-3 pt-3 border-t border-[#2A2B30]">
            <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none">
              <input type="checkbox" checked={selectedIds.length === suggestions.length && suggestions.length > 0} onChange={toggleSelectAll} className="w-3.5 h-3.5 rounded accent-violet-500" />全选
            </label>
            <span className="text-[11px] text-gray-500">已选 {selectedIds.length} 项</span><div className="flex-1" />
            <button onClick={handleBatchDismiss} disabled={selectedIds.length === 0} className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-400 hover:text-gray-200 border border-gray-600 hover:border-gray-500 transition-colors disabled:opacity-40">忽略选中</button>
            <button onClick={handleBatchAdd} disabled={selectedIds.length === 0 || batchAdding} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30 transition-colors disabled:opacity-40 flex items-center gap-1.5">
              {batchAdding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}添加选中
            </button>
          </div>
        </>}
      </Modal>

      <Modal open={showProgress} onClose={() => setShowProgress(false)} title="处理进度" maxWidth="sm">
        <div className="space-y-4">
          <ProgressRow active={progressStage === 'adding'} done={progressStage !== 'adding'} color="text-emerald-400" title="添加成员到专题" />
          <ProgressRow active={progressStage === 'summary'} done={progressStage === 'paper' || progressStage === 'done'} color="text-amber-400" title="重新生成结构化速览" waiting={progressStage === 'adding'} />
          <ProgressRow active={progressStage === 'paper'} done={progressStage === 'done'} color="text-sky-400" title="重新生成深度分析" waiting={progressStage === 'adding' || progressStage === 'summary'} />
          {progressStage === 'done' && <p className="text-[11px] text-emerald-400 text-center">全部完成，页面已自动刷新</p>}
          <p className="text-[10px] text-gray-600 text-center">关闭弹窗不会中断处理</p>
        </div>
      </Modal>

      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="删除专题" maxWidth="sm">
        <div className="space-y-4">
          <p className="text-sm text-gray-300">确认删除专题 <span className="text-white font-medium">「{series.name}」</span>？</p>
          <p className="text-xs text-gray-500">删除后专题及所有成员关联将被移除，此操作不可撤销。</p>
          <div className="flex items-center justify-end gap-3 pt-2">
            <button onClick={() => setConfirmDelete(false)} className="px-4 py-2 rounded-lg text-xs font-medium text-gray-400 hover:text-gray-200 border border-gray-600 hover:border-gray-500 transition-colors">取消</button>
            <button onClick={handleDelete} disabled={deleting} className="px-4 py-2 rounded-lg text-xs font-medium bg-red-500 text-white hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center gap-1.5">
              {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}确认删除
            </button>
          </div>
        </div>
      </Modal>
    </div>
  </div>;
}

function ProgressRow({ active, done, color, title, waiting = false }: { active: boolean; done: boolean; color: string; title: string; waiting?: boolean }) {
  return <div className="flex items-center gap-3">
    {active ? <Loader2 size={16} className={`animate-spin ${color} shrink-0`} /> : done ? <Check size={16} className="text-emerald-400 shrink-0" /> : <div className="w-4 h-4 rounded-full border border-gray-600 shrink-0" />}
    <div className="flex-1 min-w-0">
      <p className={`text-sm ${waiting ? 'text-gray-600' : 'text-white'}`}>{title}</p>
      {active && title !== '添加成员到专题' && <p className={`text-[11px] ${color}`}>生成中...</p>}
      {done && <p className="text-[11px] text-gray-500">已完成</p>}
    </div>
  </div>;
}
