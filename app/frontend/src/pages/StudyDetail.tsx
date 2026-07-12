import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, BookOpen, ChevronDown, ChevronRight, FileCode2, FileType2, Globe, Layers, Loader2, RefreshCw, Sparkles, Trash2 } from 'lucide-react';
import { formatTimeBeijing } from '../utils';
import { escapeHtml, sanitizeHtml } from '../safeHtml';
import { apiFetch } from '../api';

/* ── helpers ── */

function parseChars(s: string): { py: string; hz: string }[] {
  if (!s.trim()) return [];
  return s.split(/\s+/).map(pair => {
    const idx = pair.indexOf(':');
    return { py: pair.slice(0, idx), hz: pair.slice(idx + 1) };
  });
}

/** MD → styled HTML (matches 专题详情 depth analysis) */
function mdToHtml(md: string): string {
  function bold(s: string): string {
    return s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-gray-100">$1</strong>');
  }
  let html = '';
  let inList = false;
  for (const raw of md.split('\n')) {
    const line = escapeHtml(raw.trim());
    if (line.startsWith('#### ')) {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<h4 class="text-xs font-semibold text-purple-400/80 mt-4 mb-1.5">${bold(line.slice(5))}</h4>`;
    } else if (line.startsWith('### ')) {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<h3 class="text-sm font-semibold text-purple-400 mt-5 mb-2">${bold(line.slice(4))}</h3>`;
    } else if (line.startsWith('## ')) {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<h3 class="text-base font-bold text-purple-300 mt-5 mb-3 border-b border-[#2A2B30] pb-2">${bold(line.slice(3))}</h3>`;
    } else if (/^\* (?!\*)/.test(line)) {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<p class="mb-2 text-sm text-gray-300 leading-relaxed"><strong class="font-semibold text-gray-200">▸ ${bold(line.slice(2))}</strong></p>`;
    } else if (/^- /.test(line)) {
      if (!inList) { html += '<ul class="space-y-1 mt-1 mb-3">'; inList = true; }
      html += `<li class="flex gap-1.5"><span class="text-gray-500 shrink-0">•</span><span class="text-gray-300 text-sm leading-relaxed">${bold(line.replace(/^- /, ''))}</span></li>`;
    } else if (/^\d+\.\s/.test(line)) {
      if (inList) { html += '</ul>'; inList = false; }
      const m = line.match(/^(\d+)\.\s(.+)/);
      html += `<p class="mb-1 text-sm text-gray-300 leading-relaxed pl-4"><span class="text-gray-500 font-mono text-xs mr-1">${m![1]}.</span>${bold(m![2])}</p>`;
    } else if (/^[-*]{3,}$/.test(line)) {
      if (inList) { html += '</ul>'; inList = false; }
    } else if (line === '') {
      if (inList) { html += '</ul>'; inList = false; }
    } else {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<p class="mb-2 text-sm text-gray-300 leading-relaxed">${bold(line)}</p>`;
    }
  }
  if (inList) html += '</ul>';
  return sanitizeHtml(html);
}

/* ── types ── */

interface TextbookLesson {
  lesson_num: number; title: string; content: string; analysis_md: string;
}
interface UnitItem { type: string; title: string; lesson_num: number | null; }
interface UnitInfo { unit_num: number; theme: string; items: UnitItem[]; }
type VersionTab = 'child' | 'parent';
type FormatTab = 'md' | 'html' | 'pdf' | 'original' | 'lessons';

export interface StudyMaterial {
  id: string; subject: string; grade: string; textbook: string; study_type: string;
  title: string; source_type: string; raw_content: string;
  child_version: string; parent_version: string;
  formats_json: Record<string, string>; lessons_json: TextbookLesson[];
  status: string; score: number | null; is_correct: number | null;
  mistake_tags: string[]; created_at: string; updated_at: string;
}

/* ── constants ── */

const FORMATS: { id: FormatTab; label: string; icon: React.ReactNode }[] = [
  { id: 'md', label: 'MD', icon: <FileCode2 size={14} className="text-blue-400" /> },
  { id: 'html', label: 'HTML', icon: <Globe size={14} className="text-emerald-400" /> },
  { id: 'pdf', label: 'PDF', icon: <FileType2 size={14} className="text-rose-400" /> },
  { id: 'original', label: '原始PDF', icon: <FileType2 size={14} className="text-amber-400" /> },
  { id: 'lessons', label: '课文目录', icon: <Layers size={14} className="text-purple-400" /> },
];

/** Pre-defined unit structures — keyed by textbook title substring match */
const UNIT_REGISTRY: Record<string, UnitInfo[]> = {
  '四年级下册语文': [
    { unit_num: 1, theme: '纯朴的乡村，一道独特的风景，一幅和谐的画卷。', items: [
      { type: '课文', title: '古诗词三首', lesson_num: 1 }, { type: '课文', title: '乡下人家', lesson_num: 2 },
      { type: '课文', title: '天窗', lesson_num: 3 }, { type: '略读课文*', title: '三月桃花水', lesson_num: 4 },
      { type: '口语交际', title: '转述', lesson_num: null }, { type: '习作', title: '我的乐园', lesson_num: null },
      { type: '语文园地', title: '语文园地一', lesson_num: null },
    ]},
    { unit_num: 2, theme: '蓝天森林大海，蕴藏自然的奥秘；过去现在未来，述说科技的精彩。', items: [
      { type: '课文', title: '琥珀', lesson_num: 5 }, { type: '课文', title: '飞向蓝天的恐龙', lesson_num: 6 },
      { type: '课文', title: '纳米技术就在我们身边', lesson_num: 7 }, { type: '略读课文*', title: '千年梦圆在今朝', lesson_num: 8 },
      { type: '口语交际', title: '说新闻', lesson_num: null }, { type: '习作', title: '我的奇思妙想', lesson_num: null },
      { type: '语文园地', title: '语文园地二', lesson_num: null }, { type: '快乐读书吧', title: '十万个为什么', lesson_num: null },
    ]},
    { unit_num: 3, theme: '诗歌，让我们用美丽的眼睛看世界。', items: [
      { type: '课文', title: '短诗三首', lesson_num: 9 }, { type: '课文', title: '绿', lesson_num: 10 },
      { type: '课文', title: '白桦', lesson_num: 11 }, { type: '略读课文*', title: '在天晴了的时候', lesson_num: 12 },
      { type: '综合性学习', title: '轻叩诗歌大门', lesson_num: null }, { type: '语文园地', title: '语文园地三', lesson_num: null },
    ]},
    { unit_num: 4, theme: '奔跑飞舞，驻足凝望——可爱的动物，我们的好朋友。', items: [
      { type: '课文', title: '猫', lesson_num: 13 }, { type: '课文', title: '母鸡', lesson_num: 14 },
      { type: '课文', title: '白鹅', lesson_num: 15 }, { type: '习作', title: '我的动物朋友', lesson_num: null },
      { type: '语文园地', title: '语文园地四', lesson_num: null },
    ]},
    { unit_num: 5, theme: '妙笔写美景，巧手著奇观。', items: [
      { type: '课文', title: '海上日出', lesson_num: 16 }, { type: '课文', title: '记金华的双龙洞', lesson_num: 17 },
      { type: '习作例文', title: '颐和园', lesson_num: null }, { type: '习作例文', title: '七月的天山', lesson_num: null },
      { type: '习作', title: '游____', lesson_num: null },
    ]},
    { unit_num: 6, theme: '深深浅浅的脚印，写满成长的故事。', items: [
      { type: '课文', title: '文言文二则', lesson_num: 18 }, { type: '课文', title: '小英雄雨来（节选）', lesson_num: 19 },
      { type: '略读课文*', title: '我们家的男子汉', lesson_num: 20 }, { type: '略读课文*', title: '芦花鞋', lesson_num: 21 },
      { type: '口语交际', title: '朋友相处的秘诀', lesson_num: null }, { type: '习作', title: '我学会了____', lesson_num: null },
      { type: '语文园地', title: '语文园地六', lesson_num: null },
    ]},
    { unit_num: 7, theme: '没有伟大的品格，就没有伟大的人。', items: [
      { type: '课文', title: '古诗三首', lesson_num: 22 }, { type: '课文', title: '“诺曼底号”遇难记', lesson_num: 23 },
      { type: '略读课文*', title: '黄继光', lesson_num: 24 }, { type: '略读课文*', title: '挑山工', lesson_num: 25 },
      { type: '口语交际', title: '自我介绍', lesson_num: null }, { type: '习作', title: '我的“自画像”', lesson_num: null },
      { type: '语文园地', title: '语文园地七', lesson_num: null },
    ]},
    { unit_num: 8, theme: '奇妙的童话，点燃缤纷的焰火，照亮五彩的梦。', items: [
      { type: '课文', title: '宝葫芦的秘密（节选）', lesson_num: 26 }, { type: '课文', title: '巨人的花园', lesson_num: 27 },
      { type: '略读课文*', title: '海的女儿', lesson_num: 28 }, { type: '习作', title: '故事新编', lesson_num: null },
      { type: '语文园地', title: '语文园地八', lesson_num: null },
    ]},
  ],
};

const TYPE_CLASS: Record<string, string> = {
  '课文': 'text-blue-400 bg-blue-500/10', '略读课文*': 'text-gray-400 bg-gray-500/10',
  '口语交际': 'text-emerald-400 bg-emerald-500/10', '习作': 'text-rose-400 bg-rose-500/10',
  '语文园地': 'text-amber-400 bg-amber-500/10', '综合性学习': 'text-purple-400 bg-purple-500/10',
  '快乐读书吧': 'text-orange-400 bg-orange-500/10', '习作例文': 'text-pink-400 bg-pink-500/10',
};

/** 识字表 (四年级下册语文) */
const SHENZI_ROWS: { label: string; chars: { py: string; hz: string }[] }[] = [
  { label: '第1课', chars: parseChars('zá:杂 lí:篱 xú:徐 shū:疏 chú:锄 bō:剥') },
  { label: '第2课', chars: parseChars('gòu:构 guān:冠 pǔ:朴 sù:素 shuài:率 tǎng:倘 fù:附 dǎo:捣 huì:绘 xié:谐') },
  { label: '第3课', chars: parseChars('wèi:慰 jiè:藉 bǔ:卜') },
  { label: '第4课', chars: parseChars('qǐ:绮 hè:和 tán:谈') },
  { label: '第5课', chars: parseChars('hǔ:琥 pò:珀 wēng:嗡 zhī:脂 shì:拭 shèn:渗 fǔ:俯 zhá:扎 fān:番 mái:埋 péng:澎 pài:湃') },
  { label: '第6课', chars: parseChars('dùn:钝 jǐn:仅 miáo:描 suì:隧 yǎn:衍 dūn:吨 lú:颅 péng:膨 jié:捷 qī:栖 pì:辟 zhǎn:崭') },
  { label: '第7课', chars: parseChars('pīng:乒 pāng:乓 yōng:拥 jūn:菌 chòu:臭 shū:蔬 tàn:碳 ái:癌 zhèng:症 lǜ:率 jí:疾 zào:灶') },
  { label: '第8课', chars: parseChars('péng:鹏 lǎn:揽 qū:驱 jiàn:践 zhuó:着 dǎng:党 shī:施 xiè:懈 wǎn:宛 bēi:碑') },
  { label: '语文园地', chars: parseChars('bīn:宾 jí:吉 xián:咸 zhào:兆 tíng:廷 yǔ:予 zhǒng:肿 jiē:阶 zhǐ:趾 gǒng:巩 zhèng:政 liú:浏 màn:漫 tāo:涛') },
  { label: '第9课', chars: parseChars('chā:挤 chā:叉') },
  { label: '第11课', chars: parseChars('xiù:绣 xiāo:潇 zhàn:绽 méng:朦 lóng:胧 huī:晖 cháng:徜 yáng:徉') },
  { label: '第12课', chars: parseChars('xuàn:炫 gòu:垢 qiè:怯 pù:曝 chì:赤 shè:涉 yùn:晕') },
  { label: '语文园地', chars: parseChars('qū:屈 yuān:渊 mèng:孟 fǔ:甫 hán:韩 yù:愈 yǔ:禹 xī:锡 zhòng:仲 gōng:龚') },
  { label: '第13课', chars: parseChars('bǐng:虑 cèng:蹭 gǎo:稿 qiāng:腔 yāng:殃 shé:折') },
  { label: '第14课', chars: parseChars('gē:疙 da:瘩 wǔ:侮 è:恶 lóng:聋 zhuó:啄 fú:伏 hēng:哼 tí:啼 qī:凄') },
  { label: '第15课', chars: parseChars('kān:看 xiāo:嚣 háng:吭 fèi:吠 cù:促 pō:颇 shē:奢 chǐ:侈 gǒu:苟 shì:侍 kuī:窥 sì:伺 gōng:供') },
  { label: '语文园地', chars: parseChars('gān:肝 gǎn:秆 qiào:俏 qiào:峭 bǔ:哺 pǔ:浦 lún:沦 lūn:抡 huàn:涣 huàn:焕 jùn:俊 jùn:峻') },
  { label: '第16课', chars: parseChars('kuò:扩 hè:荷 chà:刹 xiāng:镶') },
  { label: '第17课', chars: parseChars('zhè:浙 cù:簇 tún:臀 qī:漆 wān:蜿 yán:蜒') },
  { label: '第18课', chars: parseChars('gōng:恭 qín:勤 yān:焉 zú:卒') },
  { label: '第19课', chars: parseChars('bā:吧 sāi:塞 wū:呜 wā:哇 kàng:炕 shuān:栓 kǔn:捆 bǎng:绑 jié:劫') },
  { label: '第21课', chars: parseChars('cuō:搓 kuí:葵 qí:祈 yí:遗 hàn:憾 wū:污 xiè:屑') },
  { label: '第22课', chars: parseChars('fú:芙 róng:蓉 luò:洛 chán:单 yàn:砚 qián:乾 kūn:坤') },
  { label: '第23课', chars: parseChars('mí:弥 mài:脉 zàng:葬 pōu:剖 luǒ:裸 qì:泣 xiōng:汹 wéi:维 hān:酣 xiè:械 gǎng:岗 zǎi:宰 qiǎn:遣') },
  { label: '第24课', chars: parseChars('yì:役 lǚ:屡 qǐ:启 cuī:摧 báo:雹 yùn:晕 táng:膛') },
  { label: '第25课', chars: parseChars('tài:泰 zhàng:杖 chǎng:敞 jū:拘 yùn:蕴') },
  { label: '语文园地', chars: parseChars('ǎi:蔼 kāng:慷 kǎi:慨 xián:贤 qī:戚 jù:惧 bīn:彬 zào:躁 fén:焚') },
  { label: '第26课', chars: parseChars('yāo:妖 jǔ:矩 guāi:乖 niǎn:撵 yā:丫 zhuài:拽 chòng:冲 shòu:瘦') },
  { label: '第27课', chars: parseChars('shuò:硕 yǔn:允 qì:砌 fù:覆 xiào:啸 lǚ:缕 lǒu:搂 jiá:颊') },
  { label: '第28课', chars: parseChars('shǐ:矢 diàn:殿 fǔ:抚 liú:硫 jīng:鲸 nì:昵 qià:恰') },
];

/* ── resolve unit structure ── */

function resolveUnits(title: string, lessons: TextbookLesson[]): UnitInfo[] {
  // Try registered units
  for (const [key, units] of Object.entries(UNIT_REGISTRY)) {
    if (title.includes(key)) return units;
  }
  // Fallback: flat list from lessons_json
  return [{
    unit_num: 1,
    theme: '',
    items: lessons.map(l => ({ type: '课文', title: l.title, lesson_num: l.lesson_num })),
  }];
}

/* ── component ── */

interface StudyDetailProps {
  embedded?: boolean;
  materialId?: string;
  onMaterialChange?: (material: StudyMaterial) => void;
  onDeleted?: (materialId: string) => void;
}

export default function StudyDetail({ embedded = false, materialId, onMaterialChange, onDeleted }: StudyDetailProps) {
  const { id: routeId } = useParams<{ id: string }>();
  const id = materialId || routeId;
  const navigate = useNavigate();
  const [material, setMaterial] = useState<StudyMaterial | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [version, setVersion] = useState<VersionTab>('parent');
  const [format, setFormat] = useState<FormatTab | null>(null);
  const [generating, setGenerating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [expandedLessons, setExpandedLessons] = useState<Set<number>>(new Set());
  const [expandedUnits, setExpandedUnits] = useState<Set<number>>(new Set());
  const [previewUrl, setPreviewUrl] = useState('');

  const loadMaterial = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const r = await apiFetch(`/api/study/${id}`);
      if (!r.ok) throw new Error('资料不存在');
      const next = await r.json();
      setMaterial(next);
      onMaterialChange?.(next);
    } catch (e: any) { setError(e.message); } finally { setLoading(false); }
  };

  useEffect(() => { loadMaterial(); }, [id]);

  useEffect(() => {
    if (!material) return;
    if (format !== null) return;
    if (material.study_type === '教材/课本' && material.source_type === 'pdf') setFormat('original');
    else setFormat('md');
  }, [material]);

  const handleGenerate = async () => {
    if (!id) return;
    setGenerating(true);
    try {
      const r = await apiFetch(`/api/study/${id}/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      if (!r.ok) throw new Error('生成失败');
      await loadMaterial();
      if (material?.study_type === '教材/课本') setFormat('original');
      else setFormat('md');
    } catch (e: any) { setError(e.message || '生成失败'); } finally { setGenerating(false); }
  };

  const handleDelete = async () => {
    if (!id) return;
    if (!window.confirm(`确定删除「${material?.title}」？此操作不可撤销。`)) return;
    setDeleting(true);
    try {
      const r = await apiFetch(`/api/study/${id}`, { method: 'DELETE' });
      if (!r.ok) throw new Error('删除失败');
      if (embedded) onDeleted?.(id);
      else navigate('/study-old');
    } catch (e: any) { setError(e.message || '删除失败'); setDeleting(false); }
  };

  const toggleLesson = (n: number) => setExpandedLessons(p => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleUnit = (n: number) => setExpandedUnits(p => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });

  const getFormatUrl = () => {
    if (!material || !id) return '';
    if (format === 'original') return `/api/study/${id}/file/${format}`;
    const paths = material.formats_json || {};
    const key = format === 'md' ? 'md' : format === 'html' ? 'html' : 'pdf';
    return paths[key] ? `/api/study/${id}/file/${format}` : '';
  };

  useEffect(() => {
    if (!id || !format || !['html', 'pdf', 'original'].includes(format)) {
      setPreviewUrl('');
      return;
    }
    const path = getFormatUrl();
    if (!path) { setPreviewUrl(''); return; }
    let active = true;
    let objectUrl = '';
    apiFetch(path)
      .then((response) => {
        if (!response.ok) throw new Error('预览加载失败');
        return response.blob();
      })
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPreviewUrl(objectUrl);
      })
      .catch(() => { if (active) setPreviewUrl(''); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [id, format, material]);

  const isReady = material?.status === 'ready' || material?.status === 'reviewed';
  const isTextbook = material?.study_type === '教材/课本';
  const hasOriginal = isTextbook && material?.source_type === 'pdf';
  const showTabs = isReady || hasOriginal;
  const genLabel = isTextbook ? '生成解读' : '生成讲稿';
  const emptyLabel = isTextbook ? '尚未生成教材解读' : '尚未生成讲题稿';
  const lessons: TextbookLesson[] = material?.lessons_json || [];
  const hasLessons = isTextbook && isReady && lessons.length > 0;
  const lessonMap = useMemo(() => {
    const m = new Map<number, TextbookLesson>();
    lessons.forEach(l => m.set(l.lesson_num, l));
    return m;
  }, [lessons]);
  const textbookUnits = useMemo(() => resolveUnits(material?.title || '', lessons), [material?.title, lessons]);
  const showAppendix = material?.subject === '语文' && hasLessons;
  const showVersionTabs = isReady && !isTextbook;
  const mdSource = version === 'child' ? (material?.child_version || '') : (material?.parent_version || '');

  if (loading) return <div className={`${embedded ? 'study-detail-legacy-embedded is-loading' : 'flex-1 bg-[#0B0C10]'} flex items-center justify-center`}><Loader2 size={24} className="animate-spin text-gray-500" /></div>;
  if (error || !material) return (
    <div className={`${embedded ? 'study-detail-legacy-embedded is-error' : 'flex-1 bg-[#0B0C10]'} flex items-center justify-center`}>
      <div className="text-center"><p className="text-red-400 text-sm">{error || '资料不存在'}</p>
        <button onClick={() => navigate(embedded ? '/study' : '/study-old')} className="mt-4 text-xs text-gray-500 hover:text-gray-300">返回辅导中心</button>
      </div>
    </div>
  );

  return (
    <div className={`${embedded ? 'study-detail-legacy-embedded is-ready' : 'flex-1 bg-[#0B0C10]'} text-white flex flex-col h-full overflow-hidden`}>
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-[1080px] mx-auto">
          <button onClick={() => navigate(embedded ? '/study' : '/study-old')} className="study-detail-back flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 mb-3 transition-colors">
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
                    {hasLessons && <span className="text-amber-400">{lessons.length} 课</span>}
                    <span>{formatTimeBeijing(material.created_at)}</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {!isReady && (
                <button onClick={handleGenerate} disabled={generating} className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors flex items-center gap-1.5 disabled:opacity-50">
                  {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                  <span className="hidden sm:inline">{genLabel}</span>
                </button>
              )}
              {isReady && (
                <button onClick={handleGenerate} disabled={generating} className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors flex items-center gap-1.5 disabled:opacity-50">
                  {generating ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}<span className="hidden sm:inline">重新生成</span>
                </button>
              )}
              <button onClick={handleDelete} disabled={deleting} className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20 transition-colors flex items-center gap-1.5 disabled:opacity-50">
                {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}<span className="hidden sm:inline">删除</span>
              </button>
            </div>
          </div>

          {/* Version tabs (非教材类) */}
          {showVersionTabs && (
            <div className="border-b border-[#2A2B30] mb-3">
              <div className="flex gap-6">
                {([['child', '👦 孩子版'], ['parent', '👨‍🏫 家长版']] as [VersionTab, string][]).map(([vid, label]) => (
                  <button key={vid} onClick={() => setVersion(vid)} className={`pb-3 text-xs font-medium transition-colors relative ${version === vid ? 'text-amber-400' : 'text-gray-500 hover:text-gray-300'}`}>
                    {label}
                    {version === vid && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-500" />}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Format tabs */}
          {showTabs && (
            <div className="border-b border-[#2A2B30]">
              <div className="flex gap-4">
                {FORMATS.filter(f => {
                  if (f.id === 'original') return isTextbook && material.source_type === 'pdf';
                  if (f.id === 'lessons') return hasLessons;
                  if (!isReady) return false;
                  return true;
                }).map(f => (
                  <button key={f.id} onClick={() => setFormat(f.id)} className={`inline-flex items-center gap-1.5 pb-3 text-xs font-medium transition-colors relative ${format === f.id ? 'text-amber-400' : 'text-gray-500 hover:text-gray-300'}`}>
                    {f.icon}{f.label}
                    {format === f.id && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-500" />}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-[1080px] mx-auto pt-4">
          {!showTabs ? (
            <div className="text-center text-gray-600 py-16">
              <Sparkles size={48} className="mx-auto mb-4 opacity-40" />
              <p className="text-sm">{emptyLabel}</p>
              <p className="text-xs mt-1 text-gray-700">点击上方「{genLabel}」开始 AI 生成</p>
            </div>
          ) : format === 'lessons' ? (
            <>
              <div className="space-y-5">
                <div className="flex items-center gap-2 mb-2">
                  <BookOpen size={16} className="text-amber-400" />
                  <span className="text-sm font-medium text-gray-300">教材结构</span>
                  <span className="text-xs text-gray-600">{textbookUnits.length} 单元 · {lessons.length} 课</span>
                </div>
                {textbookUnits.map(unit => {
                  const isOpen = expandedUnits.has(unit.unit_num);
                  return (
                    <div key={unit.unit_num} className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
                      <button onClick={() => toggleUnit(unit.unit_num)} className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#1A1B20] transition-colors">
                        <span className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-400 text-sm font-bold flex items-center justify-center shrink-0">{unit.unit_num}</span>
                        <div className="min-w-0 flex-1"><span className="font-medium text-sm">第{unit.unit_num}单元</span>{unit.theme && <p className="text-xs text-gray-500 truncate mt-0.5">{unit.theme}</p>}</div>
                        {isOpen ? <ChevronDown size={16} className="text-gray-500 shrink-0" /> : <ChevronRight size={16} className="text-gray-500 shrink-0" />}
                      </button>
                      {isOpen && (
                        <div className="border-t border-[#2A2B30]">
                          {unit.items.map((item, idx) => {
                            const l = item.lesson_num ? lessonMap.get(item.lesson_num) : null;
                            const isExp = item.lesson_num ? expandedLessons.has(item.lesson_num) : false;
                            const ts = TYPE_CLASS[item.type] || 'text-gray-400 bg-gray-500/10';
                            return (
                              <div key={idx} className="border-b border-[#2A2B30] last:border-b-0">
                                {l ? (
                                  <>
                                    <button onClick={() => item.lesson_num && toggleLesson(item.lesson_num)} className="w-full flex items-center gap-3 px-5 py-2.5 text-left hover:bg-[#1A1B20] transition-colors">
                                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${ts}`}>{item.type}</span>
                                      <span className="text-sm flex-1 truncate">{item.title}</span>
                                      <span className="text-xs text-gray-600 mr-1">第{item.lesson_num}课</span>
                                      {isExp ? <ChevronDown size={14} className="text-gray-500 shrink-0" /> : <ChevronRight size={14} className="text-gray-500 shrink-0" />}
                                    </button>
                                    {isExp && <div className="border-t border-[#2A2B30] px-5 py-5" dangerouslySetInnerHTML={{ __html: mdToHtml(l.analysis_md || '（暂无解析内容）') }} />}
                                  </>
                                ) : (
                                  <div className="flex items-center gap-3 px-5 py-2.5"><span className={`px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${ts}`}>{item.type}</span><span className="text-sm text-gray-400">{item.title}</span></div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* 附录（仅语文教材） */}
              {showAppendix && (
                <div className="mt-6 pt-4 border-t border-[#2A2B30]">
                  <div className="flex items-center gap-2 mb-3"><BookOpen size={16} className="text-gray-500" /><span className="text-sm font-medium text-gray-400">附录</span></div>
                  <div className="space-y-2">
                    {([
                      { key: 100, icon: '字', label: '识字表', render: () => (
                        <div className="border-t border-[#2A2B30] px-4 py-4 space-y-3">
                          {SHENZI_ROWS.map((row, ri) => (
                            <div key={ri} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                              <span className="text-[11px] text-gray-500 w-12 shrink-0">{row.label}</span>
                              <span className="inline-flex flex-wrap gap-x-1.5 gap-y-0.5">
                                {row.chars.map((c, ci) => (
                                  <span key={ci} className="inline-flex flex-col items-center" style={{ minWidth: '2em' }}>
                                    <span className="text-[11px] text-gray-400 leading-tight">{c.py}</span>
                                    <span className="text-sm leading-tight">{c.hz}</span>
                                  </span>
                                ))}
                              </span>
                            </div>
                          ))}
                          <p className="text-[11px] text-gray-600">（共250个生字，蓝色字为多音字）</p>
                        </div>
                      )},
                      { key: 101, icon: '写', label: '写字表', render: () => (
                        <div className="border-t border-[#2A2B30] px-5 py-4"><pre className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap font-sans">杂 稀 篱 蜻 蜓 蝶 宿 徐 疏 茅 檐 翁 笼 赖 剥{'\n'}构 饰 蹲 凤 序 例 率 觅 耸 踏 倘 绘 谐 寄 眠{'\n'}慰 藉 卜 锐 滩 帐 烁 蝙 蝠 霸 鹰{'\n'}怒 吼 脂 拭 餐 划 晌 辣 渗 挣 番 埋 刷 测 详{'\n'}笨 钝 鸽 毫 凌 末 描 隧 态 吨 颅 膨 肢 翼 辟{'\n'}纳 拥 箱 臭 蔬 碳 钢 隐 健 康 胞 疾 防 灶 需{'\n'}繁 漫 灭 藤 萝 膝 涛 躲  瓶 挤 叉 挥{'\n'}桦 涂 茸 绣 潇 穗 朦 胧 寂 霞 抹{'\n'}忧 虑 贪 职 屏 蹭 稿 腔 解 闷 蛇 遭 殃 盆 勃{'\n'}讨 厌 坝 忠 毒 绩 孵 警 戒 歪 咕 汤 掘 伏 啼{'\n'}吠 促 颇 剧 苟 譬 侍 馆 附 脾 敏 捷 昂 供 添{'\n'}扩 范 努 刹 烂 替 镶 紫 仅{'\n'}浙 罗 杜 鹃 窄 郁 肩 臀 移 额 陆 乳 笋 端 源{'\n'}囊 萤 恭 勤 博 贫 焉 逢 卒{'\n'}晋 炕 铅 鸣 哩 栓 胳 膊 劫 绸 扒 敌 尸 趁 慌{'\n'}芙 蓉 洛 壶 雁 砚 乾 坤{'\n'}伦 腹 剖 窟 窿 混 嘶 维 秩 岗 宰 措 遣 践{'\n'}介 绍 妖 矩 乖 撵 烫 丫 拽 福 舔 葵 瘦 棒 罢{'\n'}硕 允 砌 牌 禁 惩 踪 啸 私 颊 拆{'\n\n'}（共250个字）</pre></div>
                      )},
                      { key: 102, icon: '词', label: '词语表', render: () => (
                        <div className="border-t border-[#2A2B30] px-5 py-4"><pre className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap font-sans">屋檐 构成 装饰 顺序 华丽 独特 照例 率领 踏步 倘若 和谐 催眠曲 甜蜜 梦乡{'\n'}慰藉 扫荡 威力 锐利 河滩 帐子 闪烁 奇幻 蝙蝠 霸气 猫头鹰 复杂{'\n'}怒吼 松脂 拂拭 灰尘 美餐 晌午 热辣辣 淹没 挣扎 成千上万 冲刷 断绝 推测 详细 情形{'\n'}笨重 恐龙 迟钝 鸽子 凌空 根据 末期 描绘 隧道 形态 膨大 前肢 具备 开辟 脱离{'\n'}纳米 拥有 冰箱 功能 蔬菜 材料 无能为力 钢铁 隐形 健康 细胞 疾病 预防 病灶 需要 深刻{'\n'}繁星 藤萝 波涛 墨绿 嫩绿 集中 交叉 教练 指挥 整齐 节拍{'\n'}白桦 毛茸茸 朦胧 寂静 屏息 稿纸 梅花 解闷{'\n'}呼唤 响动 尽职 勇猛 淘气 满月 心事 忠厚 毒手{'\n'}讨厌 理由 反抗 成绩 警戒 预备 汤圆{'\n'}高傲 即将 姿态 狂吠 局促 京剧 一丝不苟 譬如 侍候 饭馆 附近 脾气 敏捷 空空如也 昂首 供养{'\n'}清静 扩大 范围 努力 刹那 夺目 分辨 灿烂 不仅 聚集 脚跟{'\n'}杜鹃 气势 拥挤 心情 移动 昏暗 挤压 额角 登陆 宽广 石笋 石钟乳 观赏{'\n'}芦花 发愣 铅笔 枪栓 胳膊 劫难 鬼脸 戒指 防备 慌忙 绸子 敌人 尸首 凌晨{'\n'}窟窿 混乱 维持 秩序 岗位 行驶 主宰 调遣 践行 声明 劈面{'\n'}介绍 妖怪 规矩 向日葵 丰硕 允许 禁止 踪迹 呼啸 幸福{'\n'}柔嫩 始终 吼叫 自私 举动 脸颊 凶狠 拆除</pre></div>
                      )},
                    ] as const).map(({ key, icon, label, render }) => (
                      <div key={key} className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
                        <button onClick={() => toggleUnit(key)} className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#1A1B20] transition-colors">
                          <span className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 text-xs font-bold flex items-center justify-center shrink-0">{icon}</span>
                          <span className="text-sm font-medium flex-1">{label}</span>
                          {expandedUnits.has(key) ? <ChevronDown size={14} className="text-gray-500 shrink-0" /> : <ChevronRight size={14} className="text-gray-500 shrink-0" />}
                        </button>
                        {expandedUnits.has(key) && render()}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              {format === 'md' && (
                <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-6" dangerouslySetInnerHTML={{ __html: mdToHtml(mdSource || '加载中...') }} />
              )}
              {(format === 'html' || format === 'pdf' || format === 'original') && (
                <div className="study-preview-frame bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden" style={{ height: 'calc(100vh - 220px)' }}>
                  {previewUrl ? <iframe src={previewUrl} className="w-full h-full border-0" title={`${format} Preview`} sandbox={format === 'html' ? 'allow-same-origin' : undefined} /> : <div className="grid h-full place-items-center text-xs text-gray-500"><Loader2 size={18} className="animate-spin" /></div>}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
