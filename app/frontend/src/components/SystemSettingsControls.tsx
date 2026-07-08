import { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export interface TaskConfig {
  temperature: number;
  max_tokens: number;
  thinking: boolean;
}

export function Toggle({ label, checked, onChange, hint }: {
  label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string;
}) {
  return (
    <label className="flex items-center justify-between py-2">
      <span className="text-xs text-gray-400">
        {label}
        {hint && <span className="text-[10px] text-gray-600 ml-1">（{hint}）</span>}
      </span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ${
          checked ? 'bg-purple-500' : 'bg-[#2A2B30]'
        }`}
      >
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`} />
      </button>
    </label>
  );
}

export function NumberInput({ label, value, onChange, min = 0, max = 2, step = 0.1, hint }: {
  label: string; value: number; onChange: (v: number) => void;
  min?: number; max?: number; step?: number; hint?: string;
}) {
  return (
    <label className="flex items-center justify-between py-2">
      <span className="text-xs text-gray-400">
        {label}
        {hint && <span className="text-[10px] text-gray-600 ml-1">（建议 {hint}）</span>}
      </span>
      <input
        type="number" min={min} max={max} step={step}
        value={value}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (!isNaN(v)) onChange(Math.min(max, Math.max(min, v)));
        }}
        className="w-20 bg-[#0B0C10] border border-[#2A2B30] rounded px-2 py-1 text-xs text-white text-right
          focus:outline-none focus:border-purple-500"
      />
    </label>
  );
}

export function TaskRow({ name, cnName, config, suggestion, onChange }: {
  name: string; cnName: string;
  config: TaskConfig;
  suggestion?: { temp: string; tokens: string };
  onChange: (c: TaskConfig) => void;
}) {
  return (
    <div className="bg-[#0B0C10] rounded-lg px-3 py-2 space-y-1">
      <div className="text-xs font-medium text-gray-300">
        {cnName}
        <span className="text-[10px] text-gray-600 ml-1">({name})</span>
      </div>
      <NumberInput label="temperature 随机度" value={config.temperature}
        onChange={(v) => onChange({ ...config, temperature: v })} hint={suggestion?.temp} />
      <NumberInput label="max_tokens 最大输出" value={config.max_tokens}
        onChange={(v) => onChange({ ...config, max_tokens: v })}
        min={64} max={32768} step={64} hint={suggestion?.tokens} />
      <Toggle label="thinking 思考模式" checked={config.thinking}
        onChange={(v) => onChange({ ...config, thinking: v })}
        hint={config.thinking ? '已开启，消耗更多 token 但推理更深' : '建议关闭，省钱'} />
    </div>
  );
}

export function PromptSection({
  moduleKey,
  taskNames,
  defaultExpanded = false,
}: {
  moduleKey: string;
  taskNames: Record<string, string>;
  defaultExpanded?: boolean;
}) {
  const [prompts, setPrompts] = useState<Record<string, Record<string, string>>>({});
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    apiFetch('/api/system/prompts')
      .then(r => r.json())
      .then(d => setPrompts(d.modules?.[moduleKey] || {}))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [moduleKey]);

  const entries = Object.entries(prompts);
  const promptCount = entries.reduce((c, [, tasks]) => c + Object.keys(tasks).length, 0);

  return (
    <div className="bg-[#141518] border border-[#2A2B30] rounded-xl mt-4 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-[#1A1B20] transition-colors"
      >
        <h3 className="text-sm font-semibold text-white">
          Prompt 模板
          {promptCount > 0 && (
            <span className="ml-2 text-xs font-normal text-gray-500">
              ({promptCount})
            </span>
          )}
        </h3>
        <span className="text-gray-500 text-xs">{expanded ? '收起 ▲' : '展开 ▼'}</span>
      </button>
      {expanded && (
        <div className="px-5 pb-4 border-t border-[#2A2B30]">
          {loading ? (
            <div className="py-8 flex items-center justify-center">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-purple-500" />
            </div>
          ) : entries.length === 0 ? (
            <p className="py-6 text-center text-xs text-gray-500">暂无 prompt 数据</p>
          ) : (
            <div className="space-y-4 pt-4">
              {entries.map(([task, promptMap]) => (
                <div key={task}>
                  <h4 className="text-xs font-medium text-purple-400 mb-2">
                    {taskNames[task] || task}
                  </h4>
                  {Object.entries(promptMap).map(([name, content]) => (
                    <details key={name} className="mb-2 group">
                      <summary className="cursor-pointer text-xs text-gray-400 hover:text-gray-300 py-1 select-none">
                        {name}
                      </summary>
                      <pre className="mt-2 p-3 bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-[11px] text-gray-300 whitespace-pre-wrap break-all max-h-[400px] overflow-y-auto custom-scrollbar font-mono leading-relaxed">
                        {content}
                      </pre>
                    </details>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
