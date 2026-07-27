import { BookOpen, ChevronDown, ChevronRight } from 'lucide-react';
import {
  mdToHtml,
  SHENZI_ROWS,
  TYPE_CLASS,
  type TextbookLesson,
  type UnitInfo,
} from './studyDetailFormat';

interface StudyLessonPanelProps {
  lessons: TextbookLesson[];
  lessonMap: Map<number, TextbookLesson>;
  textbookUnits: UnitInfo[];
  expandedLessons: Set<number>;
  expandedUnits: Set<number>;
  showAppendix: boolean;
  onToggleUnit: (unitNumber: number) => void;
  onToggleLesson: (lessonNumber: number) => void;
}

export default function StudyLessonPanel({
  lessons, lessonMap, textbookUnits, expandedLessons, expandedUnits, showAppendix,
  onToggleUnit, onToggleLesson,
}: StudyLessonPanelProps) {
  return <>
    <div className="space-y-5">
      <div className="flex items-center gap-2 mb-2">
        <BookOpen size={16} className="text-amber-400" />
        <span className="text-sm font-medium text-gray-300">教材结构</span>
        <span className="text-xs text-gray-600">{textbookUnits.length} 单元 · {lessons.length} 课</span>
      </div>
      {textbookUnits.map((unit) => {
        const isOpen = expandedUnits.has(unit.unit_num);
        return <div key={unit.unit_num} className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
          <button onClick={() => onToggleUnit(unit.unit_num)} className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#1A1B20] transition-colors">
            <span className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-400 text-sm font-bold flex items-center justify-center shrink-0">{unit.unit_num}</span>
            <div className="min-w-0 flex-1"><span className="font-medium text-sm">第{unit.unit_num}单元</span>{unit.theme && <p className="text-xs text-gray-500 truncate mt-0.5">{unit.theme}</p>}</div>
            {isOpen ? <ChevronDown size={16} className="text-gray-500 shrink-0" /> : <ChevronRight size={16} className="text-gray-500 shrink-0" />}
          </button>
          {isOpen && <div className="border-t border-[#2A2B30]">
            {unit.items.map((item, index) => {
              const lesson = item.lesson_num ? lessonMap.get(item.lesson_num) : null;
              const isExpanded = item.lesson_num ? expandedLessons.has(item.lesson_num) : false;
              const typeClass = TYPE_CLASS[item.type] || 'text-gray-400 bg-gray-500/10';
              return <div key={index} className="border-b border-[#2A2B30] last:border-b-0">
                {lesson ? <>
                  <button onClick={() => item.lesson_num && onToggleLesson(item.lesson_num)} className="w-full flex items-center gap-3 px-5 py-2.5 text-left hover:bg-[#1A1B20] transition-colors">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${typeClass}`}>{item.type}</span>
                    <span className="text-sm flex-1 truncate">{item.title}</span>
                    <span className="text-xs text-gray-600 mr-1">第{item.lesson_num}课</span>
                    {isExpanded ? <ChevronDown size={14} className="text-gray-500 shrink-0" /> : <ChevronRight size={14} className="text-gray-500 shrink-0" />}
                  </button>
                  {isExpanded && <div className="border-t border-[#2A2B30] px-5 py-5" dangerouslySetInnerHTML={{ __html: mdToHtml(lesson.analysis_md || '（暂无解析内容）') }} />}
                </> : <div className="flex items-center gap-3 px-5 py-2.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${typeClass}`}>{item.type}</span>
                  <span className="text-sm text-gray-400">{item.title}</span>
                </div>}
              </div>;
            })}
          </div>}
        </div>;
      })}
    </div>

    {showAppendix && <div className="mt-6 pt-4 border-t border-[#2A2B30]">
      <div className="flex items-center gap-2 mb-3"><BookOpen size={16} className="text-gray-500" /><span className="text-sm font-medium text-gray-400">附录</span></div>
      <div className="space-y-2">
        {([
          { key: 100, icon: '字', label: '识字表', render: () => <div className="border-t border-[#2A2B30] px-4 py-4 space-y-3">
            {SHENZI_ROWS.map((row, rowIndex) => <div key={rowIndex} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-[11px] text-gray-500 w-12 shrink-0">{row.label}</span>
              <span className="inline-flex flex-wrap gap-x-1.5 gap-y-0.5">
                {row.chars.map((character, characterIndex) => <span key={characterIndex} className="inline-flex flex-col items-center" style={{ minWidth: '2em' }}>
                  <span className="text-[11px] text-gray-400 leading-tight">{character.py}</span>
                  <span className="text-sm leading-tight">{character.hz}</span>
                </span>)}
              </span>
            </div>)}
            <p className="text-[11px] text-gray-600">（共250个生字，蓝色字为多音字）</p>
          </div> },
          { key: 101, icon: '写', label: '写字表', render: () => <div className="border-t border-[#2A2B30] px-5 py-4"><pre className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap font-sans">杂 稀 篱 蜻 蜓 蝶 宿 徐 疏 茅 檐 翁 笼 赖 剥{'\n'}构 饰 蹲 凤 序 例 率 觅 耸 踏 倘 绘 谐 寄 眠{'\n'}慰 藉 卜 锐 滩 帐 烁 蝙 蝠 霸 鹰{'\n'}怒 吼 脂 拭 餐 划 晌 辣 渗 挣 番 埋 刷 测 详{'\n'}笨 钝 鸽 毫 凌 末 描 隧 态 吨 颅 膨 肢 翼 辟{'\n'}纳 拥 箱 臭 蔬 碳 钢 隐 健 康 胞 疾 防 灶 需{'\n'}繁 漫 灭 藤 萝 膝 涛 躲  瓶 挤 叉 挥{'\n'}桦 涂 茸 绣 潇 穗 朦 胧 寂 霞 抹{'\n'}忧 虑 贪 职 屏 蹭 稿 腔 解 闷 蛇 遭 殃 盆 勃{'\n'}讨 厌 坝 忠 毒 绩 孵 警 戒 歪 咕 汤 掘 伏 啼{'\n'}吠 促 颇 剧 苟 譬 侍 馆 附 脾 敏 捷 昂 供 添{'\n'}扩 范 努 刹 烂 替 镶 紫 仅{'\n'}浙 罗 杜 鹃 窄 郁 肩 臀 移 额 陆 乳 笋 端 源{'\n'}囊 萤 恭 勤 博 贫 焉 逢 卒{'\n'}晋 炕 铅 鸣 哩 栓 胳 膊 劫 绸 扒 敌 尸 趁 慌{'\n'}芙 蓉 洛 壶 雁 砚 乾 坤{'\n'}伦 腹 剖 窟 窿 混 嘶 维 秩 岗 宰 措 遣 践{'\n'}介 绍 妖 矩 乖 撵 烫 丫 拽 福 舔 葵 瘦 棒 罢{'\n'}硕 允 砌 牌 禁 惩 踪 啸 私 颊 拆{'\n\n'}（共250个字）</pre></div> },
          { key: 102, icon: '词', label: '词语表', render: () => <div className="border-t border-[#2A2B30] px-5 py-4"><pre className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap font-sans">屋檐 构成 装饰 顺序 华丽 独特 照例 率领 踏步 倘若 和谐 催眠曲 甜蜜 梦乡{'\n'}慰藉 扫荡 威力 锐利 河滩 帐子 闪烁 奇幻 蝙蝠 霸气 猫头鹰 复杂{'\n'}怒吼 松脂 拂拭 灰尘 美餐 晌午 热辣辣 淹没 挣扎 成千上万 冲刷 断绝 推测 详细 情形{'\n'}笨重 恐龙 迟钝 鸽子 凌空 根据 末期 描绘 隧道 形态 膨大 前肢 具备 开辟 脱离{'\n'}纳米 拥有 冰箱 功能 蔬菜 材料 无能为力 钢铁 隐形 健康 细胞 疾病 预防 病灶 需要 深刻{'\n'}繁星 藤萝 波涛 墨绿 嫩绿 集中 交叉 教练 指挥 整齐 节拍{'\n'}白桦 毛茸茸 朦胧 寂静 屏息 稿纸 梅花 解闷{'\n'}呼唤 响动 尽职 勇猛 淘气 满月 心事 忠厚 毒手{'\n'}讨厌 理由 反抗 成绩 警戒 预备 汤圆{'\n'}高傲 即将 姿态 狂吠 局促 京剧 一丝不苟 譬如 侍候 饭馆 附近 脾气 敏捷 空空如也 昂首 供养{'\n'}清静 扩大 范围 努力 刹那 夺目 分辨 灿烂 不仅 聚集 脚跟{'\n'}杜鹃 气势 拥挤 心情 移动 昏暗 挤压 额角 登陆 宽广 石笋 石钟乳 观赏{'\n'}芦花 发愣 铅笔 枪栓 胳膊 劫难 鬼脸 戒指 防备 慌忙 绸子 敌人 尸首 凌晨{'\n'}窟窿 混乱 维持 秩序 岗位 行驶 主宰 调遣 践行 声明 劈面{'\n'}介绍 妖怪 规矩 向日葵 丰硕 允许 禁止 踪迹 呼啸 幸福{'\n'}柔嫩 始终 吼叫 自私 举动 脸颊 凶狠 拆除</pre></div> },
        ] as const).map(({ key, icon, label, render }) => <div key={key} className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
          <button onClick={() => onToggleUnit(key)} className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#1A1B20] transition-colors">
            <span className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 text-xs font-bold flex items-center justify-center shrink-0">{icon}</span>
            <span className="text-sm font-medium flex-1">{label}</span>
            {expandedUnits.has(key) ? <ChevronDown size={14} className="text-gray-500 shrink-0" /> : <ChevronRight size={14} className="text-gray-500 shrink-0" />}
          </button>
          {expandedUnits.has(key) && render()}
        </div>)}
      </div>
    </div>}
  </>;
}
