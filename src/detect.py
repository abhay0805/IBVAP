from ultralytics import YOLO
import cv2
import os
import json
from datetime import datetime
from database import initialize_database, save_event, get_next_event_number
from anpr import recognize_plate
from blockchain import add_event_to_blockchain, initialize_blockchain
from analytics import is_low_light_frame, apply_night_vision_enhancement, SuspiciousActivityTracker, log_suspicious_activity

# Initialize Blockchain & Analytics
initialize_blockchain()
suspicious_tracker = SuspiciousActivityTracker()
NIGHT_MODE_AUTO = True




# -----------------------------
# Configuration
# -----------------------------

VIDEO_PATH = "videos/test.mp4"
MODEL_PATH = "yolo26n.pt"
OUTPUT_PATH = "output/fence_detection.mp4"
EVENT_LOG_PATH = "output/events.json"
EVIDENCE_DIR = "output/evidence"

CONFIDENCE = 0.40

# Horizontal virtual fence
FENCE_Y = 700


# -----------------------------
# Load model
# -----------------------------

print("Loading YOLO model...")

model = YOLO(MODEL_PATH)

print("Model loaded successfully!")


# -----------------------------
# Open video
# -----------------------------

cap = cv2.VideoCapture(VIDEO_PATH)

if not cap.isOpened():
    print("ERROR: Could not open video.")
    exit()

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)

print(f"Video: {width}x{height}")
print(f"FPS: {fps}")


# -----------------------------
# Create output directory
# -----------------------------

os.makedirs("output", exist_ok=True)
os.makedirs(EVIDENCE_DIR, exist_ok=True)

    
initialize_database()


# -----------------------------
# Video writer
# -----------------------------

fourcc = cv2.VideoWriter_fourcc(*"mp4v")

out = cv2.VideoWriter(
    OUTPUT_PATH,
    fourcc,
    fps,
    (width, height)
)


# -----------------------------
# Tracking state
# -----------------------------

previous_positions = {}
triggered_ids = set()
active_alerts = {}
anpr_cache = {}
VEHICLE_CLASSES = {'car', 'truck', 'bus', 'motorbike'}

# Store security events
events = []

event_counter = get_next_event_number()



# -----------------------------
# Process video
# -----------------------------

frame_number = 0

