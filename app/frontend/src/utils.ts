/**
 * 全局时间格式化工具
 *
 * 约定：所有数据库时间字段（created_at, published_at 等）均存储为 UTC 时间，
 * 前端统一使用本模块的函数转换为北京时间（Asia/Shanghai）显示。
 *
 * 统一格式：2026/6/3 14:58:39
 */

const BEIJING_TZ = 'Asia/Shanghai';

/**
 * 将 UTC 时间字符串格式化为北京时间
 * 输入：'2026-06-03 04:05:09' (SQLite CURRENT_TIMESTAMP, UTC)
 * 输出：'2026/6/3 12:05:09' (北京时间)
 */
export function formatTimeBeijing(utcTime: string | undefined | null): string {
  if (!utcTime) return '';
  // SQLite CURRENT_TIMESTAMP 返回空格分隔，加 Z 后缀标记为 UTC
  const d = new Date(utcTime.replace(' ', 'T') + 'Z');
  // 手动格式化保证输出格式一致，不依赖浏览器 locale 差异
  const bj = new Date(d.toLocaleString('en-US', { timeZone: BEIJING_TZ }));
  const Y = bj.getFullYear();
  const M = bj.getMonth() + 1;
  const D = bj.getDate();
  const h = String(bj.getHours()).padStart(2, '0');
  const m = String(bj.getMinutes()).padStart(2, '0');
  const s = String(bj.getSeconds()).padStart(2, '0');
  return `${Y}/${M}/${D} ${h}:${m}:${s}`;
}

// ── 来源/状态标签（各页面共享） ──────────────────────────

/** 内容来源 ID → 中文标签 */
export function sourceLabel(sourceId: string): string {
  switch (sourceId) {
    case 'douyin': return '抖音分享';
    case 'user-upload': return '上传文件';
    case 'user-concept': return '沉淀概念';
    default: return sourceId;
  }
}

/** 内容来源 ID → Tailwind badge 样式 */
export function sourceBadgeClass(sourceId: string): string {
  switch (sourceId) {
    case 'douyin': return 'bg-pink-500/15 text-pink-400';
    case 'user-upload': return 'bg-cyan-500/15 text-cyan-400';
    case 'user-concept': return 'bg-emerald-500/15 text-emerald-400';
    default: return 'bg-gray-500/15 text-gray-400';
  }
}

/** 事件状态 → 中文标签 */
export function statusLabel(status: string): string {
  switch (status) {
    case 'new': return '已入库';
    case 'processing': return '处理中';
    case 'completed': return '已完成';
    case 'failed': return '失败';
    default: return status;
  }
}
