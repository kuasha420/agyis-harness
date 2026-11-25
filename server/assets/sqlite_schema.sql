CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    start_time TEXT,
    end_time TEXT,
    duration_seconds REAL,
    total_steps INTEGER,
    model TEXT,
    workspace_path TEXT,
    transcript_path TEXT,
    file_size_bytes INTEGER,
    has_errors INTEGER,
    tool_call_count INTEGER,
    tool_error_count INTEGER,
    intervention_count INTEGER,
    origin_developer TEXT DEFAULT 'local',
    remote_synced_at TEXT DEFAULT NULL,
    origin_machine TEXT,
    client_surface TEXT,
    source_kind TEXT,
    model_slug TEXT,
    model_display_name TEXT,
    max_context_tokens INTEGER,
    total_input_tokens INTEGER,
    total_cache_read_tokens INTEGER,
    total_output_tokens INTEGER,
    total_thought_tokens INTEGER,
    peak_context_tokens INTEGER,
    server_seq INTEGER
);

CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    step_index INTEGER,
    step_type TEXT,
    source TEXT,
    status TEXT,
    created_at TEXT,
    content_length INTEGER,
    content_snippet TEXT,
    has_thinking INTEGER,
    thinking_length INTEGER,
    tool_count INTEGER,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    step_index INTEGER,
    result_step_index INTEGER,
    tool_name TEXT,
    arguments_json TEXT,
    arguments_snippet TEXT,
    target_path TEXT,
    command_line TEXT,
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL,
    status TEXT,
    exit_code INTEGER,
    error_snippet TEXT,
    is_loop_candidate INTEGER DEFAULT 0,
    output_length_chars INTEGER,
    output_lines INTEGER,
    arguments_length_chars INTEGER,
    command_category TEXT,
    is_truncated INTEGER DEFAULT 0,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS user_interventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    step_index INTEGER,
    created_at TEXT,
    prompt_text TEXT,
    prompt_length INTEGER,
    preceding_tool_failed INTEGER,
    preceding_tool_name TEXT,
    preceding_error_snippet TEXT,
    intervention_type TEXT,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_steps_uniq ON steps(session_id, step_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_interventions_uniq ON user_interventions(session_id, step_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_calls_uniq ON tool_calls(session_id, step_index, tool_name, started_at, arguments_snippet);
CREATE INDEX IF NOT EXISTS idx_sessions_origin ON sessions(origin_developer);
CREATE INDEX IF NOT EXISTS idx_sessions_synced ON sessions(remote_synced_at);
CREATE INDEX IF NOT EXISTS idx_sessions_machine ON sessions(origin_machine);
CREATE INDEX IF NOT EXISTS idx_sessions_server_seq ON sessions(server_seq);
CREATE INDEX IF NOT EXISTS idx_sessions_cursor ON sessions(remote_synced_at, session_id);
CREATE INDEX IF NOT EXISTS idx_steps_session ON steps(session_id);
CREATE INDEX IF NOT EXISTS idx_tools_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_interventions_session ON user_interventions(session_id);
