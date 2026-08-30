"use client";

import React, { useState } from "react";
import {
  Radio,
  Camera,
  Bell,
  Cpu,
  Save,
  CheckCircle2,
  Globe,
} from "lucide-react";

export default function ConfigPage() {
  const [webhookUrl, setWebhookUrl] = useState("http://control-room:8080/ingest/alerts");
  const [webhookToken, setWebhookToken] = useState("ibvap_secret_token_2026");
  const [alertCooldown, setAlertCooldown] = useState(10);
  const [minObservations, setMinObservations] = useState(3);
  const [saved, setSaved] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-hairline pb-6">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider font-semibold text-primary mb-1">
            <Radio className="w-3.5 h-3.5" />
            <span>Infrastructure & Channels</span>
          </div>
          <h1 className="font-serif text-3xl md:text-5xl text-ink font-normal tracking-tight">
            System & Sensor Configuration
          </h1>
          <p className="mt-2 text-sm text-body leading-relaxed max-w-2xl">
            Manage active camera sensors, multi-channel alert dispatch pipelines, and AI inferencing parameters.
          </p>
        </div>

        {saved && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-success/15 text-success text-xs font-medium border border-success/30">
            <CheckCircle2 className="w-4 h-4" />
            <span>Configuration saved successfully</span>
          </div>
        )}
      </div>

      <form onSubmit={handleSave} className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Camera Sensor Registry */}
        <div className="lg:col-span-6 space-y-6">
          <div className="p-6 rounded-xl bg-surface-card border border-hairline space-y-4">
            <div className="flex items-center gap-2 border-b border-hairline pb-3">
              <Camera className="w-4 h-4 text-primary" />
              <h3 className="font-serif text-xl font-normal text-ink">
                Perimeter Cameras
              </h3>
            </div>

            <div className="space-y-3">
              <div className="p-3.5 rounded-md bg-canvas border border-hairline flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-ink text-xs">BOP-CAM-01</span>
                    <span className="px-2 py-0.2 rounded-pill bg-success/15 text-success text-[10px] font-semibold">
                      ACTIVE
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-soft mt-0.5">
                    Sector 4 Northern Fence · 2560×1440 @ 25 FPS
                  </p>
                </div>
                <span className="font-mono text-xs text-muted">Y=700</span>
              </div>

              <div className="p-3.5 rounded-md bg-canvas border border-hairline flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-ink text-xs">BOP-CAM-02</span>
                    <span className="px-2 py-0.2 rounded-pill bg-surface-card text-muted text-[10px] font-semibold">
                      STANDBY
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-soft mt-0.5">
                    Sector 4 Eastern Gate · 1920×1080 @ 30 FPS
                  </p>
                </div>
                <span className="font-mono text-xs text-muted">Y=540</span>
              </div>
            </div>
          </div>

          {/* AI Inferencing Stack */}
          <div className="p-6 rounded-xl bg-surface-dark text-on-dark border border-surface-dark-elevated space-y-4 font-mono text-xs">
            <div className="flex items-center gap-2 border-b border-surface-dark-soft pb-3">
              <Cpu className="w-4 h-4 text-primary" />
              <h3 className="font-serif text-xl font-normal text-on-dark">
                AI Engine & Weights
              </h3>
            </div>

            <div className="space-y-2 text-on-dark-soft text-[11.5px]">
              <div className="flex justify-between py-1 border-b border-surface-dark-soft">
                <span>Object Detector:</span>
                <span className="text-on-dark font-bold">Ultralytics YOLO (yolo26n.pt)</span>
              </div>
              <div className="flex justify-between py-1 border-b border-surface-dark-soft">
                <span>ANPR OCR Engine:</span>
                <span className="text-on-dark font-bold">EasyOCR + CLAHE Enhancement</span>
              </div>
              <div className="flex justify-between py-1 border-b border-surface-dark-soft">
                <span>Persistence Backend:</span>
                <span className="text-on-dark font-bold">SQLite 3 (WAL Mode) + JSON Feeds</span>
              </div>
            </div>
          </div>
        </div>

        {/* Alert Dispatch & Channels */}
        <div className="lg:col-span-6 space-y-6">
          <div className="p-6 rounded-xl bg-surface-card border border-hairline space-y-4">
            <div className="flex items-center gap-2 border-b border-hairline pb-3">
              <Bell className="w-4 h-4 text-primary" />
              <h3 className="font-serif text-xl font-normal text-ink">
                Alert Dispatch Channels
              </h3>
            </div>

            <div className="space-y-4 text-xs">
              <div className="space-y-1.5">
                <label className="font-semibold text-ink flex items-center gap-1.5">
                  <Globe className="w-3.5 h-3.5 text-primary" />
                  <span>Outbound Webhook URL (Emergency Dispatch)</span>
                </label>
                <input
                  type="url"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  className="w-full px-3 py-2 rounded-md bg-canvas border border-hairline text-ink font-mono focus:outline-none focus:border-primary"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-ink">Webhook Bearer Token</label>
                <input
                  type="password"
                  value={webhookToken}
                  onChange={(e) => setWebhookToken(e.target.value)}
                  className="w-full px-3 py-2 rounded-md bg-canvas border border-hairline text-ink font-mono focus:outline-none focus:border-primary"
                />
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                <div className="space-y-1.5">
                  <label className="font-semibold text-ink">Alert Cooldown (sec)</label>
                  <input
                    type="number"
                    value={alertCooldown}
                    onChange={(e) => setAlertCooldown(parseInt(e.target.value, 10))}
                    className="w-full px-3 py-2 rounded-md bg-canvas border border-hairline text-ink focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="font-semibold text-ink">Min Observations</label>
                  <input
                    type="number"
                    value={minObservations}
                    onChange={(e) => setMinObservations(parseInt(e.target.value, 10))}
                    className="w-full px-3 py-2 rounded-md bg-canvas border border-hairline text-ink focus:outline-none focus:border-primary"
                  />
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-hairline flex justify-end">
              <button
                type="submit"
                className="px-5 py-2 rounded-md bg-primary hover:bg-primary-active text-on-primary text-xs font-medium flex items-center gap-1.5 transition-colors shadow-sm"
              >
                <Save className="w-3.5 h-3.5" />
                <span>Save Configuration</span>
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
