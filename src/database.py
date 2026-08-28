"""SQLite persistence layer for the IBVAP platform.

Encapsulates all database access behind a single :class:`Database` object
so the detection and alerting layers never touch SQL directly. Connections
are short-lived and created per operation (safe under the GIL and immune
to stale-cursor bugs), with WAL journal mode enabled for crash safety on
remote/embedded deployment.

Schema notes
------------
* ``security_events`` - one row per verified incident
* ``alerts``          - one row per dispatched notification (a notification
  always references the event that produced it, when available)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from models import SecurityAlert, SecurityEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS security_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id       TEXT UNIQUE NOT NULL,
    event_type     TEXT NOT NULL,
    object_type    TEXT NOT NULL,
    track_id       INTEGER NOT NULL,
    camera_id      TEXT NOT NULL,
    timestamp      TEXT NOT NULL,
    frame_number   INTEGER NOT NULL,
    status         TEXT NOT NULL,
    confidence     REAL,
    direction      TEXT,
    evidence_path  TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id       TEXT UNIQUE NOT NULL,
    event_id       TEXT,
    event_type     TEXT NOT NULL,
    object_type    TEXT NOT NULL,
    track_id       INTEGER NOT NULL,
    camera_id      TEXT NOT NULL,
    severity       TEXT NOT NULL,
    status         TEXT NOT NULL,
    message        TEXT NOT NULL,
    timestamp      TEXT NOT NULL,
    frame_number   INTEGER NOT NULL,
    evidence_path  TEXT,
    metadata       TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp   ON security_events (timestamp);
CREATE INDEX IF NOT EXISTS idx_events_track_id    ON security_events (track_id);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp   ON alerts (timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_severity    ON alerts (severity);
"""


class Database:
    """Thread-safe-by-convention SQLite store for events and alerts."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- helpers
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the schema if it does not already exist."""
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def reset(self) -> None:
        """Drop all tables and rebuild an empty schema (dev convenience)."""
        with self._connect() as connection:
            connection.executescript(
                "DROP TABLE IF EXISTS security_events; "
                "DROP TABLE IF EXISTS alerts;"
            )
        self.initialize()

    # ------------------------------------------------------------- write path
    def insert_event(self, event: SecurityEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO security_events (
                    event_id, event_type, object_type, track_id, camera_id,
                    timestamp, frame_number, status, confidence, direction,
                    evidence_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_type.value,
                    event.object_type,
                    event.track_id,
                    event.camera_id,
                    event.timestamp.isoformat(timespec="seconds"),
                    event.frame_number,
                    event.status,
                    round(float(event.confidence), 3),
                    None if event.direction is None else event.direction.value,
                    event.evidence_path,
                ),
            )

    def insert_alert(self, alert: SecurityAlert) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO alerts (
                    alert_id, event_id, event_type, object_type, track_id,
                    camera_id, severity, status, message, timestamp,
                    frame_number, evidence_path, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.alert_id,
                    alert.event_id,
                    alert.event_type.value,
                    alert.object_type,
                    alert.track_id,
                    alert.camera_id,
                    alert.severity.value,
                    alert.status,
                    alert.message,
                    alert.timestamp.isoformat(timespec="seconds"),
                    alert.frame_number,
                    alert.evidence_path,
                    json.dumps(alert.metadata),
                ),
            )

    def upsert_event(self, event: SecurityEvent) -> None:
        """Persist an event, updating ``evidence_path`` if it changed."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO security_events (
                    event_id, event_type, object_type, track_id, camera_id,
                    timestamp, frame_number, status, confidence, direction,
                    evidence_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET evidence_path = excluded.evidence_path
                """,
                (
                    event.event_id,
                    event.event_type.value,
                    event.object_type,
                    event.track_id,
                    event.camera_id,
                    event.timestamp.isoformat(timespec="seconds"),
                    event.frame_number,
                    event.status,
                    round(float(event.confidence), 3),
                    None if event.direction is None else event.direction.value,
                    event.evidence_path,
                ),
            )

    # -------------------------------------------------------------- read path
    def fetch_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM security_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM alerts ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if item.get("metadata"):
                try:
                    item["metadata"] = json.loads(item["metadata"])
                except json.JSONDecodeError:
                    pass
            result.append(item)
        return result

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            events = connection.execute(
                "SELECT COUNT(*) FROM security_events"
            ).fetchone()[0]
            alerts = connection.execute(
                "SELECT COUNT(*) FROM alerts"
            ).fetchone()[0]
        return {"events": int(events), "alerts": int(alerts)}


def initialize_database() -> None:
    """Backwards-compatible top-level initializer for legacy entry points."""
    Database("output/ibvap.db").initialize()