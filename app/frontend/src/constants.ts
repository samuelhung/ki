// 客户端版本号 — 与 desktop/pubspec.yaml 的 marketing version 同步
// 修改版本号时请同步更新：
// 1. desktop/pubspec.yaml                 → version
// 2. desktop/changelog.json               → 版本说明
// 3. 本文件                              → APP_VERSION（前端显示用）
export const APP_VERSION = "1.3.6";

// Backend URL for API calls
export const DEFAULT_BACKEND_URL = "http://127.0.0.1:9120";

// Dashboard configuration
export const DASHBOARD_CONFIG = {
  events_page_size: 20,
  news_page_size: 20,
  reports_page_size: 20,
};

// Ingestion limits
export const INGESTION_LIMITS = {
  max_file_size_mb: 500,
  supported_audio_formats: ["mp3", "wav", "m4a", "aac", "ogg", "flac", "wma", "opus"],
  supported_video_formats: ["mp4", "mov", "avi", "mkv", "webm", "flv", "wmv"],
  supported_document_formats: ["txt", "md", "pdf", "docx", "html"],
};
