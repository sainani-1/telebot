import sqlite3
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def connection(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=30)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=30000")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db(path):
    with connection(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          telegram_id INTEGER PRIMARY KEY, name TEXT NOT NULL, qualification TEXT NOT NULL,
          grad_year TEXT NOT NULL, skills TEXT NOT NULL, opportunity_type TEXT NOT NULL,
          location_preference TEXT NOT NULL, min_stipend INTEGER,
          notification_mode TEXT NOT NULL DEFAULT 'matching' CHECK(notification_mode IN ('matching','all')),
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS opportunities(
          id INTEGER PRIMARY KEY AUTOINCREMENT, source_key TEXT UNIQUE NOT NULL, source TEXT NOT NULL,
          title TEXT NOT NULL, company TEXT NOT NULL, skills TEXT DEFAULT '', qualification TEXT DEFAULT '',
          location TEXT DEFAULT 'Not specified', stipend_text TEXT DEFAULT 'Not disclosed', stipend_min INTEGER,
          deadline TEXT DEFAULT 'Not specified', url TEXT NOT NULL, description TEXT DEFAULT '',
          opportunity_type TEXT DEFAULT 'Internship', status TEXT DEFAULT 'published',
          created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_jobs_created ON opportunities(created_at DESC);
        CREATE TABLE IF NOT EXISTS deliveries(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
          opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
          status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt_at TEXT, last_error TEXT, sent_at TEXT,
          UNIQUE(user_id,opportunity_id));
        CREATE INDEX IF NOT EXISTS idx_delivery_queue ON deliveries(status,next_attempt_at);
        CREATE TABLE IF NOT EXISTS source_health(
          source TEXT PRIMARY KEY, last_checked_at TEXT, last_success_at TEXT, last_status TEXT,
          last_error TEXT, items_seen INTEGER DEFAULT 0, new_items INTEGER DEFAULT 0);
        """)
