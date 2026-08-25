# NordicSignal database schema
import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "nordicsignal.db"
DB_PATH = Path(os.getenv("NORDICSIGNAL_DB_PATH", str(DEFAULT_DB_PATH))).expanduser().resolve()

SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    exchange TEXT DEFAULT 'Oslo Børs',
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    price REAL,
    change_pct REAL,
    volume INTEGER,
    captured_at TEXT NOT NULL,
    FOREIGN KEY(ticker) REFERENCES stocks(ticker)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker TEXT PRIMARY KEY,
    revenue REAL,
    ebitda REAL,
    ebit REAL,
    eps REAL,
    free_cash_flow REAL,
    net_debt REAL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(ticker) REFERENCES stocks(ticker)
);

CREATE TABLE IF NOT EXISTS insider_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    person TEXT,
    role TEXT,
    transaction_type TEXT,
    shares REAL,
    price REAL,
    trade_date TEXT,
    source TEXT,
    FOREIGN KEY(ticker) REFERENCES stocks(ticker)
);

CREATE TABLE IF NOT EXISTS short_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    holder TEXT,
    short_pct REAL,
    position_date TEXT,
    source TEXT,
    FOREIGN KEY(ticker) REFERENCES stocks(ticker)
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    fundamentals INTEGER NOT NULL,
    insider INTEGER NOT NULL,
    valuation INTEGER NOT NULL,
    sentiment INTEGER NOT NULL,
    total INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    source TEXT DEFAULT 'stored',
    FOREIGN KEY(ticker) REFERENCES stocks(ticker)
);

CREATE TABLE IF NOT EXISTS watchlist (
    ticker TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    FOREIGN KEY(ticker) REFERENCES stocks(ticker)
);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    conn.executescript(SCHEMA)
    try:
        conn.execute("ALTER TABLE scores ADD COLUMN source TEXT DEFAULT 'stored'")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()
