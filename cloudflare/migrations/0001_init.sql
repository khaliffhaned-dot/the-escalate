-- Initial D1 schema (SQLite). Port of the core Postgres tables.
-- Tenant isolation: every table has workspace_id / org_id; enforce in queries.

CREATE TABLE IF NOT EXISTS organisations (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  tier TEXT DEFAULT 'desk',
  status TEXT DEFAULT 'trial',
  data_region TEXT DEFAULT 'ap-southeast-1',
  retention_days INTEGER DEFAULT 396,
  ave_enabled INTEGER DEFAULT 0 CHECK (ave_enabled = 0),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT DEFAULT 'brand',
  status TEXT DEFAULT 'active',
  timezone TEXT DEFAULT 'Asia/Kuala_Lumpur',
  locale TEXT DEFAULT 'en',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (org_id) REFERENCES organisations(id)
);

CREATE TABLE IF NOT EXISTS war_rooms (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  status TEXT DEFAULT 'open',
  severity TEXT DEFAULT 'medium',
  title TEXT NOT NULL,
  locale TEXT DEFAULT 'bilingual',
  trigger_json TEXT,
  three_r_json TEXT,
  listed_json TEXT,
  opened_at TEXT,
  opened_by TEXT,
  contained_at TEXT,
  closed_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

CREATE INDEX IF NOT EXISTS idx_war_rooms_ws ON war_rooms(workspace_id, status);

CREATE TABLE IF NOT EXISTS holdings (
  id TEXT PRIMARY KEY,
  brief_id TEXT,
  war_room_id TEXT,
  workspace_id TEXT NOT NULL,
  status TEXT DEFAULT 'draft',
  locale TEXT DEFAULT 'bilingual',
  lines_json TEXT,
  human_must_send INTEGER DEFAULT 1 CHECK (human_must_send = 1),
  auto_publish INTEGER DEFAULT 0 CHECK (auto_publish = 0),
  ave INTEGER DEFAULT 0 CHECK (ave = 0),
  model_version TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_holdings_ws ON holdings(workspace_id, status);
