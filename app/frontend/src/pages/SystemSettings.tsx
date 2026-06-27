import React, { useState, useEffect } from 'react';
import { Settings, Save, Wifi, WifiOff, Globe, Server, Activity } from 'lucide-react';
import { getBackendUrl, setBackendUrl } from '../api';
import { APP_VERSION } from '../constants';
import { apiFetch } from '../api';
import { NumberInput, PromptSection, TaskRow, Toggle, type TaskConfig } from '../components/SystemSettingsControls';

// ── 统一使用 APP_VERSION 作为客户端版本号显示 ──
const CLIENT_VERSION = APP_VERSION;

interface ModuleConfig {
  [task: string]: TaskConfig;
}

interface SystemConfig {
  general: {
    model: string;
    base_url: string;
    api_key: string;
    disk_cache: boolean;
    default_temperature: number;
    default_max_tokens: number;
    default_thinking: boolean;
    reasoning_effort: string;
  };
  ingest_pipeline: ModuleConfig;
  series: ModuleConfig;
  brainstorm: ModuleConfig;
  digest_briefing: ModuleConfig;
  tasks: ModuleConfig;
  concept: ModuleConfig;
  knowledge_graph: ModuleConfig;
}

/* ── 中文翻译 ── */
const TAB_LABELS: Record<string, string> = {
  params_info: '参数说明',
  general: '通用配置',
  ingest_pipeline: '内容采集',
  series: '专题引擎',
  brainstorm: '头脑风暴',
  digest_briefing: '摘要快报',
  tasks: '待办事务',
  concept: '概念沉淀',
  knowledge_graph: '知识图谱',
  connection: '连接',
};

const TASK_NAMES: Record<string, Record<string, string>> = {
  ingest_pipeline: {
    summarize: '内容总结', classify: '认知分类', tag: '实体标注', translate: '英文翻译',
  },
  series: {
    discover: '发现专题', intro: '专题导言', summary: '结构化总结', paper: '论文分析', auto_suggest: '即时匹配',
  },
  brainstorm: {
    answer: '综合回答', summary: '对话总结', contemplate: '凝神静思', concept_extract: '概念提取',
  },
  digest_briefing: {
    digest: '每日摘要', briefing_quick: '即时快报', briefing_daily: '深度日报',
  },
  tasks: {
    judge: '事务判断',
  },
  concept: {
    auto_complete: 'AI 补全',
  },
  knowledge_graph: {
    entity_insight: '实体深度分析',
  },
};

const SUGGESTIONS: Record<string, Record<string, { temp: string; tokens: string }>> = {
  ingest_pipeline: {
    summarize:     { temp: '0.1–0.3', tokens: '3072' },
    classify:      { temp: '0.1',     tokens: '256' },
    tag:           { temp: '0.1',     tokens: '512' },
    translate:     { temp: '0.1',     tokens: '2048' },
  },
  series: {
    discover:      { temp: '0.3–0.5', tokens: '4096' },
    intro:         { temp: '0.3–0.5', tokens: '1024' },
    summary:       { temp: '0.2–0.3', tokens: '3072' },
    paper:         { temp: '0.4–0.6', tokens: '16384' },
    auto_suggest:  { temp: '0.1',     tokens: '256' },
  },
  brainstorm: {
    answer:        { temp: '0.2–0.4', tokens: '8192' },
    summary:       { temp: '0.2–0.3', tokens: '3000' },
    contemplate:   { temp: '0.2–0.3', tokens: '800' },
    concept_extract:{ temp: '0.1',    tokens: '2048' },
  },
  digest_briefing: {
    digest:        { temp: '0.2–0.3', tokens: '8192' },
    briefing_quick:{ temp: '0.2–0.3', tokens: '3072' },
    briefing_daily:{ temp: '0.2–0.3', tokens: '8192' },
  },
  tasks: {
    judge:         { temp: '0.3–0.4', tokens: '16384' },
  },
  concept: {
    auto_complete: { temp: '0.2–0.3', tokens: '1500' },
  },
  knowledge_graph: {
    entity_insight: { temp: '0.4–0.6', tokens: '2048' },
  },
};

