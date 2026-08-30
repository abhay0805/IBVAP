"use client";

import React, { useState, useEffect } from "react";
import { TerminalConsole } from "@/components/TerminalConsole";
import { VideoPlayer } from "@/components/VideoPlayer";
import { Sliders, Play, RefreshCw, Settings2 } from "lucide-react";

export default function LabPage() {
  const [selectedVideo, setSelectedVideo] = useState("videos/test.mp4");
  const [fenceY, setFenceY] = useState(700);
  const [confidence, setConfidence] = useState(0.4);
  const [anprEnabled, setAnprEnabled] = useState(true);
  const [limitFrames, setLimitFrames] = useState(0);

  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<string[]>([
    "IBVAP Virtual Fence & ANPR Interactive Lab Initialized.",
    "Adjust perimeter parameters above and click 'Run AI Detection Pipeline' to start.",
  ]);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isRunning) {
      interval = setInterval(async () => {
        try {
          const res = await fetch("/api/detect/status");
          if (res.ok) {
            const data = await res.json();
            if (data.logs && data.logs.length > 0) {
              setLogs(data.logs);
            }
            if (!data.isRunning && data.exitCode !== null) {
              setIsRunning(false);
            }
          }
        } catch (err) {
          console.error("Error polling status:", err);
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isRunning]);

  const handleStartPipeline = async () => {
    try {
      setIsRunning(true);
      setLogs([
        `[${new Date().toLocaleTimeString()}] Triggering Python AI pipeline with:`,
        `  Video: ${selectedVideo}`,
        `  Fence Y: ${fenceY}px`,
        `  Confidence: ${confidence}`,
        `  ANPR OCR: ${anprEnabled ? "Enabled" : "Disabled"}`,
        `  Limit: ${limitFrames === 0 ? "All Frames" : limitFrames}`,
      ]);

      const res = await fetch("/api/detect/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          videoPath: selectedVideo,
          fenceY,
          confidence,
          anprEnabled,
          limitFrames,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        setLogs((prev) => [...prev, `[ERROR] ${err.error || "Failed to start"}`]);
        setIsRunning(false);
      }
    } catch (err) {
      setLogs((prev) => [...prev, `[ERROR] Network error: ${String(err)}`]);
      setIsRunning(false);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-hairline pb-6">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider font-semibold text-primary mb-1">
            <Sliders className="w-3.5 h-3.5" />
            <span>Interactive Computer Vision Lab</span>
          </div>
          <h1 className="font-serif text-3xl md:text-5xl text-ink font-normal tracking-tight">
            Virtual Fence & Detection Studio
          </h1>
          <p className="mt-2 text-sm text-body leading-relaxed max-w-2xl">
            Configure tripwire geometry, tune YOLO object confidence, enable ANPR OCR workers, and execute the detection pipeline in real time.
          </p>
        </div>

        <button
          onClick={handleStartPipeline}
          disabled={isRunning}
          className={`px-6 py-3 rounded-md text-sm font-medium flex items-center gap-2 transition-all shadow-md active:scale-95 ${
            isRunning
              ? "bg-primary/50 text-on-primary cursor-not-allowed"
              : "bg-primary hover:bg-primary-active text-on-primary"
          }`}
        >
          {isRunning ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Inference in Progress...</span>
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-current" />
              <span>Run AI Detection Pipeline</span>
            </>
          )}
        </button>
      </div>

      {/* Main Studio Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Parameter Tuning */}
        <div className="lg:col-span-5 space-y-6">
          <div className="p-6 rounded-xl bg-surface-card border border-hairline space-y-6">
            <div className="flex items-center justify-between border-b border-hairline pb-3">
              <div className="flex items-center gap-2">
                <Settings2 className="w-4 h-4 text-primary" />
                <h3 className="font-serif text-xl font-normal text-ink">
                  Pipeline Configuration
                </h3>
              </div>
              <span className="text-xs font-mono text-muted">YOLOv8/26 + ANPR</span>
            </div>

            {/* Video Source */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-ink flex items-center justify-between">
                <span>Video Footage Source</span>
                <span className="text-[11px] font-mono text-muted-soft">Surveillance File</span>
              </label>
              <select
                value={selectedVideo}
                onChange={(e) => setSelectedVideo(e.target.value)}
                className="w-full p-2.5 rounded-md bg-canvas border border-hairline text-xs text-ink font-medium focus:outline-none focus:border-primary"
              >
                <option value="videos/test.mp4">videos/test.mp4 (Surveillance 2560×1440)</option>
                <option value="videos/plate_probe.mp4">videos/plate_probe.mp4 (ANPR Plate Probe)</option>
              </select>
            </div>

            {/* Tripwire Y Slider */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-ink">Virtual Tripwire Y-Line:</span>
                <span className="font-mono font-bold bg-canvas px-2 py-0.5 rounded border border-hairline text-primary">
                  {fenceY} px
                </span>
              </div>
              <input
                type="range"
                min="200"
                max="1200"
                step="25"
                value={fenceY}
                onChange={(e) => setFenceY(parseInt(e.target.value, 10))}
                className="w-full accent-primary cursor-pointer"
              />
            </div>

            {/* Confidence Threshold */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-ink">YOLO Confidence Threshold:</span>
                <span className="font-mono font-bold bg-canvas px-2 py-0.5 rounded border border-hairline text-accent-teal">
                  {Math.round(confidence * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0.15"
                max="0.85"
                step="0.05"
                value={confidence}
                onChange={(e) => setConfidence(parseFloat(e.target.value))}
                className="w-full accent-primary cursor-pointer"
              />
            </div>

            {/* Frame Limit */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-ink">Frame Limit:</span>
                <span className="font-mono font-bold bg-canvas px-2 py-0.5 rounded border border-hairline text-body">
                  {limitFrames === 0 ? "Full Video (455 frames)" : `${limitFrames} frames`}
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="450"
                step="50"
                value={limitFrames}
                onChange={(e) => setLimitFrames(parseInt(e.target.value, 10))}
                className="w-full accent-primary cursor-pointer"
              />
            </div>

            {/* ANPR Toggle */}
            <div className="pt-2 border-t border-hairline flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-ink block">
                  Automatic Number Plate Recognition (ANPR)
                </span>
                <span className="text-[11px] text-muted-soft">
                  Run background EasyOCR worker on vehicle crops
                </span>
              </div>
              <input
                type="checkbox"
                checked={anprEnabled}
                onChange={(e) => setAnprEnabled(e.target.checked)}
                className="w-4 h-4 accent-primary cursor-pointer"
              />
            </div>
          </div>
        </div>

        {/* Right Output & Console */}
        <div className="lg:col-span-7 space-y-6">
          <div className="space-y-2">
            <h3 className="font-serif text-xl font-normal text-ink">
              Annotated Video Output
            </h3>
            <VideoPlayer
              processedVideoUrl="/api/media/output/fence_detection.mp4"
              sourceVideoUrl={`/api/media/${selectedVideo}`}
              cameraId="BOP-CAM-01"
              fenceY={fenceY}
            />
          </div>

          <div className="space-y-2">
            <TerminalConsole
              logs={logs}
              isRunning={isRunning}
              onClear={() => setLogs([])}
              title="Execution Log & Subprocess Stream"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
