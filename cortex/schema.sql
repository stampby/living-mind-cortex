-- Living Mind — Cortex Memory Schema
-- PostgreSQL with pg_trgm full-text search
-- 17-field memory record per Cortex Memory Complex spec

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- MEMORIES — The primary memory store
-- ============================================================
CREATE TABLE IF NOT EXISTS memories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content         TEXT NOT NULL,
    type            TEXT NOT NULL DEFAULT 'episodic'
                        CHECK (type IN ('episodic','semantic','procedural','relational')),
    tags            TEXT[]          NOT NULL DEFAULT '{}',
    importance      REAL            NOT NULL DEFAULT 0.5
                        CHECK (importance >= 0.0 AND importance <= 1.0),
    created_at      DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now()),
    last_accessed   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    access_count    INTEGER         NOT NULL DEFAULT 0,
    embedding       BYTEA,          -- numpy float32 array, serialized
    emotion         TEXT            NOT NULL DEFAULT 'neutral'
                        CHECK (emotion IN ('neutral','joy','fear','anger','surprise',
                                           'sadness','disgust','curiosity','frustration')),
    confidence      REAL            NOT NULL DEFAULT 1.0
                        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    context         TEXT            NOT NULL DEFAULT '',
    source          TEXT            NOT NULL DEFAULT 'experienced'
                        CHECK (source IN ('experienced','told','generated','inferred')),
    linked_ids      UUID[]          NOT NULL DEFAULT '{}',
    metadata        JSONB           NOT NULL DEFAULT '{}',

    -- Computed / derived
    is_flashbulb    BOOLEAN GENERATED ALWAYS AS (
                        emotion IN ('fear','surprise') AND importance >= 0.8
                    ) STORED,
    is_identity     BOOLEAN GENERATED ALWAYS AS (
                        'identity' = ANY(tags) OR 'self' = ANY(tags)
                    ) STORED
);

-- Full-text search index using pg_trgm
CREATE INDEX IF NOT EXISTS memories_content_trgm
    ON memories USING gin(content gin_trgm_ops);

CREATE INDEX IF NOT EXISTS memories_tags_idx
    ON memories USING gin(tags);

CREATE INDEX IF NOT EXISTS memories_type_idx
    ON memories (type);

CREATE INDEX IF NOT EXISTS memories_importance_idx
    ON memories (importance DESC);

CREATE INDEX IF NOT EXISTS memories_emotion_idx
    ON memories (emotion);

CREATE INDEX IF NOT EXISTS memories_identity_idx
    ON memories (is_identity)
    WHERE is_identity = TRUE;

CREATE INDEX IF NOT EXISTS memories_flashbulb_idx
    ON memories (is_flashbulb)
    WHERE is_flashbulb = TRUE;

CREATE INDEX IF NOT EXISTS memories_created_at_idx
    ON memories (created_at DESC);


-- ============================================================
-- WORKING_MEMORY — Ephemeral salience-gated short-term buffer
-- Not persisted across restarts (cleared on boot)
-- ============================================================
CREATE TABLE IF NOT EXISTS working_memory (
    id          TEXT PRIMARY KEY,        -- wm-1, wm-2, ...
    content     TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'event'
                    CHECK (category IN ('event','decision','outcome','reflex',
                                        'alert','goal','dream','metabolism')),
    salience    REAL NOT NULL DEFAULT 0.5
                    CHECK (salience >= 0.0 AND salience <= 1.0),
    added_at    DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now()),
    metadata    JSONB NOT NULL DEFAULT '{}'
);


-- ============================================================
-- MEMORY_GRAPH — Relationship edges between memories
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_graph (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_id       UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relationship    TEXT NOT NULL DEFAULT 'related',  -- caused, supports, contradicts, etc.
    strength        REAL NOT NULL DEFAULT 0.5,
    created_at      DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now()),
    UNIQUE(source_id, target_id, relationship)
);

CREATE INDEX IF NOT EXISTS memory_graph_source_idx ON memory_graph (source_id);
CREATE INDEX IF NOT EXISTS memory_graph_target_idx ON memory_graph (target_id);


