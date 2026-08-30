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
<<<<<<< HEAD
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
    evidence_path  TEXT,
    plate_text     TEXT,
    plate_confidence REAL,
    plate_crop_path  TEXT
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
=======
import os
import re

>>>>>>> 37ad1e73dec538c3cd215f8157a05815d0c44f3c


# Nullable columns added iteratively as the platform grows. Cross-version
# databases are upgraded in-place by _migrate() below.
_ANPR_COLUMNS: dict[str, str] = {
    "plate_text": "TEXT",
    "plate_confidence": "REAL",
    "plate_crop_path": "TEXT",
}


class Database:
    """Thread-safe-by-convention SQLite store for events and alerts."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Guarded, idempotent schema migration for databases created by older
        # versions of IBVAP so they continue to open without error.
        self._migrate()

<<<<<<< HEAD
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
=======
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            event_type TEXT,
            object_type TEXT,
            track_id INTEGER,
            camera_id TEXT,
            timestamp TEXT,
            frame_number INTEGER,
            status TEXT,
            evidence_path TEXT
        )
    """)
        
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT UNIQUE,
            vehicle_type TEXT,
            owner TEXT,
            status TEXT
        )
    """)
>>>>>>> 37ad1e73dec538c3cd215f8157a05815d0c44f3c

    def _migrate(self) -> None:
        """Add columns that have appeared in newer schemas, in place."""
        with self._connect() as connection:
            connection.executescript(_SCHEMA)  # ensure base tables exist
            self._add_missing_columns(connection, "security_events", _ANPR_COLUMNS)

    @staticmethod
    def _add_missing_columns(
        connection: sqlite3.Connection,
        table: str,
        columns: dict[str, str],
    ) -> None:
        existing = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, declaration in columns.items():
            if name in existing:
                continue
            # Note: SQLite (tested up to 3.50) rejects
            # ``ADD COLUMN IF NOT EXISTS`` with a syntax error, so the guard
            # must come from the PRAGMA inspection above.
            connection.execute(
                f'ALTER TABLE {table} ADD COLUMN "{name}" {declaration}'
            )

    def initialize(self) -> None:
        """Create the schema if it does not already exist (idempotent)."""
        self._migrate()

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
                    evidence_path, plate_text, plate_confidence, plate_crop_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    event.plate_text,
                    (
                        None
                        if event.plate_confidence is None
                        else round(float(event.plate_confidence), 3)
                    ),
                    event.plate_crop_path,
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


<<<<<<< HEAD
def initialize_database() -> None:
    """Backwards-compatible top-level initializer for legacy entry points."""
    Database("output/ibvap.db").initialize()
=======
def save_event(event):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO security_events (
            event_id,
            event_type,
            object_type,
            track_id,
            camera_id,
            timestamp,
            frame_number,
            status,
            evidence_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        event["event_id"],
        event["event_type"],
        event["object"],
        event["track_id"],
        event["camera_id"],
        event["timestamp"],
        event["frame_number"],
        event["status"],
        event["evidence_path"]
    ))

    connection.commit()
    connection.close()


def get_events():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM security_events
        ORDER BY id DESC
    """)

    events = cursor.fetchall()

    connection.close()

    return events

def get_next_event_number():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM security_events
    """)

    count = cursor.fetchone()[0]

    connection.close()

    return count + 1


def get_vehicle_by_plate(plate_number):
    if not plate_number:
        return None

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT plate_number, vehicle_type, owner, status
        FROM vehicles
    """)
    vehicles = cursor.fetchall()
    connection.close()

    def clean_str(s):
        return re.sub(r'[^A-Z0-9]', '', str(s).upper())

    target = clean_str(plate_number)
    if not target:
        return None

    # Common OCR character mappings for fuzzy matching
    substitutions = [
        ('1', 'I'), ('I', '1'),
        ('0', 'O'), ('O', '0'),
        ('8', 'B'), ('B', '8')
    ]

    candidates = {target}
    for orig, repl in substitutions:
        candidates.add(target.replace(orig, repl))

    import difflib

    for row in vehicles:
        db_plate, vehicle_type, owner, status = row
        db_norm = clean_str(db_plate)

        if db_norm in candidates or target in db_norm or db_norm in target:
            return {
                "plate_number": db_plate,
                "vehicle_type": vehicle_type,
                "owner": owner,
                "status": status
            }

        # Sequence similarity check (e.g. A7060EC vs AI7060EC yields ~0.93 similarity)
        similarity = difflib.SequenceMatcher(None, target, db_norm).ratio()
        if similarity >= 0.70:
            return {
                "plate_number": db_plate,
                "vehicle_type": vehicle_type,
                "owner": owner,
                "status": status
            }

    return None


def get_suspicious_activities():
    """Retrieves list of suspicious activities from database."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suspicious_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id TEXT UNIQUE,
            track_id INTEGER,
            activity_type TEXT,
            severity TEXT,
            description TEXT,
            timestamp TEXT
        )
    """)

    cursor.execute("""
        SELECT activity_id, track_id, activity_type, severity, description, timestamp
        FROM suspicious_activities
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    connection.close()

    return [
        {
            "activity_id": r[0],
            "track_id": r[1],
            "activity_type": r[2],
            "severity": r[3],
            "description": r[4],
            "timestamp": r[5]
        }
        for r in rows
    ]


def get_blockchain_ledger_records():
    """Retrieves full blockchain audit ledger."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blockchain_ledger (
            block_index INTEGER PRIMARY KEY,
            event_id TEXT UNIQUE,
            previous_hash TEXT,
            block_hash TEXT,
            evidence_hash TEXT,
            timestamp TEXT,
            nonce INTEGER,
            data_json TEXT
        )
    """)

    cursor.execute("""
        SELECT block_index, event_id, previous_hash, block_hash, evidence_hash, timestamp, nonce, data_json
        FROM blockchain_ledger
        ORDER BY block_index DESC
    """)
    rows = cursor.fetchall()
    connection.close()

    return [
        {
            "block_index": r[0],
            "event_id": r[1],
            "previous_hash": r[2],
            "block_hash": r[3],
            "evidence_hash": r[4],
            "timestamp": r[5],
            "nonce": r[6],
            "data_json": r[7]
        }
        for r in rows
    ]


def get_system_analytics():
    """Calculates live analytics metrics for CYPHER command dashboard."""

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM security_events")
    total_events = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM vehicles")
    registered_vehicles = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM security_events WHERE status = 'UNAUTHORIZED'")
    unauthorized_intrusions = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM security_events WHERE status = 'VERIFIED_VEHICLE'")
    verified_entries = cursor.fetchone()[0]

    connection.close()

    threat_level = "CRITICAL" if unauthorized_intrusions > 2 else "HIGH" if unauthorized_intrusions > 0 else "NORMAL"

    return {
        "total_events": total_events,
        "registered_vehicles": registered_vehicles,
        "unauthorized_intrusions": unauthorized_intrusions,
        "verified_entries": verified_entries,
        "threat_level": threat_level
    }

>>>>>>> 37ad1e73dec538c3cd215f8157a05815d0c44f3c
