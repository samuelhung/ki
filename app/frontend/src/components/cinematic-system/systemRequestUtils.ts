export function buildSystemLogPath(level: string, search: string, limit = 100): string {
  const params = new URLSearchParams({ level, limit: String(limit) });
  if (search.trim()) params.set('search', search.trim());
  return `/api/logs?${params}`;
}
