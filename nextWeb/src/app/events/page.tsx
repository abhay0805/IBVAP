"use client";

import React, { useEffect, useState } from "react";
import { SecurityEvent } from "@/lib/types";
import { EvidenceModal } from "@/components/EvidenceModal";
import { Shield, Search, Download, Eye, Car, User } from "lucide-react";

export default function EventsPage() {
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [filteredEvents, setFilteredEvents] = useState<SecurityEvent[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedType, setSelectedType] = useState("ALL");
  const [selectedCamera, setSelectedCamera] = useState("ALL");
  const [selectedEvent, setSelectedEvent] = useState<SecurityEvent | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchEvents();
  }, []);

  const fetchEvents = async () => {
    try {
      setIsLoading(true);
      const res = await fetch("/api/events?limit=200");
      if (res.ok) {
        const data = await res.json();
        setEvents(data.events || []);
        setFilteredEvents(data.events || []);
      }
    } catch (err) {
      console.error("Error fetching events:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    let result = [...events];

    if (selectedType !== "ALL") {
      result = result.filter((e) => e.event_type === selectedType);
    }
    if (selectedCamera !== "ALL") {
      result = result.filter((e) => e.camera_id === selectedCamera);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (e) =>
          e.event_id.toLowerCase().includes(q) ||
          e.object_type?.toLowerCase().includes(q) ||
          e.plate_text?.toLowerCase().includes(q) ||
          e.camera_id.toLowerCase().includes(q)
      );
    }

    setFilteredEvents(result);
  }, [searchQuery, selectedType, selectedCamera, events]);

  const exportCSV = () => {
    if (filteredEvents.length === 0) return;
    const headers = [
      "Event ID",
      "Type",
      "Object",
      "Track ID",
      "Camera",
      "Direction",
      "Confidence",
      "Frame",
      "Plate",
      "Timestamp",
    ];
    const rows = filteredEvents.map((e) => [
      e.event_id,
      e.event_type,
      e.object_type || e.object || "unknown",
      e.track_id,
      e.camera_id,
      e.direction || "N/A",
      e.confidence,
      e.frame_number,
      e.plate_text || "N/A",
      e.timestamp,
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `ibvap_incidents_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-hairline pb-6">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider font-semibold text-primary mb-1">
            <Shield className="w-3.5 h-3.5" />
            <span>Audit & Verification Archive</span>
          </div>
          <h1 className="font-serif text-3xl md:text-5xl text-ink font-normal tracking-tight">
            Security Incident Explorer
          </h1>
          <p className="mt-2 text-sm text-body leading-relaxed max-w-2xl">
            Complete cryptographic audit log of all virtual fence crossings, vehicle observations, and ANPR plate detections.
          </p>
        </div>

        <button
          onClick={exportCSV}
          className="px-4 py-2 rounded-md bg-surface-card hover:bg-surface-cream-strong border border-hairline text-ink text-xs font-medium flex items-center gap-2 transition-colors shadow-sm self-start md:self-auto"
        >
          <Download className="w-3.5 h-3.5 text-primary" />
          <span>Export CSV Archive</span>
        </button>
      </div>

      {/* Filter & Search Bar */}
      <div className="p-4 rounded-xl bg-surface-card border border-hairline flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Search */}
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search Event ID, Track #, Plate..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-md bg-canvas border border-hairline text-xs text-ink placeholder:text-muted-soft focus:outline-none focus:border-primary transition-all"
          />
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 w-full md:w-auto overflow-x-auto">
          {/* Event Type Filter */}
          <div className="flex items-center gap-1.5 bg-canvas px-2.5 py-1.5 rounded-md border border-hairline text-xs">
            <span className="text-muted font-medium">Type:</span>
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="bg-transparent text-ink font-medium focus:outline-none cursor-pointer"
            >
              <option value="ALL">All Types</option>
              <option value="VIRTUAL_FENCE_BREACH">Virtual Fence Breach</option>
              <option value="PLATE_READ">ANPR Plate Read</option>
            </select>
          </div>

          {/* Camera Filter */}
          <div className="flex items-center gap-1.5 bg-canvas px-2.5 py-1.5 rounded-md border border-hairline text-xs">
            <span className="text-muted font-medium">Camera:</span>
            <select
              value={selectedCamera}
              onChange={(e) => setSelectedCamera(e.target.value)}
              className="bg-transparent text-ink font-medium focus:outline-none cursor-pointer"
            >
              <option value="ALL">All Cameras</option>
              <option value="BOP-CAM-01">BOP-CAM-01</option>
              <option value="BOP-CAM-02">BOP-CAM-02</option>
            </select>
          </div>

          <span className="text-xs font-mono text-muted pl-2 whitespace-nowrap">
            {filteredEvents.length} records
          </span>
        </div>
      </div>

      {/* Events Table */}
      <div className="bg-surface-card rounded-xl border border-hairline overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-surface-cream-strong border-b border-hairline text-muted uppercase tracking-wider font-semibold">
                <th className="py-3 px-4">Event ID</th>
                <th className="py-3 px-4">Target & Track</th>
                <th className="py-3 px-4">Camera</th>
                <th className="py-3 px-4">Direction</th>
                <th className="py-3 px-4">Confidence</th>
                <th className="py-3 px-4">Plate Reading</th>
                <th className="py-3 px-4">Timestamp</th>
                <th className="py-3 px-4 text-right">Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-muted">
                    Loading incident archives...
                  </td>
                </tr>
              ) : filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-muted">
                    No incidents match the selected criteria.
                  </td>
                </tr>
              ) : (
                filteredEvents.map((evt) => (
                  <tr
                    key={evt.event_id}
                    className="hover:bg-surface-soft/80 transition-colors cursor-pointer group"
                    onClick={() => setSelectedEvent(evt)}
                  >
                    <td className="py-3.5 px-4 font-mono font-bold text-ink">
                      {evt.event_id}
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2">
                        {evt.object_type === "person" ? (
                          <User className="w-3.5 h-3.5 text-muted" />
                        ) : (
                          <Car className="w-3.5 h-3.5 text-primary" />
                        )}
                        <span className="capitalize font-medium text-ink">
                          {evt.object_type || "Vehicle"}
                        </span>
                        <span className="font-mono text-muted-soft">#{evt.track_id}</span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-body">
                      {evt.camera_id}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="px-2 py-0.5 rounded-pill bg-primary/10 text-primary font-bold text-[10px]">
                        {evt.direction || "INBOUND"}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-body">
                      {Math.round(evt.confidence * 100)}%
                    </td>
                    <td className="py-3.5 px-4">
                      {evt.plate_text ? (
                        <span className="font-mono font-bold bg-canvas border border-hairline px-2 py-0.5 rounded text-ink">
                          {evt.plate_text}
                        </span>
                      ) : (
                        <span className="text-muted-soft italic">—</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-muted-soft">
                      {new Date(evt.timestamp).toLocaleString([], {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedEvent(evt);
                        }}
                        className="px-2.5 py-1 rounded bg-canvas group-hover:bg-primary group-hover:text-on-primary border border-hairline text-ink text-xs font-medium inline-flex items-center gap-1 transition-all"
                      >
                        <Eye className="w-3 h-3" />
                        <span>Inspect</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evidence Snapshot Modal */}
      <EvidenceModal
        item={selectedEvent}
        onClose={() => setSelectedEvent(null)}
      />
    </div>
  );
}
