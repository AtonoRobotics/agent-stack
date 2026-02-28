-- Migration 002: Create robots table (replaces repos.yml for robot registry)

CREATE TABLE IF NOT EXISTS robots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'arm',
    dof INTEGER DEFAULT 6,
    max_payload_kg REAL,
    reach_mm REAL,
    serial TEXT,
    status TEXT DEFAULT 'active',
    urdf_path TEXT,
    mesh_dir TEXT,
    tcp_host TEXT,
    tcp_ports TEXT,
    data_source TEXT DEFAULT 'ros2',
    created TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Seed with Dobot CR10 data
INSERT OR IGNORE INTO robots (id, name, type, dof, max_payload_kg, reach_mm, serial, status, urdf_path, mesh_dir, tcp_host, tcp_ports, data_source)
VALUES (
    'dobot_cr10',
    'Dobot CR10',
    'arm',
    6,
    10.0,
    1525.0,
    'CR10-2026-0001',
    'active',
    '/home/samuel/dobot_cr10/cr10_robot.urdf',
    '/home/samuel/dobot-cr10-stack/meshes',
    '192.168.5.1',
    '{"dashboard": 29999, "control": 30003, "feedback": 30004}',
    'ros2'
);
