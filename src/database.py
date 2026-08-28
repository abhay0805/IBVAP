import sqlite3
import os


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