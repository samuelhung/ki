import type React from 'react';
import { FileCode2, FileType2, Globe, Layers } from 'lucide-react';
import { escapeHtml, sanitizeHtml } from '../../safeHtml';

export interface TextbookLesson {
  lesson_num: number; title: string; content: string; analysis_md: string;
}
export interface UnitItem { type: string; title: string; lesson_num: number | null; }
export interface UnitInfo { unit_num: number; theme: string; items: UnitItem[]; }
export type VersionTab = 'child' | 'parent';
export type FormatTab = 'md' | 'html' | 'pdf' | 'original' | 'lessons';

export interface StudyMaterial {
  id: string; subject: string; grade: string; textbook: string; study_type: string;
  title: string; source_type: string; raw_content: string;
  child_version: string; parent_version: string;
  formats_json: Record<string, string>; lessons_json: TextbookLesson[];
  status: string; score: number | null; is_correct: number | null;
  mistake_tags: string[]; created_at: string; updated_at: string;
  review_content?: string;
}

export function parseChars(s: string): { py: string; hz: string }[] {
  if (!s.trim()) return [];
  return s.split(/\s+/).map((pair) => {
    const idx = pair.indexOf(':');
    return { py: pair.slice(0, idx), hz: pair.slice(idx + 1) };
  });
}

