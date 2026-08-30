import os
import re
import cv2
import numpy as np
import easyocr
from database import get_vehicle_by_plate, initialize_database

# Initialize EasyOCR reader (English)
# Lazy loading to optimize performance
_reader = None

def get_ocr_reader():
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    return _reader


def normalize_plate_number(raw_text):
    """
    Clean and normalize raw OCR text output into a standardized format.
    Removes whitespace, special characters, and converts to uppercase.
    """
    if not raw_text:
        return ""
    
    # Keep only uppercase alphanumeric characters
    cleaned = re.sub(r'[^A-ZA-Z0-9]', '', raw_text).upper()
    return cleaned


def preprocess_plate_image(plate_img):
    """
    Preprocess license plate crop to improve OCR accuracy.
    Includes resizing, grayscale conversion, contrast enhancement, and noise reduction.
    """
    if plate_img is None or plate_img.size == 0:
        return None

    # Upscale image for better character resolution if small
    h, w = plate_img.shape[:2]
    if h < 60 or w < 180:
        scale = max(2.0, 180.0 / max(w, 1))
        plate_img = cv2.resize(plate_img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # Convert to grayscale
    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY) if len(plate_img.shape) == 3 else plate_img.copy()

    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast_enhanced = clahe.apply(gray)

    # Bilateral filter to smooth while preserving edges
    filtered = cv2.bilateralFilter(contrast_enhanced, 11, 17, 17)

    # Otsu thresholding
    _, thresh = cv2.threshold(filtered, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return thresh


def detect_license_plate_roi(vehicle_img):
    """
    Detect and crop license plate candidate region from a vehicle image using contour heuristics.
    Returns the cropped license plate image (or vehicle ROI fallback) and box coordinates (x, y, w, h).
    """
    if vehicle_img is None or vehicle_img.size == 0:
        return None, None

    h, w = vehicle_img.shape[:2]

    # Focus detection primarily on lower 75% of vehicle where plates are typically mounted
    roi_top = int(h * 0.25)
    search_roi = vehicle_img[roi_top:h, 0:w]

    gray = cv2.cvtColor(search_roi, cv2.COLOR_BGR2GRAY)
    
    # Morphological gradient to highlight edges (plate boundaries and text)
    rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
    top_hat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, rect_kernel)

    # Sobel X to detect vertical edges
    sobel_x = cv2.Sobel(top_hat, cv2.CV_8U, 1, 0, ksize=3)
    sobel_x = cv2.convertScaleAbs(sobel_x)

    # Blur and threshold
    blurred = cv2.GaussianBlur(sobel_x, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Morphological close to combine character edges into a solid block
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, close_kernel)

    # Find contours
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    plate_candidates = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        aspect_ratio = float(cw) / float(ch) if ch > 0 else 0
        area = cw * ch

        # License plate aspect ratio in standard formats is between 2.0 and 6.0
        if 2.0 <= aspect_ratio <= 6.5 and area > 300 and cw > 40 and ch > 12:
            # Map coordinates back to original vehicle image
            actual_y = y + roi_top
            plate_candidates.append((actual_y, x, cw, ch, area))

    if plate_candidates:
        # Pick largest candidate by area
        plate_candidates.sort(key=lambda item: item[4], reverse=True)
        py, px, pw, ph, _ = plate_candidates[0]

        # Add small padding around cropped plate
        pad_x = int(pw * 0.05)
        pad_y = int(ph * 0.1)
        x1 = max(0, px - pad_x)
        y1 = max(0, py - pad_y)
        x2 = min(w, px + pw + pad_x)
        y2 = min(h, py + ph + pad_y)

        cropped_plate = vehicle_img[y1:y2, x1:x2]
        return cropped_plate, (x1, y1, x2 - x1, y2 - y1)

    # Fallback to lower half crop if contour detection yields no plate
    lower_crop = vehicle_img[int(h * 0.4):h, 0:w]
    return lower_crop, (0, int(h * 0.4), w, int(h * 0.6))


def recognize_plate(image):
    """
    Full ANPR pipeline for an image / vehicle crop:
    1. License plate ROI detection & crop
    2. Image preprocessing
    3. OCR execution
    4. Text normalization
    5. Registry verification lookup
    """
    reader = get_ocr_reader()

    cropped_plate, bbox = detect_license_plate_roi(image)
    if cropped_plate is None or cropped_plate.size == 0:
        cropped_plate = image

    # Preprocess cropped plate
    preprocessed = preprocess_plate_image(cropped_plate)

    # Run EasyOCR on both raw crop and preprocessed crop for best recall
    results_raw = reader.readtext(cropped_plate)
    results_prep = reader.readtext(preprocessed) if preprocessed is not None else []

    all_candidates = []

    for item in results_raw + results_prep:
        text = item[1]
        confidence = float(item[2])
        norm_text = normalize_plate_number(text)
        # Filter candidate string length typical of plate numbers (e.g. 4 to 12 chars)
        if len(norm_text) >= 4 and confidence > 0.2:
            all_candidates.append((norm_text, confidence))

    if not all_candidates:
        return {
            "raw_text": "",
            "normalized_plate": "",
            "status": "UNKNOWN",
            "vehicle_info": None,
            "confidence": 0.0
        }

    # Sort by confidence score
    all_candidates.sort(key=lambda x: x[1], reverse=True)
    best_plate, best_conf = all_candidates[0]

    # Query vehicle database
    vehicle_info = get_vehicle_by_plate(best_plate)

    if vehicle_info and vehicle_info.get("status") == "VERIFIED":
        status = "VERIFIED"
    elif vehicle_info:
        status = vehicle_info.get("status", "UNKNOWN")
    else:
        status = "UNKNOWN"

    return {
        "raw_text": best_plate,
        "normalized_plate": best_plate,
        "status": status,
        "vehicle_info": vehicle_info,
        "confidence": best_conf
    }


# Standalone Independent Test Suite
if __name__ == "__main__":
    print("==========================================")
    print("IBVAP - ANPR Independent Test Suite")
    print("==========================================")

    initialize_database()

    def create_synthetic_plate_image(plate_text):
        """Generates a synthetic license plate image for testing OCR & lookup."""
        img = np.ones((100, 320, 3), dtype=np.uint8) * 255
        # Black border
        cv2.rectangle(img, (5, 5), (315, 95), (0, 0, 0), 4)
        # Text
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(plate_text, font, 1.2, 3)[0]
        text_x = (320 - text_size[0]) // 2
        text_y = (100 + text_size[1]) // 2
        cv2.putText(img, plate_text, (text_x, text_y), font, 1.2, (0, 0, 0), 3)
        return img

    test_plates = [
        "AI 7060 EC",  # Registered in DB
        "AA 3325 MM",  # Registered in DB
        "XX 1234 ZZ"   # Unregistered / Unknown
    ]

    for plate in test_plates:
        print(f"\n[TESTING PLATE]: '{plate}'")
        synthetic_img = create_synthetic_plate_image(plate)

        result = recognize_plate(synthetic_img)

        print(f"  -> Extracted/Normalized: '{result['normalized_plate']}'")
        print(f"  -> Confidence:           {result['confidence']:.2f}")
        print(f"  -> Registry Status:      {result['status']}")
        if result['vehicle_info']:
            print(f"  -> Owner:                {result['vehicle_info']['owner']}")
            print(f"  -> Vehicle Type:         {result['vehicle_info']['vehicle_type']}")
        else:
            print("  -> Owner:                Not Found in Registry")

    print("\n==========================================")
    print("ANPR Independent Test Completed Successfully!")
    print("==========================================")
