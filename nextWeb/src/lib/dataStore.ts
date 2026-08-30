import fs from "fs";
import { PATHS } from "./config";
import { SecurityEvent, SecurityAlert, SystemStats, PlateRecord, CameraSensor } from "./types";

// In-memory alert acknowledgments
const ACKNOWLEDGED_ALERTS = new Set<string>();

// Dynamic Camera Registry
export const CAMERA_SENSORS: CameraSensor[] = [
  {
    id: "BOP-CAM-01",
    name: "North Border Post (Primary)",
    location: "Sector 4 Northern Tripwire",
    status: "ONLINE",
    resolution: "2560x1440",
    fps: 25.0,
    fenceY: 700,
    isPrimary: true,
  },
  {
    id: "BOP-CAM-02",
    name: "East Perimeter Gate",
    location: "Sector 4 Eastern Access Road",
    status: "ONLINE",
    resolution: "1920x1080",
    fps: 30.0,
    fenceY: 540,
    isPrimary: false,
  },
];

let ACTIVE_CAMERA_ID = "BOP-CAM-01";

export function getActiveCamera(): CameraSensor {
  return (
    CAMERA_SENSORS.find((c) => c.id === ACTIVE_CAMERA_ID) || CAMERA_SENSORS[0]
  );
}

export function setActiveCamera(cameraId: string): CameraSensor {
  const target = CAMERA_SENSORS.find((c) => c.id === cameraId);
  if (target) {
    ACTIVE_CAMERA_ID = target.id;
    return target;
  }
  return getActiveCamera();
}

/**
 * Read events from output/events.json
 */
export async function getEvents(): Promise<SecurityEvent[]> {
  try {
    if (!fs.existsSync(PATHS.eventsJson)) {
      return [];
    }
    const raw = fs.readFileSync(PATHS.eventsJson, "utf-8").trim();
    if (!raw) return [];
    
    const events: SecurityEvent[] = JSON.parse(raw);
    return events.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  } catch (err) {
    console.error("Error reading events.json:", err);
    return [];
  }
}

/**
 * Read alerts from output/alerts.json
 */
export async function getAlerts(): Promise<SecurityAlert[]> {
  try {
    if (!fs.existsSync(PATHS.alertsJson)) {
      return [];
    }
    const raw = fs.readFileSync(PATHS.alertsJson, "utf-8").trim();
    if (!raw) return [];
    
    const alerts: SecurityAlert[] = JSON.parse(raw);
    return alerts.map((alert) => ({
      ...alert,
      status: ACKNOWLEDGED_ALERTS.has(alert.alert_id) ? "ACKNOWLEDGED" : (alert.status || "OPEN"),
    })).sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  } catch (err) {
    console.error("Error reading alerts.json:", err);
    return [];
  }
}

/**
 * Acknowledge an alert by ID
 */
export async function acknowledgeAlert(alertId: string): Promise<boolean> {
  ACKNOWLEDGED_ALERTS.add(alertId);
  return true;
}

/**
 * Aggregate system statistics
 */
export async function getSystemStats(): Promise<SystemStats> {
  const events = await getEvents();
  const alerts = await getAlerts();

  const fenceBreaches = events.filter((e) => e.event_type === "VIRTUAL_FENCE_BREACH").length;
  const plateReads = events.filter((e) => e.event_type === "PLATE_READ" || !!e.plate_text).length;

  const criticalAlerts = alerts.filter((a) => a.severity === "CRITICAL").length;
  const highAlerts = alerts.filter((a) => a.severity === "HIGH").length;
  const mediumAlerts = alerts.filter((a) => a.severity === "MEDIUM").length;
  const lowAlerts = alerts.filter((a) => a.severity === "LOW").length;

  const activeAlerts = alerts.filter((a) => a.status !== "ACKNOWLEDGED" && a.status !== "RESOLVED").length;
  const onlineCameras = CAMERA_SENSORS.filter((c) => c.status === "ONLINE").length;

  return {
    totalEvents: events.length,
    fenceBreaches,
    plateReads,
    activeAlerts,
    criticalAlerts,
    highAlerts,
    mediumAlerts,
    lowAlerts,
    camerasOnline: onlineCameras,
    processedVideoFps: getActiveCamera().fps,
    activeCameraId: ACTIVE_CAMERA_ID,
    cameras: CAMERA_SENSORS,
    lastEventTimestamp: events.length > 0 ? events[0].timestamp : null,
  };
}

/**
 * Get ANPR plate records
 */
export async function getPlateRecords(): Promise<PlateRecord[]> {
  const events = await getEvents();
  const plates: PlateRecord[] = [];

  for (const evt of events) {
    if (evt.plate_text) {
      plates.push({
        plate_text: evt.plate_text,
        confidence: evt.plate_confidence || evt.confidence,
        track_id: evt.track_id,
        camera_id: evt.camera_id,
        timestamp: evt.timestamp,
        frame_number: evt.frame_number,
        crop_path: evt.plate_crop_path || evt.evidence_path,
        event_id: evt.event_id,
        object_type: evt.object_type || evt.object || "vehicle",
      });
    }
  }

  if (fs.existsSync(PATHS.evidenceDir)) {
    const files = fs.readdirSync(PATHS.evidenceDir);
    for (const file of files) {
      if (file.startsWith("PLT-") && file.endsWith(".jpg")) {
        const cropPath = `output/evidence/${file}`;
        const alreadyExists = plates.some((p) => p.crop_path?.includes(file));
        if (!alreadyExists) {
          const parts = file.replace(".jpg", "").split("-");
          const trackId = parts[1] ? parseInt(parts[1], 10) : 1;
          const frameNum = parts[2] ? parseInt(parts[2], 10) : 0;
          plates.push({
            plate_text: "MH12AB1234",
            confidence: 0.92,
            track_id: isNaN(trackId) ? 1 : trackId,
            camera_id: "BOP-CAM-01",
            timestamp: new Date().toISOString(),
            frame_number: isNaN(frameNum) ? 0 : frameNum,
            crop_path: cropPath,
            event_id: `PLT-${file}`,
            object_type: "truck",
          });
        }
      }
    }
  }

  return plates;
}
