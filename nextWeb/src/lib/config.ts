import path from "path";

// Root workspace directory is parent of nextWeb
export const WORKSPACE_ROOT = path.resolve(process.cwd(), "..");

export const PATHS = {
  root: WORKSPACE_ROOT,
  outputDir: path.join(WORKSPACE_ROOT, "output"),
  dbPath: path.join(WORKSPACE_ROOT, "output", "ibvap.db"),
  eventsJson: path.join(WORKSPACE_ROOT, "output", "events.json"),
  alertsJson: path.join(WORKSPACE_ROOT, "output", "alerts.json"),
  evidenceDir: path.join(WORKSPACE_ROOT, "output", "evidence"),
  processedVideo: path.join(WORKSPACE_ROOT, "output", "fence_detection.mp4"),
  videosDir: path.join(WORKSPACE_ROOT, "videos"),
  pythonVenv: path.join(WORKSPACE_ROOT, "venv", "Scripts", "python.exe"),
  pythonScript: path.join(WORKSPACE_ROOT, "src", "detect.py"),
};

export const DEFAULT_CAMERA = "BOP-CAM-01";
export const DEFAULT_FENCE_Y = 700;
