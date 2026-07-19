import React, { useMemo } from 'react';
import { escapeHtml, sanitizeHtml } from '../safeHtml';

export function chainReportToHtml(markdown: string): string {
  let md = markdown.replace(/^好的，[^。\n]+。\n\n/i, '');
  md = md.replace(/^以下为[^。\n]*报告[^。]*[。\n]\n*/i, '');

  function boldify(value: string): string {
    return value.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-gray-200">$1</strong>');
  }

  let html = '';
  for (const raw of md.split('\n')) {
    const line = escapeHtml(raw);
    if (line.startsWith('## ')) {
      html += `<h3 class="text-sm font-semibold text-purple-400 mt-5 mb-2">${boldify(line.slice(3))}</h3>`;
    } else if (line.startsWith('### ') || line.startsWith('#### ')) {
      html += `<p class="mb-2 text-purple-400 leading-relaxed font-medium text-xs">${boldify(line.replace(/^#+ /, ''))}</p>`;
    } else if (/^- /.test(line)) {
      html += `<div class="flex gap-1.5 ml-2"><span class="text-gray-500 shrink-0">•</span><span class="text-gray-300">${boldify(line.replace(/^- /, ''))}</span></div>`;
    } else if (line.trim() === '') {
      html += '<div class="h-1"></div>';
    } else if (/^[-*]{3,}$/.test(line.trim())) {
      html += '<hr class="border-[#2A2B30] my-2" />';
    } else {
      html += `<p class="mb-2 text-gray-300 leading-relaxed">${boldify(line)}</p>`;
    }
  }
  return sanitizeHtml(html);
}

export function ChainReport({ report }: { report: string }) {
  const html = useMemo(() => chainReportToHtml(report), [report]);
  return (
    <div
      className="text-xs leading-relaxed"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
