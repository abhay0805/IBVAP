import { DetectionRunParams } from "./types";

export interface DetectionState {
  isRunning: boolean;
  pid?: number;
  startTime?: string;
  exitCode?: number | null;
  logs: string[];
  lastParams?: DetectionRunParams;
}

// Global in-memory state for the active detection process
export const detectionState: DetectionState = {
  isRunning: false,
  logs: [],
};
