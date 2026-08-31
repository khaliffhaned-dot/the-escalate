-- NADI (The pulse of Malaysia) — PostgreSQL Schema with Row-Level Security (RLS)
-- AMEC / Barcelona Principles 4.0 Compliant (No AVE, Human Must Send, Tenant Isolation)

-- 1. Organizations
CREATE TABLE IF NOT EXISTS organizations (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    tier VARCHAR(64) DEFAULT 'growth',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Workspaces
CREATE TABLE IF NOT EXISTS workspaces (
    id VARCHAR(64) PRIMARY KEY,
    org_id VARCHAR(64) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_workspaces_org_id_slug ON workspaces(org_id, slug);

-- 3. Users
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    org_id VARCHAR(64) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    org_role VARCHAR(64) DEFAULT 'analyst',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_users_org_id ON users(org_id);

-- 4. Workspace Memberships
CREATE TABLE IF NOT EXISTS workspace_memberships (
    id SERIAL PRIMARY KEY,
    org_id VARCHAR(64) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    workspace_id VARCHAR(64) NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ws_role VARCHAR(64) NOT NULL,
    CONSTRAINT uq_workspace_memberships_tenant UNIQUE (org_id, workspace_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_ws_membership_tenant ON workspace_memberships(org_id, workspace_id, user_id);

-- 5. Mentions
CREATE TABLE IF NOT EXISTS mentions (
    id VARCHAR(64) PRIMARY KEY,
    org_id VARCHAR(64) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    workspace_id VARCHAR(64) NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    published_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    platform VARCHAR(32) NOT NULL,
    lang VARCHAR(16) DEFAULT 'en',
    script VARCHAR(32) DEFAULT 'latin',
    url VARCHAR(1024),
    author_handle VARCHAR(255),
    author_name VARCHAR(255),
    author_kind VARCHAR(64) DEFAULT 'public',
    outlet_name VARCHAR(255),
    outlet_tier VARCHAR(64),
    text TEXT NOT NULL,
    excerpt TEXT,
    sentiment JSONB DEFAULT '{}'::jsonb,
    three_r JSONB DEFAULT '{}'::jsonb,
    state VARCHAR(64),
    east_my BOOLEAN DEFAULT FALSE,
    engagement JSONB DEFAULT '{}'::jsonb,
    codes JSONB DEFAULT '[]'::jsonb,
    peso VARCHAR(32) DEFAULT 'earned',
    starred BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS ix_mentions_tenant_published ON mentions(org_id, workspace_id, published_at);
CREATE INDEX IF NOT EXISTS ix_mentions_platform ON mentions(org_id, workspace_id, platform);

-- 6. Evaluation Snapshots (Locked & Immutable under Barcelona 4.0)
CREATE TABLE IF NOT EXISTS evaluation_snapshots (
    id VARCHAR(64) PRIMARY KEY,
    org_id VARCHAR(64) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    workspace_id VARCHAR(64) NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    schema_version VARCHAR(16) DEFAULT '1.0.0',
    status VARCHAR(32) DEFAULT 'locked',
    title VARCHAR(255) NOT NULL,
    campaign JSONB DEFAULT '{}'::jsonb,
    window JSONB NOT NULL,
    locale VARCHAR(16) DEFAULT 'en',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by JSONB DEFAULT '{}'::jsonb,
    supersedes_id VARCHAR(64),
    methodology JSONB DEFAULT '{"ave": false, "principles": "Barcelona Principles 4.0"}'::jsonb,
    inputs JSONB DEFAULT '{}'::jsonb,
    objectives JSONB DEFAULT '[]'::jsonb,
    ladder JSONB DEFAULT '{}'::jsonb,
    contribution JSONB DEFAULT '{}'::jsonb,
    moves JSONB DEFAULT '[]'::jsonb,
    governance JSONB DEFAULT '{}'::jsonb,
    integrity JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT chk_no_ave_eval CHECK ((methodology->>'ave')::boolean IS NOT TRUE)
);
CREATE INDEX IF NOT EXISTS ix_eval_snapshots_tenant ON evaluation_snapshots(org_id, workspace_id, created_at);

-- 7. War Rooms (Crisis Management)
CREATE TABLE IF NOT EXISTS war_rooms (
    id VARCHAR(64) PRIMARY KEY,
    org_id VARCHAR(64) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    workspace_id VARCHAR(64) NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    schema_version VARCHAR(16) DEFAULT '1.0.0',
    status VARCHAR(32) DEFAULT 'open',
    severity VARCHAR(32) DEFAULT 'medium',
    title VARCHAR(255) NOT NULL,
    locale VARCHAR(32) DEFAULT 'bilingual',
    campaign_id VARCHAR(64),
    trigger JSONB DEFAULT '{}'::jsonb,
    three_r JSONB DEFAULT '{}'::jsonb,
    policy JSONB DEFAULT '{"auto_publish": false, "ave": false, "human_send": true}'::jsonb,
    queues JSONB DEFAULT '{}'::jsonb,
    holdings JSONB DEFAULT '[]'::jsonb,
    media JSONB DEFAULT '{}'::jsonb,
    decisions JSONB DEFAULT '[]'::jsonb,
    links JSONB DEFAULT '{}'::jsonb,
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    opened_by VARCHAR(255) DEFAULT 'system',
    contained_at TIMESTAMP WITH TIME ZONE,
    closed_at TIMESTAMP WITH TIME ZONE,
    methodology JSONB DEFAULT '{"ave": false, "auto_publish": false}'::jsonb,
    CONSTRAINT chk_no_ave_war_room CHECK ((policy->>'ave')::boolean IS NOT TRUE)
);
CREATE INDEX IF NOT EXISTS ix_war_rooms_tenant_status ON war_rooms(org_id, workspace_id, status);

-- 8. Holdings (Holding Briefs)
CREATE TABLE IF NOT EXISTS holdings (
    id VARCHAR(64) PRIMARY KEY,
    brief_id VARCHAR(64) NOT NULL,
    org_id VARCHAR(64) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    workspace_id VARCHAR(64) NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    war_room_id VARCHAR(64) REFERENCES war_rooms(id) ON DELETE SET NULL,
    status VARCHAR(32) DEFAULT 'draft',
    locale VARCHAR(32) DEFAULT 'bilingual',
    audience VARCHAR(32) DEFAULT 'press',
    version INT DEFAULT 1,
    facts_used JSONB DEFAULT '[]'::jsonb,
    gaps JSONB DEFAULT '[]'::jsonb,
    lines JSONB DEFAULT '{}'::jsonb,
    do_not_say JSONB DEFAULT '[]'::jsonb,
    ops JSONB DEFAULT '[]'::jsonb,
    posture VARCHAR(64) DEFAULT 'self_regulated_not_directed',
    auto_publish BOOLEAN DEFAULT FALSE,
    ave BOOLEAN DEFAULT FALSE,
    human_must_send BOOLEAN DEFAULT TRUE,
    model_version VARCHAR(64) DEFAULT 'nadi-brief-2026-08',
    prompt_hash VARCHAR(64) DEFAULT '',
    methodology JSONB DEFAULT '{"ave": false, "principles": "Barcelona Principles 4.0"}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT chk_holding_no_ave CHECK (ave IS NOT TRUE),
    CONSTRAINT chk_holding_no_autopublish CHECK (auto_publish IS NOT TRUE),
    CONSTRAINT chk_holding_human_send CHECK (human_must_send IS TRUE)
);
CREATE INDEX IF NOT EXISTS ix_holdings_tenant ON holdings(org_id, workspace_id, status);

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- Multi-Tenant Isolation by org_id and workspace_id
-- ============================================================================

-- Enable RLS on all tenant-specific tables
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE mentions ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE war_rooms ENABLE ROW LEVEL SECURITY;
ALTER TABLE holdings ENABLE ROW LEVEL SECURITY;

-- Workspaces Policy
CREATE POLICY rls_workspaces_tenant ON workspaces
    FOR ALL
    USING (
        org_id = current_setting('app.current_org_id', true)
    );

-- Workspace Memberships Policy
CREATE POLICY rls_ws_memberships_tenant ON workspace_memberships
    FOR ALL
    USING (
        org_id = current_setting('app.current_org_id', true)
        AND workspace_id = current_setting('app.current_workspace_id', true)
    );

-- Mentions Policy
CREATE POLICY rls_mentions_tenant ON mentions
    FOR ALL
    USING (
        org_id = current_setting('app.current_org_id', true)
        AND workspace_id = current_setting('app.current_workspace_id', true)
    );

-- Evaluation Snapshots Policy
CREATE POLICY rls_eval_snapshots_tenant ON evaluation_snapshots
    FOR ALL
    USING (
        org_id = current_setting('app.current_org_id', true)
        AND workspace_id = current_setting('app.current_workspace_id', true)
    );

-- War Rooms Policy
CREATE POLICY rls_war_rooms_tenant ON war_rooms
    FOR ALL
    USING (
        org_id = current_setting('app.current_org_id', true)
        AND workspace_id = current_setting('app.current_workspace_id', true)
    );

-- Holdings Policy
CREATE POLICY rls_holdings_tenant ON holdings
    FOR ALL
    USING (
        org_id = current_setting('app.current_org_id', true)
        AND workspace_id = current_setting('app.current_workspace_id', true)
    );
