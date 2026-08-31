"use client";

import React, { useRef, useState } from "react";
import { Play, Pause, RefreshCw, Shield, Eye, Layers, Camera } from "lucide-react";
import { CameraSensor } from "@/lib/types";

interface VideoPlayerProps {
  processedVideoUrl?: string;
  sourceVideoUrl?: string;
  cameraId?: string;
  fps?: number;
  fenceY?: number;
  availableCameras?: CameraSensor[];
  onSelectCamera?: (camId: string) => void;
}

export function VideoPlayer({
  processedVideoUrl = "/api/media/fence_detection.mp4",
  sourceVideoUrl = "/api/media/videos/test.mp4",
  cameraId = "BOP-CAM-01",
  fps = 25.0,
  fenceY = 700,
  availableCameras = [],
  onSelectCamera,
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(true);
  const [currentSource, setCurrentSource] = useState<"annotated" | "raw">("annotated");
  const [showFenceOverlay, setShowFenceOverlay] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [selectedCam, setSelectedCam] = useState(cameraId);

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play();
      setIsPlaying(true);
    }
  };

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
      setDuration(videoRef.current.duration || 0);
    }
  };

  const rawSource =
    selectedCam === "BOP-CAM-02"
      ? "/api/media/License Plate Detection Test.mp4"
      : sourceVideoUrl || "/api/media/videos/test.mp4";

  const annotatedSource = processedVideoUrl || "/api/media/fence_detection.mp4";

  const activeUrl = currentSource === "annotated" ? annotatedSource : rawSource;

  const handleCamChange = (newCamId: string) => {
    setSelectedCam(newCamId);
    if (onSelectCamera) onSelectCamera(newCamId);
  };

  return (
    <div className="bg-zinc-950 rounded-xl border border-zinc-200 overflow-hidden shadow-sm text-white flex flex-col font-sans">
      {/* Simple Top Bar */}
      <div className="px-4 py-3 bg-zinc-900 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <div className="flex items-center gap-1.5 font-mono text-xs font-medium text-zinc-100">
              <Camera className="w-3.5 h-3.5 text-zinc-400" />
              <select
                value={selectedCam}
                onChange={(e) => handleCamChange(e.target.value)}
                className="bg-zinc-800 text-zinc-100 font-medium border border-zinc-700 px-2 py-0.5 rounded-md focus:outline-none cursor-pointer uppercase text-xs"
              >
                <option value="BOP-CAM-01">BOP-CAM-01 (Sector 4 North)</option>
                <option value="BOP-CAM-02">BOP-CAM-02 (East Access Road)</option>
              </select>
            </div>
          </div>
          <span className="text-xs text-zinc-400 font-mono hidden sm:inline">
            2560×1440 @ {fps} FPS
          </span>
        </div>

        {/* View Toggles */}
        <div className="flex items-center gap-1 bg-zinc-800 p-1 rounded-md text-xs font-mono">
          <button
            onClick={() => setCurrentSource("annotated")}
            className={`px-2.5 py-1 rounded transition-all flex items-center gap-1.5 font-medium ${
              currentSource === "annotated"
                ? "bg-zinc-100 text-zinc-900 font-semibold"
                : "text-zinc-400 hover:text-zinc-100"
            }`}
          >
            <Shield className="w-3 h-3" />
            <span>AI Stream</span>
          </button>
          <button
            onClick={() => setCurrentSource("raw")}
            className={`px-2.5 py-1 rounded transition-all flex items-center gap-1.5 font-medium ${
              currentSource === "raw"
                ? "bg-zinc-100 text-zinc-900 font-semibold"
                : "text-zinc-400 hover:text-zinc-100"
            }`}
          >
            <Eye className="w-3 h-3" />
            <span>Raw Feed</span>
          </button>
        </div>
      </div>

      {/* Video Container */}
      <div className="relative aspect-video bg-black flex items-center justify-center group overflow-hidden">
        <video
          ref={videoRef}
          key={activeUrl}
          src={activeUrl}
          autoPlay
          loop
          muted
          playsInline
          onTimeUpdate={handleTimeUpdate}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          className="w-full h-full object-contain"
        />

        {/* Tripwire Line */}
        {showFenceOverlay && currentSource === "raw" && (
          <div
            className="absolute left-0 right-0 border-b-2 border-dashed border-rose-500 pointer-events-none flex items-center justify-between px-4"
            style={{ top: "48.6%" }}
          >
            <span className="px-2 py-0.5 rounded bg-rose-500 text-white text-[10px] font-mono tracking-wider font-semibold shadow">
              Tripwire Y={fenceY}
            </span>
            <span className="px-2 py-0.5 rounded bg-zinc-900/80 text-zinc-200 text-[10px] font-mono border border-zinc-700">
              {selectedCam === "BOP-CAM-01" ? "Sector 4 North" : "East Access Road"}
            </span>
          </div>
        )}

        {/* Play/Pause Hover Button */}
        <button
          onClick={togglePlay}
          className="absolute inset-0 m-auto w-12 h-12 rounded-full bg-zinc-900/80 text-white flex items-center justify-center opacity-0 group-hover:opacity-90 hover:scale-105 transition-all border border-zinc-700"
        >
          {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
        </button>
      </div>

      {/* Control Bar */}
      <div className="px-4 py-2.5 bg-zinc-900 flex items-center justify-between text-xs text-zinc-400 border-t border-zinc-800 font-mono">
        <div className="flex items-center gap-3">
          <button
            onClick={togglePlay}
            className="p-1 hover:text-white transition-colors"
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          </button>
          <span className="text-zinc-200 text-[11px]">
            {Math.floor(currentTime)}s / {Math.floor(duration || 18)}s
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFenceOverlay(!showFenceOverlay)}
            className={`flex items-center gap-1.5 px-2 py-1 rounded transition-colors text-[11px] ${
              showFenceOverlay
                ? "bg-zinc-800 text-zinc-100 border border-zinc-700"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            <Layers className="w-3 h-3" />
            <span>Tripwire Overlay</span>
          </button>

          <button
            onClick={() => {
              if (videoRef.current) {
                videoRef.current.currentTime = 0;
                videoRef.current.play();
              }
            }}
            title="Restart playback"
            className="p-1 hover:text-white transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
