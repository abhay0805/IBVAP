import sqlite3
import os
import re



DB_PATH = "output/ibvap.db"


def initialize_database():
    os.makedirs("output", exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

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

    connection.commit()
    connection.close()


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

