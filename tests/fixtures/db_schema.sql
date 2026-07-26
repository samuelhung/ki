CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  url TEXT NOT NULL,
  topic TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  priority TEXT NOT NULL DEFAULT 'medium',
  enabled INTEGER NOT NULL DEFAULT 1,
  last_checked_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  published_at TEXT,
  raw_summary TEXT,
  ai_summary TEXT,
  title_cn TEXT,
  summary_cn TEXT,
  translation_status TEXT,
  translation_error TEXT,
  topic TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  importance INTEGER NOT NULL DEFAULT 0,
  actionability INTEGER NOT NULL DEFAULT 0,
  decision TEXT NOT NULL DEFAULT 'digest',
  status TEXT NOT NULL DEFAULT 'new',
  content_type TEXT NOT NULL DEFAULT 'event',
  overview TEXT,
  video_path TEXT,
  audio_path TEXT,
  document_path TEXT,
  progress_stages TEXT,
  last_discovered_at TEXT,
  suggested_series_json TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS briefings (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL DEFAULT 'quick',
  topics_json TEXT NOT NULL DEFAULT '[]',
  events_used INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS brainstorm_questions (
  id TEXT PRIMARY KEY,
  event_id TEXT,
  question TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  summary_created_at TEXT,
  FOREIGN KEY(event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS brainstorm_event_links (
  question_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  PRIMARY KEY (question_id, event_id),
  FOREIGN KEY (question_id) REFERENCES brainstorm_questions(id),
  FOREIGN KEY (event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS brainstorm_contemplate_cache (
  question_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  relevance TEXT NOT NULL,
  reason TEXT,
  judged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (question_id, event_id)
);

CREATE TABLE IF NOT EXISTS brainstorm_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
  content TEXT NOT NULL DEFAULT '',
  refs_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (question_id) REFERENCES brainstorm_questions(id)
);

-- FTS5 full-text search (standalone table, trigram tokenizer for Chinese + English)
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
  event_id UNINDEXED,
  title, title_cn, raw_summary, summary_cn, ai_summary,
  tokenize='trigram'
);

-- Persistent ingest task queue (replaces BackgroundTasks)
CREATE TABLE IF NOT EXISTS ingest_tasks (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  ingest_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at TEXT,
  finished_at TEXT
);

-- Unified task management — manual tasks + KI-linked action items
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'manual',
  source_id TEXT,
  source_label TEXT,
  priority TEXT NOT NULL DEFAULT 'medium',
  due_date TEXT,
  status TEXT NOT NULL DEFAULT 'todo',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Thematic series — AI-discovered clusters of related content
CREATE TABLE IF NOT EXISTS series (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  member_ids TEXT NOT NULL DEFAULT '[]',
  sort_order TEXT DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'draft',
  intro TEXT,
  summary TEXT,
  paper TEXT,
  updated_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- AI usage tracking: per-call token counts and cost estimates
CREATE TABLE IF NOT EXISTS ai_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  module TEXT DEFAULT '',
  task TEXT DEFAULT '',
  model TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'success',
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0,
  cached_tokens INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens INTEGER NOT NULL DEFAULT 0,
  cost_rmb REAL NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  error TEXT DEFAULT ''
);

-- Series scan cache: persists expand-scan results so re-opening skips AI call
CREATE TABLE IF NOT EXISTS series_scan_cache (
  series_id TEXT PRIMARY KEY,
  scanned_count INTEGER NOT NULL,
  recommendations_json TEXT NOT NULL DEFAULT '[]',
  scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 辅导中心 — 学习资料（独立模块，与 events 无关）
CREATE TABLE IF NOT EXISTS study_materials (
  id              TEXT PRIMARY KEY,
  subject         TEXT NOT NULL DEFAULT '',
  grade           TEXT DEFAULT '',
  textbook        TEXT DEFAULT '',
  study_type      TEXT NOT NULL DEFAULT '',
  title           TEXT NOT NULL DEFAULT '',
  source_type     TEXT DEFAULT 'manual',
  raw_content     TEXT DEFAULT '',
  child_version   TEXT DEFAULT '',
  parent_version  TEXT DEFAULT '',
  formats_json    TEXT DEFAULT '{}',
  status          TEXT DEFAULT 'draft',
  score           INTEGER,
  is_correct      INTEGER,
  mistake_tags    TEXT DEFAULT '[]',
  tags_json       TEXT DEFAULT '[]',
  lessons_json    TEXT DEFAULT '[]',
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS industry_chain_nodes (
  id              TEXT PRIMARY KEY,
  chain           TEXT NOT NULL DEFAULT '',
  name            TEXT NOT NULL DEFAULT '',
  node_type       TEXT NOT NULL DEFAULT '',
  description     TEXT DEFAULT '',
  parent_id       TEXT DEFAULT '',
  global_shares   TEXT DEFAULT '[]',
  substitutes     TEXT DEFAULT '[]',
  upstream_ids    TEXT DEFAULT '[]',
  data_sources    TEXT DEFAULT '{}',
  last_updated    TEXT DEFAULT '',
  sort_order      INTEGER DEFAULT 0,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 产业链数据更新提示 — 采集内容中检测到的潜在数据更新
CREATE TABLE IF NOT EXISTS chain_data_hints (
  id              TEXT PRIMARY KEY,
  event_id        TEXT NOT NULL,
  node_id         TEXT NOT NULL,
  chain           TEXT NOT NULL DEFAULT '',
  field           TEXT NOT NULL DEFAULT '',
  current_value   TEXT DEFAULT '',
  suggested_value TEXT NOT NULL DEFAULT '',
  source_quote    TEXT DEFAULT '',
  confidence      REAL NOT NULL DEFAULT 0.5,
  status          TEXT NOT NULL DEFAULT 'pending',
  resolved_value  TEXT DEFAULT '',
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  reviewed_at     TEXT,
  FOREIGN KEY (event_id) REFERENCES events(id),
  FOREIGN KEY (node_id) REFERENCES industry_chain_nodes(id)
);

-- 新产业链建议 — AI 从采集内容中发现的新链条（尚未收录）
CREATE TABLE IF NOT EXISTS chain_suggestions (
  id              TEXT PRIMARY KEY,
  chain_name      TEXT NOT NULL DEFAULT '',
  event_id        TEXT NOT NULL,
  nodes_json      TEXT NOT NULL DEFAULT '[]',
  reason          TEXT DEFAULT '',
  source_quote    TEXT DEFAULT '',
  confidence      REAL NOT NULL DEFAULT 0.5,
  status          TEXT NOT NULL DEFAULT 'pending',
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  reviewed_at     TEXT,
  FOREIGN KEY (event_id) REFERENCES events(id)
);

-- Sync triggers: keep events_fts in sync with events table
CREATE TRIGGER IF NOT EXISTS trg_events_fts_insert AFTER INSERT ON events BEGIN
  INSERT INTO events_fts(event_id, title, title_cn, raw_summary, summary_cn, ai_summary)
  VALUES (NEW.id, NEW.title, NEW.title_cn, NEW.raw_summary, NEW.summary_cn, NEW.ai_summary);
END;

CREATE TRIGGER IF NOT EXISTS trg_events_fts_delete AFTER DELETE ON events BEGIN
  DELETE FROM events_fts WHERE event_id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_events_fts_update AFTER UPDATE ON events BEGIN
  DELETE FROM events_fts WHERE event_id = OLD.id;
  INSERT INTO events_fts(event_id, title, title_cn, raw_summary, summary_cn, ai_summary)
  VALUES (NEW.id, NEW.title, NEW.title_cn, NEW.raw_summary, NEW.summary_cn, NEW.ai_summary);
END;
