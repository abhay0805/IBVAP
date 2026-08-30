"use client";

import React, { useState } from "react";
import { SecurityAlert } from "@/lib/types";
import { CheckCircle2, Volume2, VolumeX, Eye, ShieldAlert } from "lucide-react";

interface LiveAlertStreamProps {
  alerts: SecurityAlert[];
  onAcknowledge: (alertId: string) => void;
  onSelectAlert: (alert: SecurityAlert) => void;
}

export function LiveAlertStream({
  alerts,
  onAcknowledge,
  onSelectAlert,
}: LiveAlertStreamProps) {
  const [audioEnabled, setAudioEnabled] = useState(true);

  const getSeverityStyle = (severity: string) => {
    switch (severity) {
      case "CRITICAL":
        return "bg-rose-50 text-rose-600 border-rose-200";
      case "HIGH":
        return "bg-amber-50 text-amber-600 border-amber-200";
      case "MEDIUM":
        return "bg-sky-50 text-sky-600 border-sky-200";
      default:
        return "bg-zinc-100 text-zinc-600 border-zinc-200";
    }
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-xl border border-zinc-200 shadow-sm overflow-hidden font-sans">
      {/* Header */}
      <div className="p-4 border-b border-zinc-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-zinc-700" />
          <h3 className="text-sm font-semibold text-zinc-900">
            Live Threat Feed
          </h3>
          <span className="px-2 py-0.5 text-[11px] font-medium bg-zinc-100 text-zinc-600 rounded-full">
            {alerts.length} Total
          </span>
        </div>

        <button
          onClick={() => setAudioEnabled(!audioEnabled)}
          className="p-1 hover:bg-zinc-100 text-zinc-400 hover:text-zinc-700 rounded-md transition-colors"
        >
          {audioEnabled ? (
            <Volume2 className="w-4 h-4 text-zinc-700" />
          ) : (
            <VolumeX className="w-4 h-4 text-zinc-400" />
          )}
        </button>
      </div>

      {/* Alert Feed Items */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2 max-h-[480px]">
        {alerts.length === 0 ? (
          <div className="py-12 text-center text-zinc-400">
            <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-500 mb-2" />
            <p className="text-xs font-semibold text-zinc-700">All Sectors Normal</p>
            <p className="text-xs text-zinc-400 mt-0.5">No active alerts</p>
          </div>
        ) : (
          alerts.map((alert) => {
            const isAck = alert.status === "ACKNOWLEDGED";
            return (
              <div
                key={alert.alert_id}
                className={`p-3 border rounded-lg transition-all ${
                  isAck
                    ? "bg-zinc-50 border-zinc-100 opacity-60"
                    : "bg-white border-zinc-200 hover:border-zinc-300"
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-[10px] font-semibold tracking-wide px-2 py-0.5 border rounded-full ${getSeverityStyle(
                        alert.severity
                      )}`}
                    >
                      {alert.severity}
                    </span>
                    <span className="text-xs font-mono font-medium text-zinc-900">
                      {alert.alert_id}
                    </span>
                  </div>
                  <span className="text-[11px] text-zinc-400 font-mono">
                    {new Date(alert.timestamp).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                </div>

                <p className="text-xs text-zinc-700 font-medium leading-relaxed mb-2">
                  {alert.message}
                </p>

                <div className="flex items-center justify-between text-[11px] text-zinc-500 pt-2 border-t border-zinc-100 font-mono">
                  <span>Cam: <strong className="text-zinc-800">{alert.camera_id}</strong> · Track #{alert.track_id}</span>

                  <div className="flex items-center gap-2">
                    {alert.evidence_path && (
                      <button
                        onClick={() => onSelectAlert(alert)}
                        className="text-xs font-medium text-zinc-700 hover:underline flex items-center gap-1"
                      >
                        <Eye className="w-3 h-3 text-zinc-500" />
                        <span>Evidence</span>
                      </button>
                    )}

                    {!isAck ? (
                      <button
                        onClick={() => onAcknowledge(alert.alert_id)}
                        className="px-2.5 py-1 text-xs font-medium bg-zinc-900 text-white rounded-md hover:bg-zinc-800 transition-colors"
                      >
                        Ack
                      </button>
                    ) : (
                      <span className="text-[10px] text-emerald-600 font-semibold flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" /> Ack'd
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
