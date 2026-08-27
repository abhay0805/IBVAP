from ultralytics import YOLO
import cv2
import os

# -----------------------------
# Configuration
# -----------------------------

VIDEO_PATH = "videos/test.mp4"
MODEL_PATH = "yolo26n.pt"
OUTPUT_PATH = "output/tracked.mp4"

CONFIDENCE = 0.40


# -----------------------------
# Load YOLO model
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
# Process video
# -----------------------------

frame_number = 0

while True:

    ret, frame = cap.read()

    if not ret:
        break

    frame_number += 1

    # YOLO tracking
    results = model.track(
        frame,
        persist=True,
        conf=CONFIDENCE,
        verbose=False
    )

    # Draw tracking boxes and IDs
    annotated_frame = results[0].plot()

    # Save frame
    out.write(annotated_frame)

    # Display progress
    if frame_number % 50 == 0:
        print(f"Processed {frame_number} frames")


# -----------------------------
# Cleanup
# -----------------------------

cap.release()
out.release()

print()
print("Tracking completed!")
print(f"Output saved to: {OUTPUT_PATH}")