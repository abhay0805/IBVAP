"""SQLite persistence layer for the IBVAP platform.

Encapsulates all database access behind the :class:`Database` object and
provides backwards-compatible module-level helper functions for legacy scripts.
Connections are short-lived and created per operation, with WAL journal mode
enabled for crash safety and concurrent access.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from models import SecurityAlert, SecurityEvent

DB_PATH = Path("output/ibvap.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS security_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id         TEXT UNIQUE NOT NULL,
    event_type       TEXT NOT NULL,
    object_type      TEXT NOT NULL,
    track_id         INTEGER NOT NULL,
    camera_id        TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    frame_number     INTEGER NOT NULL,
    status           TEXT NOT NULL,
    confidence       REAL,
    direction        TEXT,
    evidence_path    TEXT,
    plate_text       TEXT,
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

CREATE TABLE IF NOT EXISTS vehicles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT UNIQUE,
    vehicle_type TEXT,
    owner        TEXT,
    status       TEXT
);

CREATE TABLE IF NOT EXISTS suspicious_activities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id   TEXT UNIQUE,
    track_id      INTEGER,
    activity_type TEXT,
    severity      TEXT,
    description   TEXT,
    timestamp     TEXT
);

CREATE TABLE IF NOT EXISTS blockchain_ledger (
    block_index   INTEGER PRIMARY KEY,
    event_id      TEXT UNIQUE,
    previous_hash TEXT,
    block_hash    TEXT,
    evidence_hash TEXT,
    timestamp     TEXT,
    nonce         INTEGER,
    data_json     TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp   ON security_events (timestamp);
CREATE INDEX IF NOT EXISTS idx_events_track_id    ON security_events (track_id);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp   ON alerts (timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_severity    ON alerts (severity);
"""

_DEFAULT_VEHICLES = [
    ("AI 7060 EC", "Car", "Commander Vance (Base Security)", "VERIFIED"),
    ("AA 3325 MM", "Truck", "Supply Logistics Unit 4", "VERIFIED"),
    ("MH 12 AB 1234", "Patrol SUV", "Quick Reaction Team", "VERIFIED"),
    ("DL 01 AB 1234", "Sedan", "HQ Escort Vehicle", "VERIFIED"),
    ("KA 05 MN 9999", "Armored Van", "Border Logistics", "VERIFIED"),
]

# Nullable columns added iteratively as the platform grows.
_ANPR_COLUMNS: dict[str, str] = {
    "plate_text": "TEXT",
    "plate_confidence": "REAL",
    "plate_crop_path": "TEXT",
}


