import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { AlertTriangle, BookOpen, FileUp, Loader2, Plus, RefreshCw, Search, X } from 'lucide-react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { apiFetch } from '../api';
import { useCurtain } from '../CurtainContext';
import CinematicLaserWorkspace from '../components/cinematic/CinematicLaserWorkspace';
import CinematicTemplatePage from '../components/cinematic/CinematicTemplatePage';
import { CINEMATIC_LASER_PRESET } from '../components/cinematic/cinematicLaserPreset';
import { useCinematicTemplateLayout } from '../components/cinematic/useCinematicTemplateLayout';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import { buildStudyCreatePayload, buildStudyUploadFields, createStudyDetailCache, filterStudyItems, getStudyStats, removeStudyItem } from '../components/cinematic-study/studyWorkspace.mjs';
import LaserFlow from '../components/react-bits/LaserFlow';
import LegacyStudyDetail, { type StudyMaterial } from './StudyDetail';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';
import '../components/cinematic-study/cinematic-study.css';

type StudyItem = Pick<StudyMaterial, 'id' | 'subject' | 'grade' | 'textbook' | 'study_type' | 'title' | 'source_type' | 'status' | 'score' | 'is_correct' | 'created_at' | 'updated_at'> & { mistake_tags?: string[] };
type Mode = 'materials' | 'mistakes';

const SUBJECTS = ['全部', '语文', '数学', '英语'];
const CATEGORIES = ['单项训练', '课时练习', '单元试卷', '期中试卷', '期末试卷', '随堂测验', '课后作业', '寒暑假作业', '教材/课本'];
const TYPE_OPTIONS: Record<string, string[]> = {
  语文: ['阅读理解', '作文', '看图写话', '仿写', '句子训练'],
  数学: ['应用题', '计算题', '几何题', '单位换算', '行程问题'],
  英语: ['阅读理解', '完形填空', '单词', '语法', '翻译', '写作'],
};
const EMPTY_FORM = { subject: '语文', category: '单项训练', type: '阅读理解', title: '', raw_content: '', grade: '', textbook: '' };

