"use client";

import React, { useEffect, useState } from "react";
import { MetricCard } from "@/components/MetricCard";
import { VideoPlayer } from "@/components/VideoPlayer";
import { LiveAlertStream } from "@/components/LiveAlertStream";
import { EvidenceModal } from "@/components/EvidenceModal";
import { SecurityAlert, SecurityEvent, SystemStats } from "@/lib/types";
import {
  ShieldAlert,
  AlertOctagon,
  Eye,
  Activity,
  Layers,
  ArrowUpRight,
  Clock,
  Radio,
} from "lucide-react";
import Link from "next/link";

export default function OperationsPage() {
  const [stats, setStats] = useState<SystemStats>({
    totalEvents: 3,
    fenceBreaches: 3,
    plateReads: 1,
    activeAlerts: 3,
    criticalAlerts: 0,
    highAlerts: 3,
    mediumAlerts: 0,
    lowAlerts: 0,
    camerasOnline: 2,
    processedVideoFps: 25.0,
    activeCameraId: "BOP-CAM-01",
    cameras: [],
  });

  const [alerts, setAlerts] = useState<SecurityAlert[]>([]);
  const [recentEvents, setRecentEvents] = useState<SecurityEvent[]>([]);
  const [selectedItem, setSelectedItem] = useState<SecurityAlert | SecurityEvent | null>(null);
  const [selectedCamId, setSelectedCamId] = useState("BOP-CAM-01");

  const fetchData = async () => {
    try {
      const [statsRes, alertsRes, eventsRes] = await Promise.all([
        fetch("/api/stats"),
        fetch("/api/alerts?limit=20"),
        fetch("/api/events?limit=5"),
      ]);

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
        if (statsData.activeCameraId) setSelectedCamId(statsData.activeCameraId);
      }
      if (alertsRes.ok) {
        const alertsData = await alertsRes.json();
        setAlerts(alertsData.alerts || []);
      }
      if (eventsRes.ok) {
        const eventsData = await eventsRes.json();
        setRecentEvents(eventsData.events || []);
      }
    } catch (err) {
      console.error("Error fetching operations data:", err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleAcknowledge = async (alertId: string) => {
    try {
      await fetch(`/api/alerts/${alertId}/ack`, { method: "POST" });
      setAlerts((prev) =>
        prev.map((a) => (a.alert_id === alertId ? { ...a, status: "ACKNOWLEDGED" } : a))
      );
    } catch (err) {
      console.error("Error acknowledging alert:", err);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-300 font-sans">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-zinc-200 pb-6">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider font-semibold text-zinc-500 mb-1">
            <Radio className="w-3.5 h-3.5 text-zinc-700 animate-pulse" />
            <span>Operations Dashboard</span>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold text-zinc-900 tracking-tight">
            Border Watchtower Surveillance
          </h1>
          <p className="mt-2 text-sm text-zinc-600 leading-relaxed max-w-2xl">
            Real-time multi-spectral virtual tripwire telemetry, optical perimeter breach tracking, and automated vehicle identification.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/lab"
            className="px-3.5 py-2 bg-white hover:bg-zinc-50 border border-zinc-200 text-zinc-800 text-xs font-medium rounded-md flex items-center gap-1.5 transition-colors shadow-sm"
          >
            <Layers className="w-3.5 h-3.5 text-zinc-600" />
            <span>Tripwire Lab</span>
          </Link>
          <Link
            href="/events"
            className="px-4 py-2 bg-zinc-900 hover:bg-zinc-800 text-white text-xs font-medium rounded-md flex items-center gap-1.5 transition-colors shadow-sm"
          >
            <span>All Incidents</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* KPI Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Active Perimeter Alerts"
          value={stats.activeAlerts}
          subtitle="Awaiting triage"
          icon={AlertOctagon}
          trend={stats.activeAlerts > 0 ? "Action Req" : "Normal"}
        />
        <MetricCard
          title="Fence Crossings"
          value={stats.fenceBreaches}
          subtitle="Tripwire Y=700 crossings"
          icon={ShieldAlert}
          trend="+3 today"
        />
        <MetricCard
          title="ANPR Plate Reads"
          value={stats.plateReads}
          subtitle="OCR validated plates"
          icon={Eye}
          trend="92% conf"
        />
        <MetricCard
          title="Active Camera Feeds"
          value={`${stats.camerasOnline}/2`}
          subtitle={`${selectedCamId} · 25 FPS`}
          icon={Activity}
          trend="Online"
        />
      </div>

      {/* Main Console Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Stream */}
        <div className="lg:col-span-8 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-zinc-900 tracking-tight">
              Primary Surveillance Stream
            </h2>
            <span className="text-xs font-mono text-zinc-500 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-zinc-400" />
              <span>Latency: 42ms</span>
            </span>
          </div>

          <VideoPlayer
            processedVideoUrl="/api/media/output/fence_detection.mp4"
            sourceVideoUrl="/api/media/videos/test.mp4"
            cameraId={selectedCamId}
            fps={stats.processedVideoFps}
            fenceY={selectedCamId === "BOP-CAM-02" ? 540 : 700}
            availableCameras={stats.cameras}
            onSelectCamera={(camId) => setSelectedCamId(camId)}
          />

          {/* Quick Incident Log Bar */}
          <div className="p-4 rounded-xl bg-white border border-zinc-200 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs uppercase tracking-wider font-semibold text-zinc-700">
                Recent Perimeter Breaches
              </span>
              <Link href="/events" className="text-xs text-zinc-900 font-medium hover:underline flex items-center gap-1">
                <span>View All</span>
                <ArrowUpRight className="w-3 h-3" />
              </Link>
            </div>

            <div className="divide-y divide-zinc-100">
              {recentEvents.length === 0 ? (
                <p className="text-xs text-zinc-500 py-2">No incidents recorded yet.</p>
              ) : (
                recentEvents.slice(0, 3).map((evt) => (
                  <div
                    key={evt.event_id}
                    className="py-2.5 flex items-center justify-between text-xs cursor-pointer hover:bg-zinc-50 px-2 rounded-md transition-colors font-mono"
                    onClick={() => setSelectedItem(evt)}
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-bold text-zinc-900">{evt.event_id}</span>
                      <span className="capitalize text-zinc-600 font-medium">{evt.object_type || "Vehicle"} #{evt.track_id}</span>
                      <span className="px-2 py-0.5 bg-rose-50 text-rose-600 font-semibold text-[10px] rounded-full border border-rose-200 uppercase">
                        {evt.direction || "INBOUND"}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-zinc-400">Frame #{evt.frame_number}</span>
                      <span className="text-zinc-900 font-medium">Inspect →</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right Live Alert Stream */}
        <div className="lg:col-span-4 h-[620px]">
          <LiveAlertStream
            alerts={alerts}
            onAcknowledge={handleAcknowledge}
            onSelectAlert={(alert) => setSelectedItem(alert)}
          />
        </div>
      </div>

      {/* Evidence Snapshot Modal */}
      <EvidenceModal
        item={selectedItem}
        onClose={() => setSelectedItem(null)}
      />
    </div>
  );
}