-- ============================================================
-- PRIMING_ACTIVATIONS — Spreading activation state
-- Ephemeral — decays over time, cleared on restart
-- ============================================================
CREATE TABLE IF NOT EXISTS priming_activations (
    memory_id       UUID PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    boost           REAL NOT NULL DEFAULT 0.0,
    activated_at    DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now()),
    decay_duration  INTEGER NOT NULL DEFAULT 180   -- seconds
);


-- ============================================================
-- HORMONE_BUS — Global chemical state snapshot
-- Single-row table, upserted on every pulse
-- ============================================================
CREATE TABLE IF NOT EXISTS hormone_bus (
    id              INTEGER PRIMARY KEY DEFAULT 1,  -- always row 1
    dopamine        REAL NOT NULL DEFAULT 0.7,      -- reward, motivation
    serotonin       REAL NOT NULL DEFAULT 0.6,      -- mood stability
    cortisol        REAL NOT NULL DEFAULT 0.2,      -- stress load
    adrenaline      REAL NOT NULL DEFAULT 0.0,      -- acute threat response
    melatonin       REAL NOT NULL DEFAULT 0.0,      -- sleep pressure
    oxytocin        REAL NOT NULL DEFAULT 0.5,      -- social/bonding signal
    norepinephrine  REAL NOT NULL DEFAULT 0.3,      -- alertness/attention
    valence         TEXT NOT NULL DEFAULT 'neutral', -- positive|negative|neutral
    arousal         REAL NOT NULL DEFAULT 0.5,      -- energy/activation level
    dominant_emotion TEXT NOT NULL DEFAULT 'neutral',
    updated_at      DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now()),
    CONSTRAINT hormone_bus_singleton CHECK (id = 1)
);

INSERT INTO hormone_bus (id) VALUES (1) ON CONFLICT DO NOTHING;


-- ============================================================
-- CIRCADIAN — Body clock state
-- ============================================================
CREATE TABLE IF NOT EXISTS circadian (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    phase           TEXT NOT NULL DEFAULT 'day'
                        CHECK (phase IN ('dawn','day','evening','night')),
    adenosine       REAL NOT NULL DEFAULT 0.0,   -- sleep pressure (builds awake)
    hour_of_day     INTEGER NOT NULL DEFAULT 12,
    updated_at      DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now()),
    CONSTRAINT circadian_singleton CHECK (id = 1)
);

INSERT INTO circadian (id) VALUES (1) ON CONFLICT DO NOTHING;


-- ============================================================
-- ORGAN_REGISTRY — Live census of registered organs
-- ============================================================
CREATE TABLE IF NOT EXISTS organ_registry (
    name        TEXT PRIMARY KEY,
    category    TEXT NOT NULL,   -- Defense|Evolution|Memory|Consciousness|etc.
    status      TEXT NOT NULL DEFAULT 'loaded'
                    CHECK (status IN ('loaded','failed','disabled','quarantined')),
    pulse_freq  INTEGER NOT NULL DEFAULT 1,     -- fire every N pulses
    last_fired  DOUBLE PRECISION,
    fire_count  BIGINT NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    metadata    JSONB NOT NULL DEFAULT '{}',
    registered_at DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now())
);


-- ============================================================
-- AGENT_TRACE — Execution telemetry (every organ fire)
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_trace (
    id          BIGSERIAL PRIMARY KEY,
    organ       TEXT NOT NULL,
    action      TEXT NOT NULL,
    pulse       BIGINT NOT NULL DEFAULT 0,
    success     BOOLEAN NOT NULL DEFAULT TRUE,
    duration_ms INTEGER,
    payload     JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS agent_trace_organ_idx ON agent_trace (organ);
CREATE INDEX IF NOT EXISTS agent_trace_created_at_idx ON agent_trace (created_at DESC);
CREATE INDEX IF NOT EXISTS agent_trace_pulse_idx ON agent_trace (pulse DESC);


-- ============================================================
-- DREAM_JOURNAL — Offline cognition output
-- ============================================================
CREATE TABLE IF NOT EXISTS dream_journal (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy    TEXT NOT NULL,   -- gene_affinity|niche_fill|mutation_replay|toxic_avoidance
    hypothesis  TEXT NOT NULL,
    pattern     TEXT NOT NULL DEFAULT '',
    confidence  REAL NOT NULL DEFAULT 0.5,
    staged      BOOLEAN NOT NULL DEFAULT FALSE,
    pulse       BIGINT NOT NULL DEFAULT 0,
    created_at  DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now())
);


