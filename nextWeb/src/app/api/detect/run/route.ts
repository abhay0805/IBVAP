import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { PATHS } from "@/lib/config";
import { DetectionRunParams } from "@/lib/types";
import { detectionState } from "@/lib/detectState";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    if (detectionState.isRunning) {
      return NextResponse.json(
        { error: "A detection pipeline run is already in progress", state: detectionState },
        { status: 409 }
      );
    }

    const body: DetectionRunParams = await request.json();
    const cameraId = body.cameraId || "BOP-CAM-01";
    let videoSource = body.videoPath;
    if (!videoSource) {
      if (cameraId === "BOP-CAM-02") {
        videoSource = "License Plate Detection Test.mp4";
      } else {
        videoSource = "videos/test.mp4";
      }
    }
    const fenceY = body.fenceY ?? (cameraId === "BOP-CAM-02" ? 400 : 700);
    const confidence = body.confidence ?? 0.4;
    const anprEnabled = body.anprEnabled !== false;
    const limitFrames = body.limitFrames ?? 0;

    const args: string[] = [
      PATHS.pythonScript,
      "--video",
      videoSource,
      "--camera-id",
      cameraId,
      "--fence-y",
      String(fenceY),
      "--confidence",
      String(confidence),
      "--save",
    ];

    if (!anprEnabled) {
      args.push("--no-anpr-enabled");
    }

    if (limitFrames > 0) {
      args.push("--limit-frames", String(limitFrames));
    }

    detectionState.isRunning = true;
    detectionState.startTime = new Date().toISOString();
    detectionState.exitCode = null;
    detectionState.lastParams = body;
    detectionState.logs = [
      `[${new Date().toLocaleTimeString()}] Starting IBVAP Pipeline...`,
      `Command: python ${args.map((a) => (a.includes(" ") ? `"${a}"` : a)).join(" ")}`,
    ];

    const child = spawn(PATHS.pythonVenv, args, {
      cwd: PATHS.root,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    detectionState.pid = child.pid;

    child.stdout.on("data", (data: Buffer) => {
      const lines = data.toString().split("\n");
      for (const line of lines) {
        if (line.trim()) {
          detectionState.logs.push(line.trimEnd());
          if (detectionState.logs.length > 500) detectionState.logs.shift();
        }
      }
    });

    child.stderr.on("data", (data: Buffer) => {
      const lines = data.toString().split("\n");
      for (const line of lines) {
        if (line.trim()) {
          detectionState.logs.push(`[ERR] ${line.trimEnd()}`);
          if (detectionState.logs.length > 500) detectionState.logs.shift();
        }
      }
    });

    child.on("close", (code) => {
      detectionState.isRunning = false;
      detectionState.exitCode = code;
      detectionState.logs.push(
        `[${new Date().toLocaleTimeString()}] Pipeline completed with exit code: ${code}`
      );
    });

    return NextResponse.json({
      success: true,
      message: "Detection pipeline started successfully",
      pid: child.pid,
      params: body,
    });
  } catch (error) {
    detectionState.isRunning = false;
    return NextResponse.json(
      { error: "Failed to trigger detection pipeline", details: String(error) },
      { status: 500 }
    );
  }
}
