import React from 'react';
import { escapeHtml, sanitizeHtml } from '../../safeHtml';

export const STATUS_LABEL: Record<string, string> = {
  published: '已发布',
  draft: '草稿',
  candidate: '候选',
};

const TOPIC_COLORS: Record<string, string> = {
  '格局': 'text-blue-400',
  '财富': 'text-amber-400',
  '认知': 'text-purple-400',
  '前瞻': 'text-emerald-400',
};

const REF_COLORS = [
  'text-blue-400 hover:text-blue-200',
  'text-amber-400 hover:text-amber-200',
  'text-emerald-400 hover:text-emerald-200',
  'text-rose-400 hover:text-rose-200',
  'text-cyan-400 hover:text-cyan-200',
  'text-violet-400 hover:text-violet-200',
  'text-orange-400 hover:text-orange-200',
  'text-teal-400 hover:text-teal-200',
];

export function refColor(n: number): string {
  return REF_COLORS[(n - 1) % REF_COLORS.length];
}

export function getTopicColor(topic: string): string {
  return TOPIC_COLORS[topic] || 'text-gray-400';
}

export function refsToHtml(text: string): string {
  return escapeHtml(text).replace(/\[(\d+)\]/g, (_, n) => {
    const color = refColor(parseInt(n));
    return `<span class="ref-link ${color}" data-ref="${n}">[${n}]</span>`;
  });
}

export function renderLineWithRefs(line: string, onRefClick: (n: number) => void): React.ReactNode {
  return line.split(/(\[\d+\])/g).map((part, index) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (!match) return <React.Fragment key={index}>{part}</React.Fragment>;
    const n = parseInt(match[1]);
    return (
      <button key={index} onClick={(event) => { event.stopPropagation(); onRefClick(n); }}
        className={`inline-flex items-center px-0.5 text-[11px] font-mono align-baseline cursor-pointer hover:underline ${refColor(n)}`}>
        [{n}]
      </button>
    );
  });
}

export function summaryToHtml(md: string, mode?: 'summary' | 'paper'): string {
  if (mode !== 'paper') {
    md = md.replace(/^##\s*结构化速览\s*\n+/i, '').replace(/^##\s*专题总结\s*\n+/i, '');
  }
  const boldify = (text: string) => text.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-gray-200">$1</strong>');
  let html = '';
  let inList = false;
  const closeList = () => {
    if (!inList) return;
    html += '</ul>';
    inList = false;
  };
  for (const raw of md.split('\n')) {
    const line = refsToHtml(raw);
    if (line.startsWith('## ')) {
      closeList();
      html += `<h3 class="text-sm font-semibold text-purple-400 mt-5 mb-2">${boldify(line.slice(3))}</h3>`;
    } else if (line.startsWith('### ')) {
      closeList();
      html += `<p class="mb-2 text-purple-400 leading-relaxed font-medium">${boldify(line.slice(4))}</p>`;
    } else if (/^- /.test(line)) {
      if (!inList) { html += '<ul class="space-y-1 mt-1 mb-3">'; inList = true; }
      html += `<li class="flex gap-1.5"><span class="text-gray-500 shrink-0">•</span><span class="text-gray-300">${boldify(line.replace(/^- /, ''))}</span></li>`;
    } else if (line.trim() === '' || /^[-*]{3,}$/.test(line.trim())) {
      closeList();
    } else {
      closeList();
      html += `<p class="mb-2 text-gray-300 leading-relaxed">${boldify(line)}</p>`;
    }
  }
  closeList();
  return sanitizeHtml(html);
}
