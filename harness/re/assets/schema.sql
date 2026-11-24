CREATE TABLE IF NOT EXISTS binaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    sha256 TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    architecture TEXT,
    format TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS functions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    binary_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    address INTEGER NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    signature TEXT,
    is_exported INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(binary_id) REFERENCES binaries(id)
);

CREATE TABLE IF NOT EXISTS strings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    binary_id INTEGER NOT NULL,
    value TEXT NOT NULL,
    address INTEGER,
    length INTEGER NOT NULL DEFAULT 0,
    encoding TEXT DEFAULT 'utf-8',
    FOREIGN KEY(binary_id) REFERENCES binaries(id)
);

CREATE TABLE IF NOT EXISTS rtti_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    binary_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    vtable_address INTEGER,
    base_classes TEXT,
    FOREIGN KEY(binary_id) REFERENCES binaries(id)
);

CREATE TABLE IF NOT EXISTS packets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pcap_name TEXT NOT NULL,
    frame_number INTEGER NOT NULL,
    timestamp REAL,
    proto TEXT,
    src_ip TEXT,
    dst_ip TEXT,
    src_port INTEGER,
    dst_port INTEGER,
    payload_len INTEGER,
    summary TEXT,
    binary_id INTEGER,
    run_id INTEGER,
    FOREIGN KEY(binary_id) REFERENCES binaries(id),
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    exit_code INTEGER,
    log_path TEXT,
    binary_id INTEGER,
    FOREIGN KEY(binary_id) REFERENCES binaries(id)
);

CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name);
CREATE INDEX IF NOT EXISTS idx_functions_address ON functions(address);
CREATE INDEX IF NOT EXISTS idx_strings_value ON strings(value);
CREATE INDEX IF NOT EXISTS idx_strings_address ON strings(address);
CREATE INDEX IF NOT EXISTS idx_rtti_name ON rtti_classes(name);
CREATE INDEX IF NOT EXISTS idx_packets_pcap ON packets(pcap_name);
CREATE INDEX IF NOT EXISTS idx_packets_binary ON packets(binary_id);
CREATE INDEX IF NOT EXISTS idx_packets_run ON packets(run_id);
