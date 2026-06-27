import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCurtain } from '../CurtainContext';
import { BookOpen, Loader2, Plus, Search, Trash2, Upload, X } from 'lucide-react';
import { formatTimeBeijing } from '../utils';
import { apiFetch } from '../api';

interface StudyItem {
  id: string;
  subject: string;
  grade: string;
  textbook: string;
  study_type: string;
  title: string;
  source_type: string;
  status: string;
  score: number | null;
  is_correct: number | null;
  created_at: string;
  updated_at: string;
}

const SUBJECTS = ['全部', '语文', '数学', '英语'];
const STATUS_LABELS: Record<string, string> = { draft: '草稿', ready: '已生成', reviewed: '已批改' };
const CORRECT_LABELS: Record<number, string> = { 1: '✓', 0: '✗' };
const CORRECT_COLORS: Record<number, string> = { 1: 'text-emerald-400', 0: 'text-red-400' };

export default function Study() {
  const navigate = useNavigate();
  const { navigateWithCurtain } = useCurtain();
  const [items, setItems] = useState<StudyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [subject, setSubject] = useState('全部');
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Create modal
  const [showCreate, setShowCreate] = useState(false);
  const [newSubject, setNewSubject] = useState('语文');
  const [newCategory, setNewCategory] = useState('单项训练');
  const [newType, setNewType] = useState('阅读理解');
  const [newTitle, setNewTitle] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newGrade, setNewGrade] = useState('');
  const [newTextbook, setNewTextbook] = useState('');
  const [creating, setCreating] = useState(false);
  // File upload state
  const [uploading, setUploading] = useState(false);
  const [uploadFileName, setUploadFileName] = useState('');
  const [ocrMaterialId, setOcrMaterialId] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const CATEGORIES = ['单项训练', '课时练习', '单元试卷', '期中试卷', '期末试卷', '随堂测验', '课后作业', '寒暑假作业', '教材/课本'];

  const TYPE_OPTIONS: Record<string, string[]> = {
    '语文': ['阅读理解', '作文', '看图写话', '仿写', '句子训练'],
    '数学': ['应用题', '计算题', '几何题', '单位换算', '行程问题'],
    '英语': ['阅读理解', '完形填空', '单词', '语法', '翻译', '写作'],
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (subject !== '全部') params.set('subject', subject);
      const r = await apiFetch(`/api/study/list?${params.toString()}`);
      if (!r.ok) throw new Error('加载失败');
      const data = await r.json();
      setItems(data.items || []);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [subject]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCreate = async () => {
    if (!newContent.trim()) return;
    setCreating(true);
    try {
      const actualType = newCategory === '单项训练' ? newType : newCategory;
      const r = await apiFetch('/api/study/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject: newSubject,
          study_type: actualType,
          title: newTitle.trim() || '未命名',
          raw_content: newContent.trim(),
          grade: newGrade,
          textbook: newTextbook,
        }),
      });
      if (!r.ok) throw new Error('创建失败');
      const data = await r.json();
      closeCreate();
      navigate(`/study/${data.material_id}`);
    } catch (e: any) {
      setError(e.message || '创建失败');
    } finally {
      setCreating(false);
    }
  };

  const closeCreate = () => {
    setShowCreate(false);
    setNewCategory('单项训练');
    setNewTitle('');
    setNewContent('');
    setNewGrade('');
    setNewTextbook('');
    setError('');
    setUploadFileName('');
    setOcrMaterialId('');
  };

  const handleFileUpload = async (file: File) => {
    setUploading(true);
    setUploadFileName(file.name);
    setError('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('category', newCategory);
      if (newSubject) formData.append('subject', newSubject);
      if (newType) formData.append('study_type', newType);
      if (newGrade) formData.append('grade', newGrade);

      const r = await apiFetch('/api/study/upload', { method: 'POST', body: formData });
      if (!r.ok) {
        const err = await r.json();
        throw new Error(err.detail || 'OCR 失败');
      }
      const data = await r.json();
      if (data.auto_created) {
        // 教材类：已自动创建记录，直接跳转
        closeCreate();
        navigate(`/study/${data.material_id}`);
        return;
      }
      setNewContent(data.text || '');
      setOcrMaterialId(data.material_id || '');
      // 如果没标题，用文件名
      if (!newTitle) setNewTitle(file.name.replace(/\.[^.]+$/, ''));
    } catch (e: any) {
      setError(e.message || '上传失败');
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileUpload(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileUpload(file);
  };

  const handleDelete = async (id: string, title: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`确定删除「${title}」？`)) return;
    setDeletingId(id);
    try {
      const r = await apiFetch(`/api/study/${id}`, { method: 'DELETE' });
      if (!r.ok) throw new Error('删除失败');
      setItems(prev => prev.filter(i => i.id !== id));
    } catch (e: any) {
      setError(e.message || '删除失败');
    } finally {
      setDeletingId(null);
    }
  };

  const filtered = search
    ? items.filter(i => i.title.toLowerCase().includes(search.toLowerCase()))
    : items;

  return (
    <div className="flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
      {/* 吸顶头部 */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-[1080px] mx-auto">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
            <div>
              <div className="flex items-center gap-3">
                <BookOpen size={40} className="text-amber-400 shrink-0" />
                <div>
                  <h1 className="text-2xl font-bold">辅导中心</h1>
                  <p className="text-gray-400 text-sm mt-0.5">学习资料管理与讲题稿生成</p>
                </div>
              </div>
            </div>
            <button
              onClick={() => setShowCreate(true)}
              className="px-3 py-2 rounded-lg text-xs font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30 transition-colors flex items-center gap-1.5 shrink-0"
            >
              <Plus size={14} />
              <span className="hidden sm:inline">新建资料</span>
            </button>
          </div>

          {error && <div className="text-red-400 text-xs mb-3 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</div>}

          {/* Tab 栏 */}
          <div className="border-b border-[#2A2B30]">
            <div className="flex gap-6">
              {SUBJECTS.map(s => (
                <button
                  key={s}
                  onClick={() => setSubject(s)}
                  className={`pb-3 text-xs font-medium transition-colors relative ${
                    subject === s ? 'text-amber-400' : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {s}
                  {subject === s && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-500" />}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 可滚动内容区 */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-[1080px] mx-auto pt-4">
          {/* 搜索栏 */}
          <div className="mb-4 flex items-center gap-2">
            <div className="relative flex-1 max-w-xs">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="搜索标题..."
                className="w-full bg-[#141518] border border-[#2A2B30] rounded-lg pl-9 pr-3 py-1.5 text-xs text-gray-300 outline-none focus:border-amber-500/50"
              />
              {search && (
                <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400"><X size={12} /></button>
              )}
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16"><Loader2 size={24} className="animate-spin text-gray-500" /></div>
          ) : filtered.length === 0 ? (
            <div className="text-center text-gray-600 py-16">
              <BookOpen size={48} className="mx-auto mb-4 opacity-40" />
              <p className="text-sm">暂无学习资料</p>
              <p className="text-xs mt-1 text-gray-700">点击「新建资料」开始</p>
            </div>
          ) : (
            <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[#2A2B30] text-gray-500">
                    <th className="text-center py-3 px-3 font-medium">标题</th>
                    <th className="text-center py-3 px-3 font-medium hidden sm:table-cell">学科</th>
                    <th className="text-center py-3 px-3 font-medium hidden md:table-cell">题型</th>
                    <th className="text-center py-3 px-3 font-medium whitespace-nowrap">状态</th>
                    <th className="text-center py-3 px-3 font-medium whitespace-nowrap">对错</th>
                    <th className="text-center py-3 px-3 font-medium hidden lg:table-cell whitespace-nowrap">时间</th>
                    <th className="text-center py-3 px-3 font-medium w-12">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(item => (
                    <tr
                      key={item.id}
                      onClick={() => navigateWithCurtain(`/study/${item.id}`)}
                      className="border-b border-[#2A2B30] last:border-b-0 hover:bg-[#1A1B20] cursor-pointer transition-colors"
                    >
                      <td className="py-3 px-3 text-center">
                        <span className="text-gray-200 truncate inline-block max-w-[240px]">{item.title}</span>
                      </td>
                      <td className="py-3 px-3 text-center hidden sm:table-cell">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded whitespace-nowrap ${
                          item.subject === '语文' ? 'text-blue-400 bg-blue-500/10' :
                          item.subject === '数学' ? 'text-amber-400 bg-amber-500/10' :
                          'text-emerald-400 bg-emerald-500/10'
                        }`}>{item.subject}</span>
                      </td>
                      <td className="py-3 px-3 text-center text-gray-400 hidden md:table-cell">{item.study_type}</td>
                      <td className="py-3 px-3 text-center whitespace-nowrap">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium border whitespace-nowrap ${
                          item.status === 'ready' ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' :
                          item.status === 'reviewed' ? 'text-sky-400 bg-sky-500/10 border-sky-500/20' :
                          'text-gray-500 bg-gray-500/10 border-gray-500/20'
                        }`}>{STATUS_LABELS[item.status] || item.status}</span>
                      </td>
                      <td className="py-3 px-3 text-center whitespace-nowrap">
                        {item.is_correct != null && (
                          <span className={`font-bold ${CORRECT_COLORS[item.is_correct]}`}>
                            {CORRECT_LABELS[item.is_correct]}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-center text-gray-600 hidden lg:table-cell whitespace-nowrap">{formatTimeBeijing(item.created_at)}</td>
                      <td className="py-3 px-1 text-center">
                        <button
                          onClick={(e) => handleDelete(item.id, item.title, e)}
                          disabled={deletingId === item.id}
                          className="p-1 rounded text-gray-600 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-30"
                          title="删除"
                        >
                          {deletingId === item.id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* 新建弹窗 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={closeCreate} />
          <div className="relative bg-[#141518] border border-[#2A2B30] rounded-xl w-full max-w-lg mx-4 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold">新建学习资料</h2>
              <button onClick={closeCreate} className="text-gray-500 hover:text-gray-300"><X size={18} /></button>
            </div>

            <div className="space-y-4">
              <div className="flex gap-2">
                <select value={newCategory} onChange={e => setNewCategory(e.target.value)}
                  className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-amber-500/50">
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                <select value={newSubject} onChange={e => { setNewSubject(e.target.value); setNewType(TYPE_OPTIONS[e.target.value]?.[0] || ''); }}
                  className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-amber-500/50">
                  {Object.keys(TYPE_OPTIONS).map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="flex gap-2">
                {newCategory === '单项训练' ? (
                  <select value={newType} onChange={e => setNewType(e.target.value)}
                    className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-amber-500/50">
                    {(TYPE_OPTIONS[newSubject] || []).map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                ) : (
                  <div className="flex-1" />
                )}
                <input
                  value={newGrade}
                  onChange={e => setNewGrade(e.target.value)}
                  placeholder="年级"
                  className="w-20 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-amber-500/50"
                />
                {newCategory === '教材/课本' ? (
                  <input
                    value={newTextbook}
                    onChange={e => setNewTextbook(e.target.value)}
                    placeholder="如：人教版三年级上册"
                    className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-amber-500/50"
                  />
                ) : (
                  <div className="flex-1" />
                )}
              </div>
              <input
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                placeholder="标题（可选，AI 会自动生成）"
                className="w-full bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-amber-500/50"
              />

              {/* 文件拖拽上传区 */}
              <div
                onDrop={handleDrop}
                onDragOver={e => e.preventDefault()}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
                  uploading
                    ? 'border-purple-500/30 bg-purple-500/5'
                    : uploadFileName
                    ? 'border-emerald-500/30 bg-emerald-500/5'
                    : 'border-[#2A2B30] hover:border-amber-500/30 hover:bg-[#1A1B20]'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.webp"
                  onChange={handleFileChange}
                  className="hidden"
                />
                {uploading ? (
                  <div className="flex items-center justify-center gap-2 text-xs text-purple-400">
                    <Loader2 size={14} className="animate-spin" />
                    <span>正在识别 {uploadFileName}...</span>
                  </div>
                ) : uploadFileName ? (
                  <div className="text-xs text-emerald-400">
                    <Upload size={16} className="mx-auto mb-1" />
                    <span>{uploadFileName}</span>
                    <span className="block text-gray-500 mt-0.5">识别完成，内容已填入下方</span>
                  </div>
                ) : (
                  <div className="text-xs text-gray-500">
                    <Upload size={16} className="mx-auto mb-1" />
                    <span>拖拽 PDF 或图片到这里</span>
                    <span className="block text-gray-600 mt-0.5">支持扫描件自动 OCR</span>
                  </div>
                )}
              </div>

              <textarea
                value={newContent}
                onChange={e => setNewContent(e.target.value)}
                placeholder="粘贴题目内容，或上传文件自动识别..."
                rows={6}
                className="w-full bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2 text-xs text-gray-300 outline-none focus:border-amber-500/50 resize-none"
              />
            </div>

            <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-[#2A2B30]">
              <button onClick={closeCreate} className="px-4 py-2 rounded-lg text-xs text-gray-400 hover:text-gray-200 transition-colors">取消</button>
              <button
                onClick={handleCreate}
                disabled={creating || !newContent.trim()}
                className="px-4 py-2 rounded-lg text-xs font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30 transition-colors flex items-center gap-1.5 disabled:opacity-50"
              >
                {creating && <Loader2 size={12} className="animate-spin" />}
                创建并生成讲稿
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
