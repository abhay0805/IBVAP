"use client";

import React from "react";
import { SecurityAlert, SecurityEvent } from "@/lib/types";
import { X, ShieldAlert, ExternalLink, Lock } from "lucide-react";

interface EvidenceModalProps {
  item: SecurityAlert | SecurityEvent | null;
  onClose: () => void;
}

export function EvidenceModal({ item, onClose }: EvidenceModalProps) {
  if (!item) return null;

  const eventId = "event_id" in item ? item.event_id : (item as SecurityAlert).alert_id;
  const imageSrc = item.evidence_path
    ? `/api/media/${item.evidence_path.replace(/\\/g, "/")}`
    : `/api/media/output/evidence/EVT-0001.jpg`;

  const isEvent = "confidence" in item;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md font-mono">
      <div
        className="bg-[#0A0F1D] w-full max-w-4xl border border-[#00E5FF]/40 shadow-[0_0_30px_rgba(0,229,255,0.2)] overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-4 bg-[#050811] border-b border-[#1E293B] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#FF1744] text-white font-bold">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h3 className="text-base font-extrabold uppercase tracking-widest text-[#F8FAFC]">
                  CLASSIFIED INCIDENT EVIDENCE
                </h3>
                <span className="font-mono text-xs px-2.5 py-0.5 bg-[#050811] border border-[#00E5FF] text-[#00E5FF] font-bold">
                  {eventId}
                </span>
              </div>
              <p className="text-xs text-[#94A3B8] mt-0.5">
                // RAW RECONNAISSANCE HIGH-RESOLUTION FRAME CAPTURE & TELEMETRY
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 hover:bg-[#1E293B] text-[#94A3B8] hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto grid grid-cols-1 lg:grid-cols-12 gap-6 bg-[#020408]">
          {/* Main Frame Snapshot */}
          <div className="lg:col-span-8 flex flex-col gap-2">
            <div className="relative bg-[#050811] border border-[#1E293B]">
              <img
                src={imageSrc}
                alt={`Evidence for ${eventId}`}
                className="w-full h-auto object-contain max-h-[460px]"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = "/api/media/output/evidence/EVT-0001.jpg";
                }}
              />
              <div className="absolute bottom-2 left-2 px-3 py-1 bg-[#050811] text-[#00E5FF] border border-[#00E5FF]/40 font-mono text-[10px] font-bold uppercase">
                FRAME #{item.frame_number} · SENSOR {item.camera_id}
              </div>
            </div>
          </div>

          {/* Telemetry Breakdown */}
          <div className="lg:col-span-4 flex flex-col justify-between space-y-4">
            <div className="space-y-4">
              <h4 className="text-xs uppercase tracking-widest font-bold text-[#94A3B8]">
                // TELEMETRY LOGS
              </h4>

              <div className="space-y-2 text-xs">
                <div className="p-3 bg-[#0A0F1D] border border-[#1E293B] flex items-center justify-between">
                  <span className="text-[#94A3B8]">EVENT TYPE</span>
                  <span className="font-bold text-[#00E5FF] uppercase">{item.event_type}</span>
                </div>

                <div className="p-3 bg-[#0A0F1D] border border-[#1E293B] flex items-center justify-between">
                  <span className="text-[#94A3B8]">TARGET CLASS</span>
                  <span className="font-bold text-white uppercase">
                    {item.object_type || "VEHICLE"} (TRK #{item.track_id})
                  </span>
                </div>

                {isEvent && (
                  <div className="p-3 bg-[#0A0F1D] border border-[#1E293B] flex items-center justify-between">
                    <span className="text-[#94A3B8]">DIRECTION</span>
                    <span className="px-2 py-0.5 bg-[#FF1744] text-white font-black text-[10px] uppercase">
                      {(item as SecurityEvent).direction || "INBOUND"}
                    </span>
                  </div>
                )}

                <div className="p-3 bg-[#0A0F1D] border border-[#1E293B] flex items-center justify-between">
                  <span className="text-[#94A3B8]">TIMESTAMP</span>
                  <span className="text-white text-[11px]">
                    {new Date(item.timestamp).toLocaleString()}
                  </span>
                </div>

                {"plate_text" in item && item.plate_text && (
                  <div className="p-3 bg-[#0A0F1D] border border-[#00E5FF]">
                    <span className="text-[#94A3B8] block text-[10px] uppercase mb-1">// ANPR PLATE MATCH</span>
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-[#00E5FF] text-base bg-[#020408] px-2.5 py-1 border border-[#1E293B]">
                        {item.plate_text}
                      </span>
                      <span className="text-[11px] text-[#00E676] font-bold">
                        {Math.round((item.plate_confidence || 0.92) * 100)}% CONF
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="pt-4 border-t border-[#1E293B] flex gap-2">
              <a
                href={imageSrc}
                target="_blank"
                rel="noreferrer"
                className="flex-1 py-2.5 px-3 bg-[#050811] hover:bg-[#1E293B] border border-[#1E293B] text-white text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>RAW FRAME</span>
              </a>
              <button
                onClick={onClose}
                className="py-2.5 px-5 bg-[#00E5FF] hover:bg-[#00B0FF] text-black text-xs font-extrabold uppercase tracking-wider transition-colors"
              >
                CLOSE
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
