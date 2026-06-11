import React from 'react';

/**
 * Render inline text with **bold** and evidence annotations.
 */
export function renderInline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*.+?\*\*|（证据：[^）]*）)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**'))
      return <strong key={i} className="font-semibold text-gray-200">{part.slice(2, -2)}</strong>;
    if (part.startsWith('（证据：'))
      return <span key={i} className="text-gray-500 italic">{part}</span>;
    return part;
  });
}

/**
 * Render AI-generated Markdown content with consistent typography.
 *
 * Layout spec:
 *   ## heading   → <h3> text-sm font-semibold text-purple-400 mt-5 mb-2
 *   ### heading  → <p>  text-purple-400 leading-relaxed font-medium mb-2
 *   paragraph    → <p>  text-gray-300 leading-relaxed mb-2
 *   list item    → <li> text-gray-300, • bullet, space-y-1
 *   **bold**     → <strong> font-semibold text-gray-200
 *   （证据：...） → <span> text-gray-500 italic
 */
export function renderMarkdown(md: string): React.ReactNode {
  if (!md)
    return <p className="text-gray-500 py-4 text-center">暂无内容</p>;

  // Strip AI preamble boilerplate
  md = md.replace(/^好的，[^。\n]+。\n\n/, '');
  md = md.replace(/^根据(所选|您提供的)文章(内容)?[，,]\s*[^。\n]*[。，：:]\s*/s, '');

  const lines = md.split('\n');
  const nodes: React.ReactNode[] = [];
  let i = 0;
  let listItems: string[] = [];

  function flushList() {
    if (listItems.length > 0) {
      nodes.push(
        <ul key={`ul-${i}`} className="space-y-1 mt-1 mb-3">
          {listItems.map((item, j) => (
            <li key={j} className="flex gap-1.5">
              <span className="text-gray-500 shrink-0">•</span>
              <span className="text-gray-300">{renderInline(item)}</span>
            </li>
          ))}
        </ul>
      );
      listItems = [];
    }
  }

  for (i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('## ')) {
      flushList();
      nodes.push(
        <h3 key={i} className="text-sm font-semibold text-purple-400 mt-5 mb-2">
          {line.slice(3)}
        </h3>
      );
    } else if (line.startsWith('### ')) {
      flushList();
      nodes.push(
        <p key={i} className="mb-2 text-purple-400 leading-relaxed font-medium">
          {line.slice(4)}
        </p>
      );
    } else if (/^- /.test(line)) {
      listItems.push(line.replace(/^- /, ''));
    } else if (line.trim() === '') {
      flushList();
    } else {
      flushList();
      nodes.push(
        <p key={i} className="mb-2 text-gray-300 leading-relaxed">
          {renderInline(line)}
        </p>
      );
    }
  }
  flushList();
  return <>{nodes}</>;
}
