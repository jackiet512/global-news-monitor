PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS news_context (
  fingerprint TEXT PRIMARY KEY,
  polymarket_json TEXT,
  community_json TEXT,
  query_terms TEXT,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_context_updated ON news_context(updated_at DESC);