class Database:
    """Thread-safe-by-convention SQLite store for events, alerts, and analytics."""

    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    # ---------------------------------------------------------------- helpers
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _migrate(self) -> None:
        """Add tables and missing columns in-place and seed default vehicles."""
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            self._add_missing_columns(connection, "security_events", _ANPR_COLUMNS)
            # Seed default registry if empty
            count = connection.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
            if count == 0:
                for row in _DEFAULT_VEHICLES:
                    connection.execute(
                        "INSERT OR IGNORE INTO vehicles (plate_number, vehicle_type, owner, status) "
                        "VALUES (?, ?, ?, ?)",
                        row,
                    )

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
                "DROP TABLE IF EXISTS alerts; "
                "DROP TABLE IF EXISTS vehicles; "
                "DROP TABLE IF EXISTS suspicious_activities; "
                "DROP TABLE IF EXISTS blockchain_ledger;"
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
                    event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                    event.object_type,
                    event.track_id,
                    event.camera_id,
                    event.timestamp.isoformat(timespec="seconds") if hasattr(event.timestamp, "isoformat") else str(event.timestamp),
                    event.frame_number,
                    event.status,
                    round(float(event.confidence), 3) if event.confidence is not None else 0.0,
                    None if event.direction is None else (event.direction.value if hasattr(event.direction, "value") else str(event.direction)),
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
                    alert.event_type.value if hasattr(alert.event_type, "value") else str(alert.event_type),
                    alert.object_type,
                    alert.track_id,
                    alert.camera_id,
                    alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
                    alert.status,
                    alert.message,
                    alert.timestamp.isoformat(timespec="seconds") if hasattr(alert.timestamp, "isoformat") else str(alert.timestamp),
                    alert.frame_number,
                    alert.evidence_path,
                    json.dumps(alert.metadata) if isinstance(alert.metadata, dict) else str(alert.metadata or "{}"),
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
                    evidence_path, plate_text, plate_confidence, plate_crop_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    evidence_path = excluded.evidence_path,
                    plate_text = COALESCE(excluded.plate_text, security_events.plate_text),
                    plate_confidence = COALESCE(excluded.plate_confidence, security_events.plate_confidence),
                    plate_crop_path = COALESCE(excluded.plate_crop_path, security_events.plate_crop_path)
                """,
                (
                    event.event_id,
                    event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                    event.object_type,
                    event.track_id,
                    event.camera_id,
                    event.timestamp.isoformat(timespec="seconds") if hasattr(event.timestamp, "isoformat") else str(event.timestamp),
                    event.frame_number,
                    event.status,
                    round(float(event.confidence), 3) if event.confidence is not None else 0.0,
                    None if event.direction is None else (event.direction.value if hasattr(event.direction, "value") else str(event.direction)),
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


# -----------------------------------------------------------------------------
# Module-level convenience functions for backwards compatibility
# -----------------------------------------------------------------------------

_default_db: Database | None = None


def get_default_db() -> Database:
    global _default_db
    if _default_db is None:
        _default_db = Database(DB_PATH)
    return _default_db


def initialize_database(db_path: Path | str | None = None) -> None:
    """Backwards-compatible top-level initializer for legacy entry points."""
    global _default_db
    if db_path:
        _default_db = Database(db_path)
    else:
        _default_db = Database(DB_PATH)
    _default_db.initialize()


def save_event(event: dict[str, Any] | SecurityEvent) -> None:
    db = get_default_db()
    if isinstance(event, SecurityEvent):
        db.insert_event(event)
        return

    with db._connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO security_events (
                event_id, event_type, object_type, track_id, camera_id,
                timestamp, frame_number, status, confidence, direction,
                evidence_path, plate_text, plate_confidence, plate_crop_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("event_id"),
                event.get("event_type", "VIRTUAL_FENCE_BREACH"),
                event.get("object", event.get("object_type", "unknown")),
                event.get("track_id", 0),
                event.get("camera_id", "BOP-CAM-01"),
                str(event.get("timestamp", "")),
                event.get("frame_number", 0),
                event.get("status", "UNAUTHORIZED"),
                event.get("confidence", 0.0),
                event.get("direction", None),
                event.get("evidence_path", None),
                event.get("plate_text", event.get("plate_number", None)),
                event.get("plate_confidence", None),
                event.get("plate_crop_path", None),
            ),
        )


def get_events(limit: int = 100) -> list[dict[str, Any]]:
    return get_default_db().fetch_events(limit)


def get_next_event_number() -> int:
    db = get_default_db()
    with db._connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM security_events").fetchone()[0]
    return int(count) + 1


def get_vehicle_by_plate(plate_number: str | None) -> dict[str, Any] | None:
    if not plate_number:
        return None

    db = get_default_db()
    with db._connect() as connection:
        vehicles = connection.execute(
            "SELECT plate_number, vehicle_type, owner, status FROM vehicles"
        ).fetchall()

    def clean_str(s: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(s).upper())

    target = clean_str(plate_number)
    if not target:
        return None

    substitutions = [
        ("1", "I"), ("I", "1"),
        ("0", "O"), ("O", "0"),
        ("8", "B"), ("B", "8"),
        ("5", "S"), ("S", "5"),
        ("2", "Z"), ("Z", "2"),
    ]

    candidates = {target}
    for orig, repl in substitutions:
        candidates.add(target.replace(orig, repl))

    for row in vehicles:
        db_plate, vehicle_type, owner, status = row["plate_number"], row["vehicle_type"], row["owner"], row["status"]
        db_norm = clean_str(db_plate)

        if db_norm in candidates or (len(target) >= 5 and (target in db_norm or db_norm in target)):
            return {
                "plate_number": db_plate,
                "vehicle_type": vehicle_type,
                "owner": owner,
                "status": status,
            }

        similarity = difflib.SequenceMatcher(None, target, db_norm).ratio()
        if similarity >= 0.75:
            return {
                "plate_number": db_plate,
                "vehicle_type": vehicle_type,
                "owner": owner,
                "status": status,
            }

    return None


def get_suspicious_activities() -> list[dict[str, Any]]:
    """Retrieves list of suspicious activities from database."""
    db = get_default_db()
    with db._connect() as connection:
        rows = connection.execute(
            "SELECT activity_id, track_id, activity_type, severity, description, timestamp "
            "FROM suspicious_activities ORDER BY id DESC"
        ).fetchall()

    return [
        {
            "activity_id": r["activity_id"],
            "track_id": r["track_id"],
            "activity_type": r["activity_type"],
            "severity": r["severity"],
            "description": r["description"],
            "timestamp": r["timestamp"],
        }
        for r in rows
    ]


def get_blockchain_ledger_records() -> list[dict[str, Any]]:
    """Retrieves full blockchain audit ledger."""
    db = get_default_db()
    with db._connect() as connection:
        rows = connection.execute(
            "SELECT block_index, event_id, previous_hash, block_hash, evidence_hash, timestamp, nonce, data_json "
            "FROM blockchain_ledger ORDER BY block_index DESC"
        ).fetchall()

    return [
        {
            "block_index": r["block_index"],
            "event_id": r["event_id"],
            "previous_hash": r["previous_hash"],
            "block_hash": r["block_hash"],
            "evidence_hash": r["evidence_hash"],
            "timestamp": r["timestamp"],
            "nonce": r["nonce"],
            "data_json": r["data_json"],
        }
        for r in rows
    ]


def get_system_analytics() -> dict[str, Any]:
    """Calculates live analytics metrics for CYPHER command dashboard."""
    db = get_default_db()
    with db._connect() as connection:
        total_events = connection.execute("SELECT COUNT(*) FROM security_events").fetchone()[0]
        registered_vehicles = connection.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
        unauthorized_intrusions = connection.execute(
            "SELECT COUNT(*) FROM security_events WHERE status = 'UNAUTHORIZED'"
        ).fetchone()[0]
        verified_entries = connection.execute(
            "SELECT COUNT(*) FROM security_events WHERE status = 'VERIFIED_VEHICLE' OR status = 'VERIFIED'"
        ).fetchone()[0]

    threat_level = (
        "CRITICAL" if unauthorized_intrusions > 2
        else "HIGH" if unauthorized_intrusions > 0
        else "NORMAL"
    )

    return {
        "total_events": int(total_events),
        "registered_vehicles": int(registered_vehicles),
        "unauthorized_intrusions": int(unauthorized_intrusions),
        "verified_entries": int(verified_entries),
        "threat_level": threat_level,
    }
