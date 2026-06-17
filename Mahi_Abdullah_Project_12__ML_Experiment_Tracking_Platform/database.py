"""SQLite database access layer for the ML Experiment Tracking platform."""

import os
import sqlite3
from typing import Optional

# Path to the SQLite file. Resolves relative to this module so the DB lives
# next to the application regardless of the working directory used at launch.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "experiments.db")


def get_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a SQLite connection.

    The database file is created automatically if it does not exist.
    Row access by column name is enabled for ergonomic querying.
    """
    path = db_path or DB_PATH
    # `check_same_thread=False` lets the connection be shared across threads
    # (Flask's default threaded development server is one such case).
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Create the `experiments` and `epoch_metrics` tables if missing."""
    conn = get_db(db_path)
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                project     TEXT,
                tags        TEXT,
                params      TEXT,   -- JSON text
                metrics     TEXT,   -- JSON text
                notes       TEXT,
                status      TEXT    DEFAULT 'running',
                created_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
                end_time    TEXT
            )
            """
        )

        # Lightweight in-place migration for databases created by Prompt 1
        # (which lacked the `end_time` column). Safe to run on every startup.
        existing_cols = {
            row["name"]
            for row in cursor.execute("PRAGMA table_info(experiments)")
        }
        if "end_time" not in existing_cols:
            cursor.execute("ALTER TABLE experiments ADD COLUMN end_time TEXT")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS epoch_metrics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id   INTEGER NOT NULL,
                metric_name     TEXT    NOT NULL,
                value           REAL    NOT NULL,
                step            INTEGER NOT NULL,
                FOREIGN KEY (experiment_id) REFERENCES experiments (id)
                    ON DELETE CASCADE
            )
            """
        )

        # Index speeds up per-experiment metric lookups.
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_epoch_metrics_experiment_id
                ON epoch_metrics (experiment_id)
            """
        )

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    # Allow `python database.py` to (re)initialize the schema on demand.
    init_db()
    print(f"Initialized database at {DB_PATH}")