-- ============================================================
-- SESSION_JOURNAL — Wipe-proof session bridge
-- ============================================================
CREATE TABLE IF NOT EXISTS session_journal (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type  TEXT NOT NULL,  -- session_start|session_end|decision|discovery|error_resolved
    summary     TEXT NOT NULL,
    is_identity BOOLEAN NOT NULL DEFAULT FALSE,
    pulse       BIGINT NOT NULL DEFAULT 0,
    metadata    JSONB NOT NULL DEFAULT '{}',
    created_at  DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now())
);

CREATE INDEX IF NOT EXISTS session_journal_identity_idx
    ON session_journal (is_identity)
    WHERE is_identity = TRUE;


-- ============================================================
-- HOMEOSTASIS_LOG — Set-point deviation tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS homeostasis_log (
    id          BIGSERIAL PRIMARY KEY,
    variable    TEXT NOT NULL,
    set_point   REAL NOT NULL,
    actual      REAL NOT NULL,
    deviation   REAL GENERATED ALWAYS AS (actual - set_point) STORED,
    action_taken TEXT,
    pulse       BIGINT NOT NULL DEFAULT 0,
    created_at  DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now())
);


-- ============================================================
-- AGENT_SESSIONS — Tracks every Antigravity (or external agent)
-- conversation session end-to-end. Core research dataset.
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_sessions (
    id              TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL DEFAULT 'antigravity',
    started_at      DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now()),
    ended_at        DOUBLE PRECISION,
    task_context    TEXT NOT NULL DEFAULT '',
    outcome         TEXT CHECK (outcome IN ('success','partial','failure','ongoing')),
    summary         TEXT,
    rating          REAL CHECK (rating >= 0.0 AND rating <= 1.0),
    what_worked     TEXT,
    what_failed     TEXT,
    memory_count    INTEGER NOT NULL DEFAULT 0,
    hormone_snapshot JSONB NOT NULL DEFAULT '{}',   -- hormone state at session start
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS agent_sessions_agent_idx ON agent_sessions (agent_id);
CREATE INDEX IF NOT EXISTS agent_sessions_started_idx ON agent_sessions (started_at DESC);
CREATE INDEX IF NOT EXISTS agent_sessions_outcome_idx ON agent_sessions (outcome);


-- ============================================================
-- MEMORIES — Pillar 6 additions (safe ALTER, idempotent)
-- counterfactual_of: fork-point provenance (the "git log")
-- agent_session_id: which agent session wrote this memory
-- ============================================================
DO $$ BEGIN
    ALTER TABLE memories ADD COLUMN counterfactual_of UUID REFERENCES memories(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_column THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE memories ADD COLUMN agent_session_id TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_column THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS memories_counterfactual_idx ON memories (counterfactual_of) WHERE counterfactual_of IS NOT NULL;
CREATE INDEX IF NOT EXISTS memories_agent_session_idx ON memories (agent_session_id) WHERE agent_session_id IS NOT NULL;


-- ============================================================
-- LINEAGE_SNAPSHOTS — Evolver genome archive (Pillar 7)
-- Every accepted mutation is checkpointed here.
-- ============================================================
CREATE TABLE IF NOT EXISTS lineage_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    phase_config    JSONB NOT NULL DEFAULT '{}',
    hormone_genome  JSONB NOT NULL DEFAULT '{}',
    fitness         REAL NOT NULL DEFAULT 0.0,
    session_ratings JSONB NOT NULL DEFAULT '[]',
    accepted_at     DOUBLE PRECISION NOT NULL DEFAULT extract(epoch from now()),
    generation      INTEGER NOT NULL DEFAULT 0,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS lineage_snapshots_accepted_idx ON lineage_snapshots (accepted_at DESC);
