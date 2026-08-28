from ultralytics import YOLO
import cv2
import os
import json
from datetime import datetime
from database import initialize_database, save_event


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
if os.path.exists("output/ibvap.db"):
    os.remove("output/ibvap.db")

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



# Store security events
events = []

event_counter = 1


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
            # Draw bounding box
            # -------------------------

            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            label = f"{class_name} | Track ID: {track_id}"

            cv2.putText(
                frame,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )


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

                    event = {
                        "event_id": event_id,
                        "event_type": "VIRTUAL_FENCE_BREACH",
                        "object": class_name,
                        "track_id": int(track_id),
                        "camera_id": "BOP-CAM-01",
                        "timestamp": timestamp,
                        "frame_number": frame_number,
                        "status": "UNAUTHORIZED",
                        "evidence_path": f"output/evidence/{event_id}.jpg"
                    }
                    events.append(event)
                    save_event(event)

                    event_counter += 1

                    triggered_ids.add(track_id)

                    # -------------------------
                    # Capture evidence
                    # -------------------------

                    evidence_path = os.path.join(
                        EVIDENCE_DIR,
                        f"{event_id}.jpg"
                    )

                    cv2.imwrite(
                        evidence_path,
                        frame
                    )

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