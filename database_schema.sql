-- SQLite schema used by the application.
-- The database is created automatically by manufacturing_planning_tool.py.

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    azmana_no TEXT NOT NULL,
    thickness_mm INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS metals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    role TEXT CHECK(role IN ('up','down')) NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    hazit_index INTEGER NOT NULL,
    pack_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pack_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL,
    size_mm INTEGER NOT NULL,
    count INTEGER NOT NULL,
    mufa_role TEXT CHECK(mufa_role IN ('F','R')) NULL,
    mufa_value INTEGER NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(pack_id) REFERENCES packs(id) ON DELETE CASCADE
);