/* ── 主组件 ── */

/** Format seconds into human-readable uptime string. */
function formatUptime(sec: number): string {
  if (sec < 60) return `${Math.floor(sec)}秒`;
  if (sec < 3600) return `${Math.floor(sec / 60)}分`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}时${Math.floor((sec % 3600) / 60)}分`;
  return `${Math.floor(sec / 86400)}天${Math.floor((sec % 86400) / 3600)}时`;
}

export default function SystemSettings() {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [tab, setTab] = useState('params_info');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  // ── Connection tab state ──
  interface HealthData { ok: boolean; service: string; version: string; uptime_sec: number; database: { ok: boolean; size_mb: number; event_count: number; error: string | null } }
  const [backendUrl, setBackendUrlState] = useState(getBackendUrl());
  const [urlMode, setUrlMode] = useState<'auto' | 'manual'>(getBackendUrl() === 'http://127.0.0.1:9120' ? 'auto' : 'manual');
  const [urlInput, setUrlInput] = useState(getBackendUrl() === 'http://127.0.0.1:9120' ? '' : getBackendUrl());
  const [health, setHealth] = useState<{ data: HealthData | null; latency_ms: number; error: string | null }>({ data: null, latency_ms: 0, error: null });
  const [testing, setTesting] = useState(false);
  const [connSaved, setConnSaved] = useState(false);

  // Heartbeat: poll /api/health every 5 seconds
  useEffect(() => {
    const check = async () => {
      const t0 = performance.now();
      try {
        const r = await apiFetch('/api/health');
        const json = await r.json();
        setHealth({ data: json, latency_ms: Math.round(performance.now() - t0), error: null });
      } catch (e: any) {
        setHealth({ data: null, latency_ms: 0, error: e.message || '连接失败' });
      }
    };
    check(); // immediate
    const interval = setInterval(check, 5000);
    return () => clearInterval(interval);
  }, []);

  const testConnection = async () => {
    const target = urlMode === 'auto' ? 'http://127.0.0.1:9120' : urlInput.trim();
    setTesting(true);
    const t0 = performance.now();
    try {
      const r = await fetch(target + '/api/health');
      const json = await r.json();
      setHealth({ data: json, latency_ms: Math.round(performance.now() - t0), error: null });
      setConnSaved(false);
    } catch (e: any) {
      setHealth({ data: null, latency_ms: 0, error: e.message || '无法连接' });
    } finally {
      setTesting(false);
    }
  };

  const saveConnection = () => {
    const target = urlMode === 'auto' ? '' : urlInput.trim(); // empty = revert to default
    setBackendUrl(target);
    setBackendUrlState(getBackendUrl());
    setConnSaved(true);
    setTimeout(() => setConnSaved(false), 3000);
  };

  useEffect(() => {
    apiFetch('/api/system-config')
      .then(r => r.json())
      .then(setConfig)
      .catch(() => setMsg('加载配置失败'));
  }, []);

  const updateGeneral = (key: string, value: any) => {
    if (!config) return;
    setConfig({ ...config, general: { ...config.general, [key]: value } });
  };

  const updateModule = (module: string, task: string, value: TaskConfig) => {
    if (!config) return;
    setConfig({
      ...config,
      [module]: { ...(config as any)[module], [task]: value },
    });
  };

  const save = async () => {
    setSaving(true); setMsg('');
    try {
      const r = await apiFetch('/api/system-config', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config),
      });
      setMsg(r.ok ? '保存成功，下次 AI 调用生效' : '保存失败');
    } catch {
      setMsg('保存失败');
    } finally { setSaving(false); }
  };

  if (!config) return <div className="p-8 text-gray-400">加载中...</div>;

  const moduleTabs = Object.keys(TAB_LABELS);

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[#0B0C10] text-white">
      {/* Sticky header */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-[1080px] mx-auto">
          {/* Header */}
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Settings size={32} className="text-purple-400 shrink-0" />
              <div>
                <h1 className="text-2xl font-bold text-white">系统设置</h1>
                <p className="text-gray-400 text-sm mt-0.5">AI 模型参数与业务模块专属配置</p>
              </div>
            </div>
            <button
              onClick={save} disabled={saving}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                bg-purple-500 text-white hover:bg-purple-600 disabled:opacity-50 transition-colors"
            >
              <Save size={14} />
              {saving ? '保存中...' : '保存配置'}
            </button>
          </div>

          {msg && (
            <div className={`mb-4 px-4 py-2 rounded-lg text-sm ${
              msg.includes('成功') ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
              : 'bg-red-500/10 text-red-400 border border-red-500/20'
            }`}>{msg}</div>
          )}

          {/* Tabs */}
          <div className="border-b border-[#2A2B30]">
            <div className="flex gap-4 overflow-x-auto">
              {moduleTabs.map((k) => (
                <button
                  key={k} onClick={() => setTab(k)}
                  className={`pb-3 text-sm font-medium transition-colors relative whitespace-nowrap ${
                    tab === k ? 'text-white' : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {TAB_LABELS[k]}
                  {tab === k && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-500" />}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-[1080px] mx-auto pt-4">

      {/* Tab: 参数说明 */}
      {tab === 'params_info' && (
        <div className="space-y-6">
          {/* DeepSeek 模型规格 */}
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-1">DeepSeek 模型规格</h2>
            <p className="text-[11px] text-gray-500 mb-4">官方数据，来源 api-docs.deepseek.com</p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[#2A2B30] text-gray-400">
                    <th className="text-left py-2 pr-4 font-medium">参数</th>
                    <th className="text-center py-2 px-3 font-medium">V4 Flash</th>
                    <th className="text-center py-2 pl-3 font-medium text-purple-400">V4 Pro（当前）</th>
                  </tr>
                </thead>
                <tbody className="text-gray-300">
                  <tr className="border-b border-[#1E2025]">
                    <td className="py-2 pr-4">上下文长度</td>
                    <td className="text-center py-2 px-3 text-emerald-400">1M token</td>
                    <td className="text-center py-2 pl-3 text-emerald-400">1M token</td>
                  </tr>
                  <tr className="border-b border-[#1E2025]">
                    <td className="py-2 pr-4">最大输出</td>
                    <td className="text-center py-2 px-3 text-emerald-400">384K token</td>
                    <td className="text-center py-2 pl-3 text-emerald-400">384K token</td>
                  </tr>
                  <tr className="border-b border-[#1E2025]">
                    <td className="py-2 pr-4">思考模式</td>
                    <td className="text-center py-2 px-3">支持</td>
                    <td className="text-center py-2 pl-3">支持</td>
                  </tr>
                  <tr className="border-b border-[#1E2025]">
                    <td className="py-2 pr-4">JSON Output</td>
                    <td className="text-center py-2 px-3">✓</td>
                    <td className="text-center py-2 pl-3">✓</td>
                  </tr>
                  <tr className="border-b border-[#1E2025]">
                    <td className="py-2 pr-4">FIM 补全</td>
                    <td className="text-center py-2 px-3">非思考模式</td>
                    <td className="text-center py-2 pl-3">非思考模式</td>
                  </tr>
                  <tr className="border-b border-[#1E2025]">
                    <td className="py-2 pr-4">输入价格（缓存未命中）</td>
                    <td className="text-center py-2 px-3">1 元/百万 token</td>
                    <td className="text-center py-2 pl-3">3 元/百万 token</td>
                  </tr>
                  <tr className="border-b border-[#1E2025]">
                    <td className="py-2 pr-4">输入价格（缓存命中）</td>
                    <td className="text-center py-2 px-3 text-emerald-400">0.02 元/百万 token</td>
                    <td className="text-center py-2 pl-3 text-emerald-400">0.025 元/百万 token</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-4">输出价格</td>
                    <td className="text-center py-2 px-3">2 元/百万 token</td>
                    <td className="text-center py-2 pl-3">6 元/百万 token</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="text-[10px] text-gray-600 mt-3">
              *缓存命中：重复发送相同 system prompt + messages 时自动触发，大幅省钱。建议开启上下文硬盘缓存。
            </p>
          </div>

          {/* 参数解释 */}
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">参数详解</h2>
            <div className="space-y-4">
              <div>
                <h3 className="text-xs font-medium text-purple-400 mb-1">temperature 随机度</h3>
                <p className="text-xs text-gray-400 leading-relaxed">
                  控制输出的随机性和创造性。取值 0–2。<br />
                  <span className="text-gray-300">0</span>：完全确定性，同样 prompt 永远同样输出，适合分类/标注/数学。<br />
                  <span className="text-gray-300">0.1–0.3</span>：轻微发散，适合摘要/翻译/事实性问答。<br />
                  <span className="text-gray-300">0.4–0.6</span>：适度创造，适合论文/导言/综合回答。<br />
                  <span className="text-gray-300">0.7+</span>：高度随机，创意写作/头脑风暴，但可能胡言乱语。<br />
                  <span className="text-gray-500">注意：开启思考模式时 temperature 仅影响最终输出，不影响推理链路。</span>
                </p>
              </div>
              <div>
                <h3 className="text-xs font-medium text-purple-400 mb-1">max_tokens 最大输出</h3>
                <p className="text-xs text-gray-400 leading-relaxed">
                  AI 一次最多输出多少个 token。1 中文字 ≈ 1.5 token，4096 token ≈ 2700 汉字。<br />
                  模型上限 384K（约 25 万汉字），实际按任务需求设置即可。<br />
                  <span className="text-gray-500">设太小会导致回答被截断；设太大浪费 token 且 AI 可能啰嗦。</span>
                </p>
              </div>
              <div>
                <h3 className="text-xs font-medium text-purple-400 mb-1">thinking 思考模式</h3>
                <p className="text-xs text-gray-400 leading-relaxed">
                  开启后 AI 先内部推理再输出答案，推理过程不收费但会看到更长延迟。<br />
                  适合：复杂多步推理、论文级分析、需要引用支撑的论证。<br />
                  不适合：简单分类/标注/翻译——开了浪费延迟还不提升质量。<br />
                  <span className="text-gray-500">thinking token 不计入输出计费。</span>
                </p>
              </div>
              <div>
                <h3 className="text-xs font-medium text-purple-400 mb-1">reasoning_effort 推理强度</h3>
                <p className="text-xs text-gray-400 leading-relaxed">
                  仅在开启思考模式时生效。控制 AI 内部推理的步数和深度。<br />
                  <span className="text-gray-300">high</span>：标准推理链，适合大多数场景。<br />
                  <span className="text-gray-300">max</span>：更长的推理链，数学证明/复杂逻辑/多跳推理可能需要。<br />
                  <span className="text-gray-500">推理 token 不收费，但会增加首 token 延迟。</span>
                </p>
              </div>
              <div>
                <h3 className="text-xs font-medium text-purple-400 mb-1">上下文硬盘缓存</h3>
                <p className="text-xs text-gray-400 leading-relaxed">
                  DeepSeek 的云端缓存机制。相同 system prompt + 消息历史触达缓存时，<br />
                  输入价格从 3 元/百万 token 降至 0.025 元/百万 token（节省 99%）。<br />
                  <span className="text-gray-500">KI 的摘要、快报等定时任务 prompt 高度重复，强烈建议开启。</span>
                </p>
              </div>
            </div>
          </div>

          {/* 当前消耗估算 */}
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">各任务单次调用成本估算（V4 Pro）</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[#2A2B30] text-gray-400">
                    <th className="text-left py-2 pr-4">任务</th>
                    <th className="text-center py-2 px-3">max_tokens</th>
                    <th className="text-center py-2 px-3">≈ 汉字</th>
                    <th className="text-center py-2 px-3">输出成本</th>
                  </tr>
                </thead>
                <tbody className="text-gray-300">
                  {[
                    ['内容总结 summarize', '3072', '2000', '0.02 元'],
                    ['认知分类 classify', '256', '170', '&lt;0.01 元'],
                    ['实体标注 tag', '512', '340', '&lt;0.01 元'],
                    ['英文翻译 translate', '2048', '1300', '0.01 元'],
                    ['发现专题 discover', '4096', '2700', '0.02 元'],
                    ['专题导言 intro', '1024', '680', '&lt;0.01 元'],
                    ['结构化总结 summary', '3072', '2000', '0.02 元'],
                    ['论文分析 paper', '16384', '11000', '0.10 元'],
                    ['即时匹配 auto_suggest', '256', '170', '&lt;0.01 元'],
                    ['综合回答 answer', '8192', '5500', '0.05 元'],
                    ['对话总结 summary', '3000', '2000', '0.02 元'],
                    ['凝神静思 contemplate', '800', '530', '&lt;0.01 元'],
                    ['概念提取 concept_extract', '2048', '1300', '0.01 元'],
                    ['每日摘要 digest', '8192', '5500', '0.05 元'],
                    ['即时快报 briefing_quick', '3072', '2000', '0.02 元'],
                    ['深度日报 briefing_daily', '8192', '5500', '0.05 元'],
                    ['AI 补全 auto_complete', '1500', '1000', '0.01 元'],
                    ['事务判断 judge', '16384', '11000', '0.10 元'],
                    ['实体深度分析 entity_insight', '2048', '1300', '0.01 元'],
                  ].map(([name, tokens, chars, cost]) => (
                    <tr key={name} className="border-b border-[#1E2025]">
                      <td className="py-1.5 pr-4">{name}</td>
                      <td className="text-center py-1.5 px-3">{tokens}</td>
                      <td className="text-center py-1.5 px-3 text-gray-500">{chars}</td>
                      <td className="text-center py-1.5 pl-3 text-emerald-400">{cost}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[10px] text-gray-600 mt-3">
              *仅估算输出成本（6 元/百万 token）。输入成本和思考模式 token 另行计算。
            </p>
          </div>
        </div>
      )}

      {/* Tab: 通用配置 */}
      {tab === 'general' && (
        <div className="space-y-6">
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">模型与连接</h2>
            <div className="space-y-1">
              <label className="flex items-center justify-between py-2">
                <span className="text-xs text-gray-400">
                  选用模型
                  <span className="text-[10px] text-gray-600 ml-1">（建议 deepseek-v4-pro）</span>
                </span>
                <select
                  value={config.general.model}
                  onChange={(e) => updateGeneral('model', e.target.value)}
                  className="bg-[#0B0C10] border border-[#2A2B30] rounded px-2 py-1 text-xs text-white
                    focus:outline-none focus:border-purple-500"
                >
                  <option value="deepseek-v4-pro">deepseek-v4-pro</option>
                  <option value="deepseek-v4-flash">deepseek-v4-flash</option>
                  <option value="deepseek-chat">deepseek-chat（即将弃用）</option>
                </select>
              </label>
              <label className="flex items-center justify-between py-2">
                <span className="text-xs text-gray-400">
                  接口地址
                  <span className="text-[10px] text-gray-600 ml-1">（建议 https://api.deepseek.com）</span>
                </span>
                <input
                  type="text" value={config.general.base_url}
                  onChange={(e) => updateGeneral('base_url', e.target.value)}
                  className="w-64 bg-[#0B0C10] border border-[#2A2B30] rounded px-2 py-1 text-xs text-white
                    focus:outline-none focus:border-purple-500 text-right"
                />
              </label>
              <label className="flex items-center justify-between py-2">
                <span className="text-xs text-gray-400">
                  API 密钥
                  <span className="text-[10px] text-gray-600 ml-1">（输入后自动同步到 .env）</span>
                </span>
                <input
                  type="password" value={config.general.api_key}
                  onChange={(e) => updateGeneral('api_key', e.target.value)}
                  placeholder={config.general.api_key ? '已设置（••••）' : '未设置'}
                  className="w-52 bg-[#0B0C10] border border-[#2A2B30] rounded px-2 py-1 text-xs text-white
                    focus:outline-none focus:border-purple-500 text-right"
                />
              </label>
            </div>
          </div>

          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">缓存与全局默认</h2>
            <div className="space-y-1">
              <Toggle label="上下文硬盘缓存" checked={config.general.disk_cache}
                onChange={(v) => updateGeneral('disk_cache', v)}
                hint="建议开启，重复 prompt 大幅省钱" />

              <label className="flex items-center justify-between py-2">
                <span className="text-xs text-gray-400">
                  推理强度
                  <span className="text-[10px] text-gray-600 ml-1">（建议 high；复杂场景选 max）</span>
                </span>
                <select
                  value={config.general.reasoning_effort}
                  onChange={(e) => updateGeneral('reasoning_effort', e.target.value)}
                  className="bg-[#0B0C10] border border-[#2A2B30] rounded px-2 py-1 text-xs text-white
                    focus:outline-none focus:border-purple-500"
                >
                  <option value="high">high 标准推理</option>
                  <option value="max">max 最强推理</option>
                </select>
              </label>
            </div>
          </div>

          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">全局默认值</h2>
            <p className="text-[11px] text-gray-500 mb-2">模块未单独设置时的兜底参数</p>
            <NumberInput label="temperature 随机度" value={config.general.default_temperature}
              onChange={(v) => updateGeneral('default_temperature', v)} hint="0.3" />
            <NumberInput label="max_tokens 最大输出" value={config.general.default_max_tokens}
              onChange={(v) => updateGeneral('default_max_tokens', v)}
              min={64} max={32768} step={64} hint="2048" />
          </div>
        </div>
      )}

      {/* Tab: 连接 */}
      {tab === 'connection' && (
        <div className="space-y-6">
          {/* Status panel */}
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
              <Activity size={16} className="text-purple-400" />
              连接状态
            </h2>
            {health.error ? (
              <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
                <WifiOff size={20} className="text-red-400 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-red-400">未连接</p>
                  <p className="text-xs text-gray-500 mt-0.5">{health.error}</p>
                  <p className="text-xs text-gray-600 mt-0.5">目标: {backendUrl}</p>
                </div>
              </div>
            ) : health.data ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                  <Wifi size={20} className="text-emerald-400 shrink-0" />
                  <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2">
                    <div>
                      <span className="text-[10px] text-gray-500">状态</span>
                      <p className="text-sm text-emerald-400 font-medium">已连接</p>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-500">延迟</span>
                      <p className="text-sm text-white">{health.latency_ms}ms</p>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-500">后端版本</span>
                      <p className="text-sm text-white">{health.data.version}</p>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-500">运行时间</span>
                      <p className="text-sm text-white">{formatUptime(health.data.uptime_sec)}</p>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs bg-purple-500/5 text-purple-400">
                  <Globe size={12} />
                  <span>客户端 v{CLIENT_VERSION}</span>
                  <span className="text-gray-600">→</span>
                  <span className="text-gray-300">{backendUrl}</span>
                </div>
                {/* Database sub-status */}
                <div className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs ${
                  health.data.database?.ok
                    ? 'bg-emerald-500/5 text-emerald-400'
                    : 'bg-red-500/5 text-red-400'
                }`}>
                  <Server size={12} />
                  <span>数据库：{health.data.database?.ok ? '正常' : '异常'}</span>
                  {health.data.database?.ok && (
                    <>
                      <span className="text-gray-600">|</span>
                      <span>{health.data.database.event_count} 条事件</span>
                      <span className="text-gray-600">|</span>
                      <span>{health.data.database.size_mb} MB</span>
                    </>
                  )}
                  {!health.data.database?.ok && health.data.database?.error && (
                    <>
                      <span className="text-gray-600">|</span>
                      <span className="text-red-300">{health.data.database.error}</span>
                    </>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 p-4 bg-[#0B0C10] border border-[#2A2B30] rounded-lg">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-purple-500" />
                <p className="text-sm text-gray-500">检测中...</p>
              </div>
            )}
          </div>

          {/* Backend URL config */}
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
              <Globe size={16} className="text-purple-400" />
              后端地址
            </h2>

            {/* Mode selector */}
            <div className="flex gap-4 mb-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio" name="urlMode" value="auto"
                  checked={urlMode === 'auto'}
                  onChange={() => setUrlMode('auto')}
                  className="accent-purple-500"
                />
                <span className="text-xs text-gray-300">自动检测（默认连本地）</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio" name="urlMode" value="manual"
                  checked={urlMode === 'manual'}
                  onChange={() => setUrlMode('manual')}
                  className="accent-purple-500"
                />
                <span className="text-xs text-gray-300">手动指定</span>
              </label>
            </div>

            {urlMode === 'manual' && (
              <div className="flex gap-3">
                <input
                  type="text"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="http://10.8.0.105:9120"
                  className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2 text-sm text-white
                    placeholder-gray-600 focus:outline-none focus:border-purple-500"
                />
                <button
                  onClick={testConnection}
                  disabled={testing || !urlInput.trim()}
                  className="px-4 py-2 rounded-lg text-xs font-medium bg-[#2A2B30] text-gray-300
                    hover:bg-[#3A3B40] disabled:opacity-40 transition-colors shrink-0"
                >
                  {testing ? '测试中...' : '测试连接'}
                </button>
              </div>
            )}

            {urlMode === 'auto' && (
              <div className="flex gap-3">
                <div className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2 text-sm text-gray-500">
                  http://127.0.0.1:9120（自动）
                </div>
                <button
                  onClick={testConnection}
                  disabled={testing}
                  className="px-4 py-2 rounded-lg text-xs font-medium bg-[#2A2B30] text-gray-300
                    hover:bg-[#3A3B40] disabled:opacity-40 transition-colors shrink-0"
                >
                  {testing ? '测试中...' : '测试连接'}
                </button>
              </div>
            )}

            {/* Save / Reset */}
            <div className="flex items-center gap-3 mt-4">
              <button
                onClick={saveConnection}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                  bg-purple-500 text-white hover:bg-purple-600 transition-colors"
              >
                <Save size={14} />
                保存
              </button>
              {urlMode === 'manual' && (
                <button
                  onClick={() => { setUrlMode('auto'); setUrlInput(''); }}
                  className="px-3 py-2 rounded-lg text-xs text-gray-400 hover:text-white hover:bg-[#2A2B30] transition-colors"
                >
                  恢复默认
                </button>
              )}
              {connSaved && (
                <span className="text-xs text-emerald-400">✓ 已保存，下次请求生效</span>
              )}
            </div>

            <p className="text-[11px] text-gray-600 mt-4 leading-relaxed">
              本地模式：后端运行在本机 127.0.0.1:9120，数据存在本地。<br />
              远程模式：填入 VPN 地址（如 <code className="text-gray-500 bg-[#0B0C10] px-1 rounded">http://10.8.0.105:9120</code>），
              多设备共享同一后端和数据。切换后即刻生效。
            </p>
          </div>
        </div>
      )}

      {/* Tab: 业务模块 */}
      {tab !== 'general' && tab !== 'params_info' && tab !== 'connection' && (
        <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-4">
            {TAB_LABELS[tab]} — 任务参数
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {Object.entries(config[tab as keyof SystemConfig] as ModuleConfig).map(([task, cfg]) => (
              <TaskRow
                key={task}
                name={task}
                cnName={TASK_NAMES[tab]?.[task] || task}
                config={cfg}
                suggestion={SUGGESTIONS[tab]?.[task]}
                onChange={(v) => updateModule(tab, task, v)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Prompt 模板 */}
      {tab !== 'general' && tab !== 'params_info' && (
        <PromptSection moduleKey={tab} taskNames={TASK_NAMES[tab] || {}} />
      )}
        </div>
      </div>
    </div>
  );
}