while True:

    ret, frame = cap.read()

    if not ret:
        break

    frame_number += 1


    # -------------------------
    # YOLO Tracking
    # -------------------------

    results = model.track(
        frame,
        persist=True,
        conf=CONFIDENCE,
        verbose=False
    )

    result = results[0]


    # -------------------------
    # Draw virtual fence
    # -------------------------

    cv2.line(
        frame,
        (0, FENCE_Y),
        (width, FENCE_Y),
        (0, 0, 255),
        4
    )

    cv2.putText(
        frame,
        "VIRTUAL FENCE",
        (50, FENCE_Y - 15),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 255),
        3
    )


    # -------------------------
    # Process detections
    # -------------------------

    if result.boxes.id is not None:

        boxes = result.boxes.xyxy.cpu().numpy()
        track_ids = result.boxes.id.cpu().numpy().astype(int)
        classes = result.boxes.cls.cpu().numpy().astype(int)


        for box, track_id, class_id in zip(
            boxes,
            track_ids,
            classes
        ):

            x1, y1, x2, y2 = map(int, box)

            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)

            class_name = model.names[class_id]

            # -------------------------
            # ANPR for Vehicle Objects
            # -------------------------
            plate_extra_label = ""
            box_color = (0, 255, 0)

            if class_name in VEHICLE_CLASSES:
                # Perform ANPR on vehicle crop if missing from cache or periodically
                if track_id not in anpr_cache or frame_number % 20 == 0:
                    vehicle_crop = frame[max(0, y1):min(height, y2), max(0, x1):min(width, x2)]
                    if vehicle_crop is not None and vehicle_crop.size > 0:
                        anpr_res = recognize_plate(vehicle_crop)
                        if anpr_res.get("normalized_plate") or track_id not in anpr_cache:
                            anpr_cache[track_id] = anpr_res

                if track_id in anpr_cache:
                    info = anpr_cache[track_id]
                    plate_num = info.get("normalized_plate", "")
                    status = info.get("status", "UNKNOWN")
                    if plate_num:
                        plate_extra_label = f" | Plate: {plate_num} [{status}]"
                    else:
                        plate_extra_label = f" | [{status}]"
                    
                    if status == "UNKNOWN":
                        box_color = (0, 165, 255)  # Orange for UNKNOWN vehicles
                    elif status == "VERIFIED":
                        box_color = (0, 255, 0)    # Green for VERIFIED vehicles

            # -------------------------
            # Draw bounding box & label
            # -------------------------

            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                box_color,
                2
            )

            label = f"{class_name} | Track ID: {track_id}{plate_extra_label}"

            cv2.putText(
                frame,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                box_color,
                2
            )


            # Analyze trajectory for loitering & rapid approach anomalies
            sa_alerts = suspicious_tracker.analyze_object(track_id, class_name, center_x, center_y, FENCE_Y)
            for sa in sa_alerts:
                log_suspicious_activity(sa)

            # Center point

            cv2.circle(
                frame,
                (center_x, center_y),
                6,
                (255, 0, 0),
                -1
                )
            
            # Show intrusion warning for this object
            if track_id in active_alerts:

                cv2.putText(
                    frame,
                    "INTRUSION",
                    (x1, y2 + 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 0, 255),
                    2
                )

                active_alerts[track_id] -= 1

                if active_alerts[track_id] <= 0:
                    del active_alerts[track_id]
                    
            previous_y = previous_positions.get(track_id)
            if previous_y is not None:

                crossed_fence = (
                    previous_y < FENCE_Y
                    and center_y >= FENCE_Y
                )


                if crossed_fence and track_id not in triggered_ids:

                    # -------------------------
                    # Create security event
                    # -------------------------

                    event_id = f"EVT-{event_counter:04d}"

                    timestamp = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                    # Determine security event status based on vehicle registry
                    vehicle_status = anpr_cache.get(track_id, {}).get("status", "UNAUTHORIZED")
                    event_status = "VERIFIED_VEHICLE" if vehicle_status == "VERIFIED" else "UNAUTHORIZED"

                    event = {
                        "event_id": event_id,
                        "event_type": "VIRTUAL_FENCE_BREACH",
                        "object": class_name,
                        "track_id": int(track_id),
                        "camera_id": "BOP-CAM-01",
                        "timestamp": timestamp,
                        "frame_number": frame_number,
                        "status": event_status,
                        "evidence_path": f"output/evidence/{event_id}.jpg"
                    }

                    events.append(event)
                    save_event(event)

                    event_counter += 1

                    triggered_ids.add(track_id)

                    # -------------------------
                    # Capture evidence & Blockchain Hashing
                    # -------------------------

                    evidence_path = os.path.join(
                        EVIDENCE_DIR,
                        f"{event_id}.jpg"
                    )

                    cv2.imwrite(
                        evidence_path,
                        frame
                    )

                    # Mine Cryptographic Block in Audit Ledger
                    block_hash, ev_hash = add_event_to_blockchain(event_id, event, evidence_path)
                    print(f"Evidence saved: {evidence_path} | Block Hash: {block_hash[:16]}...")


                    print(f"Evidence saved: {evidence_path}")

                    # Keep this specific object's alert visible for 3 seconds
                    active_alerts[track_id] = int(fps * 3)


                    # -------------------------
                    # CLI alert
                    # -------------------------

                    print()
                    print("🚨 SECURITY EVENT")
                    print("-----------------------------")
                    print(f"Event ID : {event_id}")
                    print(f"Object   : {class_name}")
                    print(f"Track ID : {track_id}")
                    print(f"Camera   : BOP-CAM-01")
                    print(f"Time     : {timestamp}")
                    print("-----------------------------")


            # Save position

            previous_positions[track_id] = center_y


    


    # -----------------------------
    # Save frame
    # -----------------------------

    out.write(frame)


    if frame_number % 50 == 0:

        print(
            f"Processed {frame_number} frames"
        )


# -----------------------------
# Cleanup
# -----------------------------

cap.release()
out.release()


# -----------------------------
# Save events
# -----------------------------

with open(EVENT_LOG_PATH, "w") as file:

    json.dump(
        events,
        file,
        indent=4
    )


print()
print("================================")
print("Processing completed!")
print("================================")
print(f"Video : {OUTPUT_PATH}")
print(f"Events: {EVENT_LOG_PATH}")
print(f"Total security events: {len(events)}")