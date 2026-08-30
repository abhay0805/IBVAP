import cv2
import numpy as np
import time
import math
import sqlite3
import os

DB_PATH = "output/ibvap.db"

def is_low_light_frame(frame, threshold=85.0):
    """Detects if frame lighting is low (night time / poor visibility)."""
    if frame is None:
        return False
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    mean_brightness = float(np.mean(gray))
    return mean_brightness < threshold

def apply_night_vision_enhancement(frame, mode="thermal_enhanced"):
    """
    Applies adaptive contrast enhancement and low-light amplification for night surveillance.
    Supports 'enhanced_contrast' and 'thermal_enhanced' color visualization modes.
    """
    if frame is None:
        return frame

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame.copy()

    # Apply CLAHE contrast amplification
    clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8))
    enhanced_gray = clahe.apply(gray)

    if mode == "thermal_enhanced":
        # Pseudo-thermal color mapping for high-contrast human/vehicle hotspot visibility
        colored = cv2.applyColorMap(enhanced_gray, cv2.COLORMAP_JET)
        # Blend original frame with thermal overlay
        blended = cv2.addWeighted(frame, 0.35, colored, 0.65, 0)
        return blended
    else:
        # High-contrast night vision grayscale / green tint
        green_tint = cv2.merge([np.zeros_like(enhanced_gray), enhanced_gray, np.zeros_like(enhanced_gray)])
        return green_tint


class SuspiciousActivityTracker:
    def __init__(self, loitering_threshold_sec=4.0, rapid_approach_speed=45.0):
        self.loitering_threshold_sec = loitering_threshold_sec
        self.rapid_approach_speed = rapid_approach_speed
        
        # Track ID state maps
        self.track_history = {}  # track_id -> [(timestamp, (center_x, center_y))]
        self.proximity_counts = {} # track_id -> count
        self.flagged_activities = {} # track_id -> set of flagged event types

    def analyze_object(self, track_id, object_type, center_x, center_y, fence_y, current_time=None):
        """
        Analyzes object trajectory, speed, dwell time, and fence proximity.
        Returns list of newly triggered suspicious activity records.
        """
        if current_time is None:
            current_time = time.time()

        if track_id not in self.track_history:
            self.track_history[track_id] = []
            self.flagged_activities[track_id] = set()
            self.proximity_counts[track_id] = 0

        history = self.track_history[track_id]
        history.append((current_time, (center_x, center_y)))

        # Keep history window (last 10 seconds)
        cutoff = current_time - 10.0
        self.track_history[track_id] = [h for h in history if h[0] >= cutoff]
        history = self.track_history[track_id]

        new_alerts = []

        if len(history) < 3:
            return new_alerts

        # 1. Calculate dwell time & movement distance for Loitering Detection
        first_time, first_pos = history[0]
        last_time, last_pos = history[-1]
        dwell_duration = last_time - first_time

        total_dist = math.hypot(last_pos[0] - first_pos[0], last_pos[1] - first_pos[1])
        speed = total_dist / dwell_duration if dwell_duration > 0 else 0

        # Loitering Rule: Object remains in fence vicinity (> threshold_sec) with low movement speed
        distance_to_fence = abs(center_y - fence_y)
        if distance_to_fence < 220:  # Buffer zone near virtual fence
            if dwell_duration >= self.loitering_threshold_sec and speed < 25.0:
                if "LOITERING" not in self.flagged_activities[track_id]:
                    self.flagged_activities[track_id].add("LOITERING")
                    new_alerts.append({
                        "activity_type": "LOITERING_BEHAVIOR",
                        "severity": "HIGH",
                        "description": f"Object ({object_type} ID #{track_id}) loitering near fence zone for {dwell_duration:.1f}s",
                        "dwell_duration": round(dwell_duration, 1),
                        "track_id": track_id
                    })

            # 2. Rapid Approach Velocity Anomaly
            # Compare position from 1 second ago vs current position
            recent_points = [h for h in history if current_time - h[0] <= 1.2]
            if len(recent_points) >= 2:
                dt = recent_points[-1][0] - recent_points[0][0]
                dy = recent_points[-1][1][1] - recent_points[0][1][1]
                # Positive dy means moving downward towards FENCE_Y
                y_speed = dy / dt if dt > 0 else 0
                if y_speed > self.rapid_approach_speed:
                    if "RAPID_APPROACH" not in self.flagged_activities[track_id]:
                        self.flagged_activities[track_id].add("RAPID_APPROACH")
                        new_alerts.append({
                            "activity_type": "RAPID_FENCE_APPROACH",
                            "severity": "CRITICAL",
                            "description": f"High-velocity approach towards virtual fence by {object_type} ID #{track_id} ({y_speed:.1f} px/s)",
                            "speed": round(y_speed, 1),
                            "track_id": track_id
                        })

        return new_alerts


def log_suspicious_activity(activity):
    """Persists suspicious activity alert into SQLite database."""
    os.makedirs("output", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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

    act_id = f"SA-{int(time.time()*1000)%1000000:06d}"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT OR IGNORE INTO suspicious_activities (activity_id, track_id, activity_type, severity, description, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        act_id,
        activity.get("track_id", 0),
        activity.get("activity_type", "SUSPICIOUS_MOVEMENT"),
        activity.get("severity", "MEDIUM"),
        activity.get("description", ""),
        timestamp
    ))

    conn.commit()
    conn.close()
    return act_id

if __name__ == "__main__":
    print("Testing Analytics & Night Vision Module...")
    tracker = SuspiciousActivityTracker(loitering_threshold_sec=2.0)
    alerts = tracker.analyze_object(1, "person", 500, 680, 700, time.time())
    print("Night vision & loitering tracker module ready!")