export function mdToHtml(md: string): string {
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
      const match = line.match(/^(\d+)\.\s(.+)/);
      if (match) html += `<p class="mb-1 text-sm text-gray-300 leading-relaxed pl-4"><span class="text-gray-500 font-mono text-xs mr-1">${match[1]}.</span>${bold(match[2])}</p>`;
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

export const FORMATS: { id: FormatTab; label: string; icon: React.ReactNode }[] = [
  { id: 'md', label: 'MD', icon: <FileCode2 size={14} className="text-blue-400" /> },
  { id: 'html', label: 'HTML', icon: <Globe size={14} className="text-emerald-400" /> },
  { id: 'pdf', label: 'PDF', icon: <FileType2 size={14} className="text-rose-400" /> },
  { id: 'original', label: '原始PDF', icon: <FileType2 size={14} className="text-amber-400" /> },
  { id: 'lessons', label: '课文目录', icon: <Layers size={14} className="text-purple-400" /> },
];

export const UNIT_REGISTRY: Record<string, UnitInfo[]> = {
  '四年级下册语文': [
    { unit_num: 1, theme: '纯朴的乡村，一道独特的风景，一幅和谐的画卷。', items: [
      { type: '课文', title: '古诗词三首', lesson_num: 1 }, { type: '课文', title: '乡下人家', lesson_num: 2 },
      { type: '课文', title: '天窗', lesson_num: 3 }, { type: '略读课文*', title: '三月桃花水', lesson_num: 4 },
      { type: '口语交际', title: '转述', lesson_num: null }, { type: '习作', title: '我的乐园', lesson_num: null },
      { type: '语文园地', title: '语文园地一', lesson_num: null },
    ] },
    { unit_num: 2, theme: '蓝天森林大海，蕴藏自然的奥秘；过去现在未来，述说科技的精彩。', items: [
      { type: '课文', title: '琥珀', lesson_num: 5 }, { type: '课文', title: '飞向蓝天的恐龙', lesson_num: 6 },
      { type: '课文', title: '纳米技术就在我们身边', lesson_num: 7 }, { type: '略读课文*', title: '千年梦圆在今朝', lesson_num: 8 },
      { type: '口语交际', title: '说新闻', lesson_num: null }, { type: '习作', title: '我的奇思妙想', lesson_num: null },
      { type: '语文园地', title: '语文园地二', lesson_num: null }, { type: '快乐读书吧', title: '十万个为什么', lesson_num: null },
    ] },
    { unit_num: 3, theme: '诗歌，让我们用美丽的眼睛看世界。', items: [
      { type: '课文', title: '短诗三首', lesson_num: 9 }, { type: '课文', title: '绿', lesson_num: 10 },
      { type: '课文', title: '白桦', lesson_num: 11 }, { type: '略读课文*', title: '在天晴了的时候', lesson_num: 12 },
      { type: '综合性学习', title: '轻叩诗歌大门', lesson_num: null }, { type: '语文园地', title: '语文园地三', lesson_num: null },
    ] },
    { unit_num: 4, theme: '奔跑飞舞，驻足凝望——可爱的动物，我们的好朋友。', items: [
      { type: '课文', title: '猫', lesson_num: 13 }, { type: '课文', title: '母鸡', lesson_num: 14 },
      { type: '课文', title: '白鹅', lesson_num: 15 }, { type: '习作', title: '我的动物朋友', lesson_num: null },
      { type: '语文园地', title: '语文园地四', lesson_num: null },
    ] },
    { unit_num: 5, theme: '妙笔写美景，巧手著奇观。', items: [
      { type: '课文', title: '海上日出', lesson_num: 16 }, { type: '课文', title: '记金华的双龙洞', lesson_num: 17 },
      { type: '习作例文', title: '颐和园', lesson_num: null }, { type: '习作例文', title: '七月的天山', lesson_num: null },
      { type: '习作', title: '游____', lesson_num: null },
    ] },
    { unit_num: 6, theme: '深深浅浅的脚印，写满成长的故事。', items: [
      { type: '课文', title: '文言文二则', lesson_num: 18 }, { type: '课文', title: '小英雄雨来（节选）', lesson_num: 19 },
      { type: '略读课文*', title: '我们家的男子汉', lesson_num: 20 }, { type: '略读课文*', title: '芦花鞋', lesson_num: 21 },
      { type: '口语交际', title: '朋友相处的秘诀', lesson_num: null }, { type: '习作', title: '我学会了____', lesson_num: null },
      { type: '语文园地', title: '语文园地六', lesson_num: null },
    ] },
    { unit_num: 7, theme: '没有伟大的品格，就没有伟大的人。', items: [
      { type: '课文', title: '古诗三首', lesson_num: 22 }, { type: '课文', title: '“诺曼底号”遇难记', lesson_num: 23 },
      { type: '略读课文*', title: '黄继光', lesson_num: 24 }, { type: '略读课文*', title: '挑山工', lesson_num: 25 },
      { type: '口语交际', title: '自我介绍', lesson_num: null }, { type: '习作', title: '我的“自画像”', lesson_num: null },
      { type: '语文园地', title: '语文园地七', lesson_num: null },
    ] },
    { unit_num: 8, theme: '奇妙的童话，点燃缤纷的焰火，照亮五彩的梦。', items: [
      { type: '课文', title: '宝葫芦的秘密（节选）', lesson_num: 26 }, { type: '课文', title: '巨人的花园', lesson_num: 27 },
      { type: '略读课文*', title: '海的女儿', lesson_num: 28 }, { type: '习作', title: '故事新编', lesson_num: null },
      { type: '语文园地', title: '语文园地八', lesson_num: null },
    ] },
  ],
};

export const TYPE_CLASS: Record<string, string> = {
  '课文': 'text-blue-400 bg-blue-500/10', '略读课文*': 'text-gray-400 bg-gray-500/10',
  '口语交际': 'text-emerald-400 bg-emerald-500/10', '习作': 'text-rose-400 bg-rose-500/10',
  '语文园地': 'text-amber-400 bg-amber-500/10', '综合性学习': 'text-purple-400 bg-purple-500/10',
  '快乐读书吧': 'text-orange-400 bg-orange-500/10', '习作例文': 'text-pink-400 bg-pink-500/10',
};

export const SHENZI_ROWS: { label: string; chars: { py: string; hz: string }[] }[] = [
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

export function resolveUnits(title: string, lessons: TextbookLesson[]): UnitInfo[] {
  for (const [key, units] of Object.entries(UNIT_REGISTRY)) {
    if (title.includes(key)) return units;
  }
  return [{
    unit_num: 1,
    theme: '',
    items: lessons.map((lesson) => ({ type: '课文', title: lesson.title, lesson_num: lesson.lesson_num })),
  }];
}
