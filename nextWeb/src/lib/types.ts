export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type EventType =
  | "VIRTUAL_FENCE_BREACH"
  | "NIGHT_MOVEMENT"
  | "SUSPICIOUS_ACTIVITY"
  | "PLATE_READ";

export type CrossingDirection = "INBOUND" | "OUTBOUND";

export interface CameraSensor {
  id: string;
  name: string;
  location: string;
  status: "ONLINE" | "STANDBY" | "OFFLINE";
  resolution: string;
  fps: number;
  fenceY: number;
  isPrimary?: boolean;
}

export interface SecurityEvent {
  id?: number;
  event_id: string;
  event_type: EventType;
  object_type: string;
  object?: string; // backwards compatibility
  track_id: number;
  camera_id: string;
  timestamp: string;
  frame_number: number;
  status: string;
  confidence: number;
  direction?: CrossingDirection | null;
  evidence_path?: string | null;
  plate_text?: string | null;
  plate_confidence?: number | null;
  plate_crop_path?: string | null;
}

export interface SecurityAlert {
  id?: number;
  alert_id: string;
  event_id?: string | null;
  event_type: EventType;
  object_type: string;
  track_id: number;
  camera_id: string;
  severity: Severity;
  status: string;
  message: string;
  timestamp: string;
  frame_number: number;
  evidence_path?: string | null;
  metadata?: Record<string, any> | string;
}

export interface PlateRecord {
  plate_text: string;
  confidence: number;
  track_id: number;
  camera_id: string;
  timestamp: string;
  frame_number: number;
  crop_path?: string | null;
  event_id?: string | null;
  object_type: string;
}

export interface SystemStats {
  totalEvents: number;
  fenceBreaches: number;
  plateReads: number;
  activeAlerts: number;
  criticalAlerts: number;
  highAlerts: number;
  mediumAlerts: number;
  lowAlerts: number;
  camerasOnline: number;
  processedVideoFps: number;
  activeCameraId: string;
  cameras: CameraSensor[];
  lastEventTimestamp?: string | null;
}

export interface DetectionRunParams {
  videoPath?: string;
  confidence?: number;
  fenceY?: number;
  cameraId?: string;
  minObservations?: number;
  anprEnabled?: boolean;
  limitFrames?: number;
}
