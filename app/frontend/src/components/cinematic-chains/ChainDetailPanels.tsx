import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { Eraser, Loader2, MessageCircle, Send, Sparkles } from 'lucide-react';
import { apiFetch } from '../../api';
import { ChainReport } from '../ChainReport';
import { RequestLifecycle } from '../ingest/requestLifecycle';

type ChatMessage = { role: string; content: string };
type DetailCache = {
  getChat: (chainName: string) => ChatMessage[];
  setChat: (chainName: string, messages: ChatMessage[]) => void;
  clearChat: (chainName: string) => void;
  getReport: (chainName: string) => { report: string; cached: boolean } | null;
  setReport: (chainName: string, entry: { report: string; cached: boolean }) => void;
  clearReport: (chainName: string) => void;
};

export const ChainReportPanel = memo(function ChainReportPanel({ chainName, embedded, cache }: {
  chainName: string;
  embedded: boolean;
  cache: DetailCache;
}) {
  const cachedEntry = cache.getReport(chainName);
  const [report, setReport] = useState<string | null>(cachedEntry?.report || null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState('');
  const [reportFromCache, setReportFromCache] = useState(Boolean(cachedEntry?.cached));
  const requestLifecycleRef = useRef(new RequestLifecycle());

  const loadReport = useCallback(async (force = false) => {
    if (!force) {
      const cached = cache.getReport(chainName);
      if (cached) {
        setReport(cached.report);
        setReportFromCache(cached.cached);
        setReportError('');
        setReportLoading(false);
        return;
      }
    }
    const request = requestLifecycleRef.current.start();
    setReportLoading(true);
    setReportError('');
    try {
      const response = await apiFetch('/api/chains/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chain_name: chainName, force, cache_only: embedded && !force }),
        signal: request.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `分析报告加载失败：HTTP ${response.status}`);
      if (!requestLifecycleRef.current.isCurrent(request.sequence)) return;
      if (data.report) {
        const entry = { report: data.report, cached: Boolean(data.cached) };
        cache.setReport(chainName, entry);
        setReport(entry.report);
        setReportFromCache(entry.cached);
      } else if (data.missing) {
        cache.clearReport(chainName);
        setReport(null);
        setReportFromCache(false);
      } else {
        throw new Error(data.error || '分析失败');
      }
    } catch (reason: any) {
      if (reason?.name !== 'AbortError' && requestLifecycleRef.current.isCurrent(request.sequence)) {
        setReportError(reason?.message || '分析报告加载失败');
      }
    } finally {
      if (requestLifecycleRef.current.isCurrent(request.sequence)) setReportLoading(false);
    }
  }, [cache, chainName, embedded]);

  useEffect(() => {
    const cached = cache.getReport(chainName);
    setReport(cached?.report || null);
    setReportFromCache(Boolean(cached?.cached));
    setReportError('');
    setReportLoading(false);
    void loadReport(false);
    return () => requestLifecycleRef.current.abort();
  }, [cache, chainName, loadReport]);

  return (
    <div className="w-1/2 border-r border-[#2A2B30] overflow-y-auto custom-scrollbar p-5 min-h-0">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="w-1 h-3 rounded-full bg-emerald-400" />
          <span className="text-[11px] text-emerald-400 font-medium">AI 产业链分析</span>
          {reportFromCache && <span className="text-[9px] text-gray-600">（缓存）</span>}
        </div>
        <button onClick={() => void loadReport(true)} disabled={reportLoading} className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium text-gray-500 hover:text-purple-400 hover:bg-purple-500/10 border border-transparent hover:border-purple-500/20 transition-colors disabled:opacity-50">
          {reportLoading ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
          重新分析
        </button>
      </div>
      {reportLoading && <div className="flex items-center gap-2 text-gray-500 text-sm py-8"><Loader2 size={16} className="animate-spin" /> {embedded ? '正在读取分析报告…' : '正在生成分析报告…'}</div>}
      {reportError && <div className="text-red-400 text-sm py-4">{reportError}</div>}
      {report && !reportLoading && <ChainReport report={report} />}
      {!report && !reportLoading && !reportError && <button onClick={() => void loadReport(true)} className="flex items-center gap-2 py-8 text-xs text-gray-500 hover:text-emerald-400"><Sparkles size={14} />生成产业链分析报告</button>}
    </div>
  );
});

export const ChainChatPanel = memo(function ChainChatPanel({ chainName, cache }: {
  chainName: string;
  cache: DetailCache;
}) {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(() => cache.getChat(chainName));
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const requestLifecycleRef = useRef(new RequestLifecycle());

  useEffect(() => {
    setChatMessages(cache.getChat(chainName));
    setChatInput('');
    setChatLoading(false);
    requestLifecycleRef.current.abort();
  }, [cache, chainName]);

  useEffect(() => () => requestLifecycleRef.current.abort(), []);

  useEffect(() => {
    const target = chatScrollRef.current;
    if (!target || chatMessages.length === 0) return;
    target.scrollTo({ top: target.scrollHeight, behavior: 'smooth' });
  }, [chatMessages, chatLoading]);

  const replaceMessages = useCallback((messages: ChatMessage[]) => {
    cache.setChat(chainName, messages);
    setChatMessages(messages);
  }, [cache, chainName]);

  const sendMessage = useCallback(async () => {
    const message = chatInput.trim();
    if (!message || chatLoading) return;
    const history = cache.getChat(chainName);
    const nextMessages = [...history, { role: 'user', content: message }];
    replaceMessages(nextMessages);
    setChatInput('');
    setChatLoading(true);
    const request = requestLifecycleRef.current.start();
    try {
      const response = await apiFetch('/api/chains/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chain_name: chainName, message, history }),
        signal: request.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `请求失败：HTTP ${response.status}`);
      if (!requestLifecycleRef.current.isCurrent(request.sequence)) return;
      replaceMessages([...nextMessages, { role: 'assistant', content: data.reply || data.error || '暂时没有可用回答' }]);
    } catch (reason: any) {
      if (reason?.name !== 'AbortError' && requestLifecycleRef.current.isCurrent(request.sequence)) {
        replaceMessages([...nextMessages, { role: 'assistant', content: `请求失败：${reason?.message || '请重试'}` }]);
      }
    } finally {
      if (requestLifecycleRef.current.isCurrent(request.sequence)) setChatLoading(false);
    }
  }, [cache, chainName, chatInput, chatLoading, replaceMessages]);

  const clearMessages = useCallback(() => {
    requestLifecycleRef.current.abort();
    cache.clearChat(chainName);
    setChatMessages([]);
    setChatLoading(false);
  }, [cache, chainName]);

  return (
    <div className="w-1/2 flex flex-col min-h-0">
      <div className="flex items-center justify-between px-5 py-2 border-b border-[#2A2B30] shrink-0">
        <div className="flex items-center gap-2"><MessageCircle size={14} className="text-purple-400" /><span className="text-[11px] text-purple-400 font-medium">智能答疑</span></div>
        {chatMessages.length > 0 && <button onClick={clearMessages} className="text-[9px] text-gray-500 hover:text-gray-300 flex items-center gap-1"><Eraser size={11} />清空</button>}
      </div>
      <div ref={chatScrollRef} className="flex-1 overflow-y-auto custom-scrollbar px-4 py-2 space-y-2 min-h-0">
        {chatMessages.length === 0 && <div className="text-[10px] text-gray-600 text-center py-4">我是产业链分析助手，可以问我关于{chainName}的全球格局、供应链风险、替代方案等问题</div>}
        {chatMessages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-lg px-3 py-1.5 text-[11px] leading-relaxed ${message.role === 'user' ? 'bg-blue-500/15 text-blue-200 border border-blue-500/20' : 'bg-[#1A1B20] text-gray-300 border border-[#2A2B30]'}`}>{message.content}</div>
          </div>
        ))}
        {chatLoading && <div className="flex justify-start"><div className="bg-[#1A1B20] border border-[#2A2B30] rounded-lg px-3 py-1.5"><Loader2 size={12} className="animate-spin text-gray-500" /></div></div>}
      </div>
      <div className="px-4 py-2 border-t border-[#2A2B30] shrink-0 flex items-center gap-2">
        <input value={chatInput} onChange={(event) => setChatInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && void sendMessage()} placeholder="问一个关于这条产业链的问题..." className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-[11px] text-gray-200 placeholder-gray-600 outline-none focus:border-purple-500/30" />
        <button onClick={() => void sendMessage()} disabled={chatLoading || !chatInput.trim()} className="shrink-0 p-1.5 rounded-lg bg-purple-500/15 text-purple-400 hover:bg-purple-500/25 border border-purple-500/20 disabled:opacity-30 transition-colors"><Send size={12} /></button>
      </div>
    </div>
  );
});
