import { useEffect, useId, useRef, useState, type LucideIcon } from 'react';
import {
  BrainCircuit,
  Check,
  ChevronDown,
  FileUp,
  Gauge,
  Link2,
  Play,
  Sparkles,
  Tags,
  Workflow,
  X,
} from 'lucide-react';
import CinematicScene from '../components/cinematic/CinematicScene';
import KiMagicBentoFrame from '../components/react-bits/KiMagicBentoFrame';
import '../components/cinematic/cinematic.css';
import './DockPopupVisualDemo.css';

type DemoStatus = 'idle' | 'busy' | 'success';
type ModeValue = 'auto' | 'fast' | 'deep';

const MODE_OPTIONS: Array<{
  value: ModeValue;
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  { value: 'auto', label: '自动识别', description: '按内容类型匹配处理链路', icon: Sparkles },
  { value: 'fast', label: '快速解析', description: '优先完成转写与结构提取', icon: Gauge },
  { value: 'deep', label: '深度处理', description: '启用完整分析与知识沉淀', icon: BrainCircuit },
];

function useDemoAction() {
  const [status, setStatus] = useState<DemoStatus>('idle');
  const timerRef = useRef<number | null>(null);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  function run() {
    if (status === 'busy') return;
    setStatus('busy');
    timerRef.current = window.setTimeout(() => setStatus('success'), 720);
  }

  return { status, run };
}

function ModeSelect() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState<ModeValue>('auto');
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();
  const selected = MODE_OPTIONS.find((option) => option.value === value) ?? MODE_OPTIONS[0];
  const SelectedIcon = selected.icon;

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  return (
    <div className={`dock-popup-study__mode-select ${open ? 'is-open' : ''}`} ref={rootRef} data-bento-suspend>
      <button
        className="dock-popup-study__mode-trigger"
        type="button"
        role="combobox"
        aria-controls={listboxId}
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen((current) => !current)}
      >
        <SelectedIcon />
        <span>{selected.label}</span>
        <ChevronDown className="dock-popup-study__mode-chevron" />
      </button>

      {open && (
        <div className="dock-popup-study__mode-menu" id={listboxId} role="listbox" aria-label="处理模式">
          {MODE_OPTIONS.map((option) => {
            const OptionIcon = option.icon;
            const isSelected = option.value === value;
            return (
              <button
                className={`dock-popup-study__mode-option ${isSelected ? 'is-selected' : ''}`}
                type="button"
                role="option"
                aria-selected={isSelected}
                key={option.value}
                onClick={() => {
                  setValue(option.value);
                  setOpen(false);
                }}
              >
                <OptionIcon />
                <span><b>{option.label}</b><small>{option.description}</small></span>
                <Check className="dock-popup-study__mode-check" />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function PopupStudy() {
  const { status, run } = useDemoAction();
  const [tab, setTab] = useState<'douyin' | 'file'>('douyin');

  return (
    <div className="dock-popup-study__interaction-zone">
      <KiMagicBentoFrame className={`dock-popup-study__window-bento-grid is-${status}`} cardClassName="dock-popup-study__window-bento-card">
          <article className={`dock-popup-study__surface dock-popup-study__surface--bento is-${status}`}>
            <button className="dock-popup-study__close" type="button" aria-label="关闭演示"><X /></button>

            <header className="dock-popup-study__popup-header">
              <span>GLOBAL ACCESS / 01</span>
              <div className="dock-popup-study__popup-title"><Sparkles /><h2>内容接入</h2></div>
              <p>将外部信号送入知几处理轨道</p>
            </header>

            <nav className="dock-popup-study__tabs" aria-label="接入方式">
              <button className={tab === 'douyin' ? 'is-active' : ''} onClick={() => setTab('douyin')}><span className="dock-popup-study__tab-icon is-violet"><Link2 /></span><span>抖音分享</span></button>
              <button className={tab === 'file' ? 'is-active' : ''} onClick={() => setTab('file')}><span className="dock-popup-study__tab-icon is-cyan"><FileUp /></span><span>文件上传</span></button>
            </nav>

            <div className="dock-popup-study__content">
              <label className="dock-popup-study__plane--primary">
                <span className="dock-popup-study__field-label is-violet">{tab === 'douyin' ? <Link2 /> : <FileUp />}<span>{tab === 'douyin' ? '分享文本' : '本地文件'}</span></span>
                {tab === 'douyin'
                  ? <textarea defaultValue="3.64 复制打开抖音，查看趋势信号与原始内容……" aria-label="分享文本" />
                  : <span className="dock-popup-study__drop"><FileUp /><b>选择文档、音频或视频</b><small>PDF · DOCX · MP4 · MP3</small></span>}
              </label>

              <div className="dock-popup-study__plane--options">
                <label><span className="dock-popup-study__field-label is-gold"><Tags /><span>分类</span></span><input defaultValue="前瞻" /></label>
                <div>
                  <span className="dock-popup-study__field-label is-cyan"><Workflow /><span>处理模式</span></span>
                  <ModeSelect />
                </div>
              </div>

              <button className="dock-popup-study__submit" type="button" onClick={run}>
                {status === 'success' ? <Check /> : status === 'busy' ? <Sparkles /> : <Play />}
                <span>{status === 'success' ? '已进入处理队列' : status === 'busy' ? '正在建立处理轨道' : tab === 'douyin' ? '提交解析' : '上传文件'}</span>
                <small className="dock-popup-study__submit-state">{status === 'success' ? 'DONE' : status === 'busy' ? 'LINKING' : 'ENTER'}</small>
              </button>
            </div>
          </article>
      </KiMagicBentoFrame>
    </div>
  );
}

export default function DockPopupVisualDemo() {
  return (
    <main className="dock-popup-study">
      <CinematicScene focus={0} variant="ingest" laserPrimary />
      <div className="dock-popup-study__film" aria-hidden="true" />
      <header className="dock-popup-study__heading">
        <div><span>KI / POPUP VISUAL SYSTEM</span><h1>全局弹窗视觉系统</h1></div>
        <p>整窗 Magic Bento 统一承载空间反馈，内部表单保持连续、紧凑与稳定。</p>
      </header>
      <div className="dock-popup-study__gallery">
        <PopupStudy />
      </div>
    </main>
  );
}
