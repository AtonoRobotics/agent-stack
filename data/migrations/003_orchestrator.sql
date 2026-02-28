-- Migration 003: Orchestrator events and agent conversations tables

CREATE TABLE IF NOT EXISTS orchestrator_events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    priority INTEGER DEFAULT 50,
    timestamp TEXT NOT NULL,
    payload TEXT,
    status TEXT DEFAULT 'pending',
    assigned_agents TEXT,
    messages TEXT,
    result TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    message TEXT NOT NULL,
    tool_calls TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES orchestrator_events(id)
);

CREATE INDEX IF NOT EXISTS idx_orch_events_status ON orchestrator_events(status);
CREATE INDEX IF NOT EXISTS idx_orch_events_source ON orchestrator_events(source);
CREATE INDEX IF NOT EXISTS idx_orch_events_created ON orchestrator_events(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_conv_event ON agent_conversations(event_id);
