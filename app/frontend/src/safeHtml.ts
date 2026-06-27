const BLOCKED_TAG_RE = /<\/?(?:script|style|iframe|object|embed|link|meta|base|form|input|button|textarea|select|option|svg|math)\b[^>]*>/gi;
const EVENT_HANDLER_RE = /\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi;
const DANGEROUS_URL_RE = /\s+(href|src)\s*=\s*(?:("|')\s*(?:javascript:|data:text\/html|vbscript:)[\s\S]*?\2|(?:javascript:|data:text\/html|vbscript:)[^\s>]*)/gi;

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function sanitizeHtml(html: string): string {
  return html
    .replace(BLOCKED_TAG_RE, '')
    .replace(EVENT_HANDLER_RE, '')
    .replace(DANGEROUS_URL_RE, '');
}