export default function CinematicStudy() {
  const { id: routeId } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { navigateWithCurtain } = useCurtain();
  const { profile, style } = useCinematicTemplateLayout('system');
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const [materials, setMaterials] = useState<StudyItem[]>([]);
  const [mistakes, setMistakes] = useState<StudyItem[]>([]);
  const [mode, setMode] = useState<Mode>(() => location.pathname === '/study-mistakes' ? 'mistakes' : 'materials');
  const [subject, setSubject] = useState('全部');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState(routeId || '');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState(false);
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const fileRef = useRef<HTMLInputElement>(null);
  const detailCacheRef = useRef(createStudyDetailCache(12));

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [materialsResponse, mistakesResponse] = await Promise.all([
        apiFetch('/api/study/list?page_size=100'),
        apiFetch('/api/study/mistakes/list'),
      ]);
      if (!materialsResponse.ok || !mistakesResponse.ok) throw new Error('学习资料加载失败');
      const [materialsData, mistakesData] = await Promise.all([materialsResponse.json(), mistakesResponse.json()]);
      const nextMaterials = materialsData.items || [];
      const nextMistakes = mistakesData.items || [];
      setMaterials(nextMaterials);
      setMistakes(nextMistakes);
      setSelectedId((current) => current && nextMaterials.some((item: StudyItem) => item.id === current) ? current : nextMaterials[0]?.id || '');
      setError('');
    } catch (reason: any) { setError(reason?.message || '学习资料加载失败'); }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => { if (routeId) setSelectedId(routeId); }, [routeId]);

  const sourceItems = mode === 'mistakes' ? mistakes : materials;
  const filteredItems = useMemo(() => filterStudyItems(sourceItems, subject, query), [sourceItems, subject, query]);
  const selected = materials.find((item) => item.id === selectedId) || mistakes.find((item) => item.id === selectedId) || filteredItems[0];
  const stats = useMemo(() => ({ ...getStudyStats(materials), mistakes: mistakes.length }), [materials, mistakes]);
  const coreBoxHeight = Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamVerticalOffset = (coreBoxHeight - 6) / Math.max(viewportHeight, 1) - 0.5;

  function selectItem(id: string) {
    setSelectedId(id);
    navigate(`/study/${id}`, { replace: true });
  }

  function handleMaterialChange(detail: StudyMaterial) {
    detailCacheRef.current.set(detail.id, detail);
    setMaterials((current) => current.map((item) => item.id === detail.id ? { ...item, ...detail } : item));
    setMistakes((current) => detail.is_correct === 0
      ? current.some((item) => item.id === detail.id) ? current.map((item) => item.id === detail.id ? { ...item, ...detail } : item) : [{ ...detail }, ...current]
      : current.filter((item) => item.id !== detail.id));
  }

  function handleDeleted(id: string) {
    setMaterials((current) => {
      const next = removeStudyItem(current, id);
      setSelectedId(next.selectedId);
      navigate(next.selectedId ? `/study/${next.selectedId}` : '/study', { replace: true });
      return next.items;
    });
    setMistakes((current) => current.filter((item) => item.id !== id));
    detailCacheRef.current.delete(id);
  }

  async function createMaterial() {
    if (!form.raw_content.trim()) return;
    setCreating(true); setError('');
    try {
      const response = await apiFetch('/api/study/create', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildStudyCreatePayload(form)) });
      if (!response.ok) throw new Error('创建失败');
      const data = await response.json();
      setDialog(false); setForm(EMPTY_FORM);
      await loadData(); selectItem(data.material_id);
    } catch (reason: any) { setError(reason?.message || '创建失败'); }
    setCreating(false);
  }

  async function uploadFile(file: File) {
    setUploading(true); setError('');
    try {
      const body = new FormData();
      body.append('file', file);
      Object.entries(buildStudyUploadFields(form)).forEach(([key, value]) => body.append(key, value));
      const response = await apiFetch('/api/study/upload', { method: 'POST', body });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '上传失败');
      if (data.auto_created) { setDialog(false); await loadData(); selectItem(data.material_id); }
      else setForm((current) => ({ ...current, title: current.title || file.name.replace(/\.[^.]+$/, ''), raw_content: data.text || '' }));
    } catch (reason: any) { setError(reason?.message || '上传失败'); }
    setUploading(false);
  }

  const status = <section className="ingest-observation cinematic-observation study-status"><div className="panel-status"><i className="signal-dot" /><span>学习中枢</span></div><span>学习资料、讲题稿与错题复盘统一编排</span><div className="system-status-summary"><span className="is-good">资料 {stats.total}</span><span className="is-cyan">已生成 {stats.ready}</span><span className="is-warn">错题 {stats.mistakes}</span></div><div className="panel-detail-grid"><span>当前<b>{selected?.title || '--'}</b></span><span>学科<b>{selected?.subject || '--'}</b></span></div></section>;
  const commands = <section className="ingest-command-launcher study-command-launcher"><div className="launcher-actions"><button className="launcher-action ingest-command-metric is-douyin" onClick={() => setDialog(true)}><Plus size={15} /><b>新建资料</b><span>录入或 OCR</span><small>CREATE</small></button><button className="launcher-action ingest-command-metric is-file" onClick={() => { setMode('materials'); setSubject('全部'); }}><BookOpen size={15} /><b>学习资料</b><span>{materials.length} 项</span><small>MATERIAL</small></button><button className="launcher-action ingest-command-metric is-concept" onClick={() => { setMode('mistakes'); setSubject('全部'); }}><AlertTriangle size={15} /><b>错题复盘</b><span>{mistakes.length} 项</span><small>REVIEW</small></button><button className="launcher-action ingest-command-metric is-source" onClick={loadData}><RefreshCw size={15} /><b>刷新学习</b><span>同步状态</span><small>REFRESH</small></button></div></section>;
  const index = <><div className="ingest-topic-orbit study-topic-orbit"><button className={mode === 'materials' ? 'is-active is-gold' : ''} onClick={() => setMode('materials')}><BookOpen size={14} /><span>资料</span></button><button className={mode === 'mistakes' ? 'is-active is-gold' : ''} onClick={() => setMode('mistakes')}><AlertTriangle size={14} /><span>错题</span></button>{SUBJECTS.slice(1).map((value) => <button key={value} className={subject === value ? 'is-active is-cyan' : ''} onClick={() => setSubject(subject === value ? '全部' : value)}><span>{value}</span></button>)}</div><label className="study-index-search"><Search size={13} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索学习资料" /></label><div className="ingest-index-list study-index-list">{filteredItems.map((item, index) => <button key={item.id} className={`ingest-index-item${selected?.id === item.id ? ' is-active' : ''}`} style={{ '--index-depth-scale': 1 - Math.min(index, 9) * .028, '--index-depth-z': `${-Math.min(index, 9) * 3}px`, '--index-depth-opacity': 1 - Math.min(index, 9) * .04 } as CSSProperties} onClick={() => selectItem(item.id)}><div className="index-title"><b>{item.title}</b><span><em className={item.is_correct === 0 ? 'is-warn' : 'is-cyan'}>{item.subject}</em></span></div><small>{item.study_type}{item.grade ? ` · ${item.grade}` : ''}</small></button>)}</div></>;

  const isTextbookForm = form.category === '教材/课本';
  return <CinematicTemplatePage className="cinematic-study" profile={profile} topic="gold" style={style} variant="system" status={status} commands={commands} workspace={<CinematicLaserWorkspace ariaLabel="学习聚合舱" indexAriaLabel="学习索引" index={index} stageAriaLabel="学习详情" stage={<><LaserFlow {...CINEMATIC_LASER_PRESET} color="#F7C873" verticalBeamOffset={beamVerticalOffset} dpr={laserRenderProfile.dpr} maxFps={laserRenderProfile.maxFps} />{selected ? <LegacyStudyDetail embedded materialId={selected.id} initialMaterial={detailCacheRef.current.get(selected.id)} onMaterialChange={handleMaterialChange} onDeleted={handleDeleted} /> : <div className="study-cinematic-loading">{loading ? <Loader2 className="animate-spin" /> : error || '暂无学习资料'}</div>}<div className="laser-media-box study-core-box"><span>LEARNING WORKSPACE</span><b>{selected?.title || '等待学习资料'}</b><div><em>学科<strong>{selected?.subject || '--'}</strong></em><em>状态<strong>{selected?.status || '--'}</strong></em><em>成绩<strong>{selected?.score ?? '--'}</strong></em></div></div></>} />} overlays={dialog ? <div className="study-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setDialog(false)}><section className="study-dialog"><button className="study-dialog-close" onClick={() => setDialog(false)}><X /></button><header><span>LEARNING INPUT</span><h2>新建学习资料</h2></header><div className="study-dialog-body"><div className="study-form-grid"><label><span>分类</span><select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>{CATEGORIES.map((value) => <option key={value}>{value}</option>)}</select></label><label><span>学科</span><select value={form.subject} onChange={(event) => setForm({ ...form, subject: event.target.value, type: TYPE_OPTIONS[event.target.value]?.[0] || '' })}><option>语文</option><option>数学</option><option>英语</option></select></label>{form.category === '单项训练' && <label><span>题型</span><select value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value })}>{TYPE_OPTIONS[form.subject].map((value) => <option key={value}>{value}</option>)}</select></label>}<label><span>年级</span><input value={form.grade} onChange={(event) => setForm({ ...form, grade: event.target.value })} placeholder="例如：四年级" /></label>{isTextbookForm && <label><span>教材</span><input value={form.textbook} onChange={(event) => setForm({ ...form, textbook: event.target.value })} placeholder="例如：人教版" /></label>}<label><span>标题</span><input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder={isTextbookForm ? '教材名称' : '可选'} /></label></div>{!isTextbookForm && <label className="study-content-field"><span>学习内容</span><textarea value={form.raw_content} onChange={(event) => setForm({ ...form, raw_content: event.target.value })} placeholder="粘贴题目、文章或学习材料" /></label>}<p className="study-dialog-hint">{isTextbookForm ? '教材模式直接上传 PDF 或图片，系统保留原文件并创建资料。' : '可手动粘贴，也可上传 PDF 或图片完成 OCR 后再确认创建。'}</p>{error && <p className="study-dialog-error">{error}</p>}<footer><input ref={fileRef} hidden type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={(event) => event.target.files?.[0] && uploadFile(event.target.files[0])} /><button onClick={() => fileRef.current?.click()} disabled={uploading}><FileUp size={14} />{uploading ? '处理中' : isTextbookForm ? '上传教材' : '上传 OCR'}</button>{!isTextbookForm && <button className="study-primary" onClick={createMaterial} disabled={creating || !form.raw_content.trim()}>{creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}创建资料</button>}</footer></div></section></div> : null} activeHub={activeHub} onActiveHubChange={setActiveHub} onNavigate={(path) => navigateWithCurtain(path)} />;
}
