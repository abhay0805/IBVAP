"use client";

import React, { useEffect, useState } from "react";
import { PlateRecord } from "@/lib/types";
import {
  Eye,
  Search,
  Plus,
  Trash2,
  Car,
  ShieldCheck,
  ExternalLink,
} from "lucide-react";

export default function AnprPage() {
  const [plates, setPlates] = useState<PlateRecord[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [watchlist, setWatchlist] = useState<string[]>([
    "MH12AB1234",
    "DL01XY9999",
    "GJ05ZZ4444",
  ]);
  const [newWatchlistPlate, setNewWatchlistPlate] = useState("");

  useEffect(() => {
    fetchPlates();
  }, []);

  const fetchPlates = async () => {
    try {
      const res = await fetch("/api/anpr");
      if (res.ok) {
        const data = await res.json();
        setPlates(data.plates || []);
      }
    } catch (err) {
      console.error("Error fetching ANPR plates:", err);
    }
  };

  const filteredPlates = plates.filter(
    (p) =>
      p.plate_text.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.camera_id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const addWatchlistPlate = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = newWatchlistPlate.trim().toUpperCase();
    if (clean && !watchlist.includes(clean)) {
      setWatchlist([...watchlist, clean]);
      setNewWatchlistPlate("");
    }
  };

  const removeWatchlistPlate = (plate: string) => {
    setWatchlist(watchlist.filter((p) => p !== plate));
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-hairline pb-6">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider font-semibold text-primary mb-1">
            <Eye className="w-3.5 h-3.5" />
            <span>Optical Character Recognition Engine</span>
          </div>
          <h1 className="font-serif text-3xl md:text-5xl text-ink font-normal tracking-tight">
            ANPR Vehicle Intelligence
          </h1>
          <p className="mt-2 text-sm text-body leading-relaxed max-w-2xl">
            Automated license plate localization, CLAHE contrast enhancement, slot-based normalization, and flagged vehicle cross-referencing.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-muted bg-surface-card px-3 py-1.5 rounded-md border border-hairline">
            OCR CONFIDENCE THRESHOLD: <strong>35%</strong>
          </span>
        </div>
      </div>

      {/* Grid: Watchlist Management & Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Plate Crop Gallery & Log */}
        <div className="lg:col-span-8 space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="font-serif text-2xl text-ink font-normal">
              Detected Plate Sightings & Crop Evidence
            </h2>
            <div className="relative w-64">
              <Search className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search Plate or Camera..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 rounded-md bg-surface-card border border-hairline text-xs text-ink focus:outline-none focus:border-primary transition-all"
              />
            </div>
          </div>

          {/* Plate Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {filteredPlates.length === 0 ? (
              <div className="col-span-2 py-12 text-center text-muted bg-surface-card rounded-xl border border-hairline">
                <Car className="w-8 h-8 mx-auto text-muted-soft mb-2" />
                <p className="text-sm font-medium">No plate sightings found</p>
                <p className="text-xs text-muted-soft">Run detection on vehicle footage to populate</p>
              </div>
            ) : (
              filteredPlates.map((record, index) => {
                const isWatchlisted = watchlist.includes(record.plate_text);
                const cropUrl = record.crop_path
                  ? `/api/media/${record.crop_path.replace(/\\/g, "/")}`
                  : `/api/media/output/evidence/PLT-1-0020.jpg`;

                return (
                  <div
                    key={`${record.plate_text}-${index}`}
                    className={`p-4 rounded-xl border transition-all flex flex-col justify-between ${
                      isWatchlisted
                        ? "bg-primary/5 border-primary/40 shadow-sm"
                        : "bg-surface-card border-hairline hover:border-muted"
                    }`}
                  >
                    <div>
                      {/* Top Header */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono text-base font-bold bg-canvas border border-hairline px-2.5 py-1 rounded text-ink shadow-sm tracking-wider">
                            {record.plate_text}
                          </span>
                          {isWatchlisted && (
                            <span className="px-2 py-0.5 rounded-pill bg-error/15 text-error text-[10px] font-bold tracking-wider">
                              FLAGGED
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] font-mono text-accent-teal font-semibold">
                          {Math.round(record.confidence * 100)}% Conf
                        </span>
                      </div>

                      {/* Plate Crop Image Viewer */}
                      <div className="relative aspect-[3/1] bg-surface-dark rounded-lg overflow-hidden border border-surface-dark-elevated mb-3 flex items-center justify-center">
                        <img
                          src={cropUrl}
                          alt={`Plate Crop ${record.plate_text}`}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLImageElement).src = "/api/media/output/evidence/PLT-1-0020.jpg";
                          }}
                        />
                        <div className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-surface-dark/80 text-on-dark text-[9px] font-mono">
                          ROI CROP
                        </div>
                      </div>

                      {/* Metadata */}
                      <div className="space-y-1 text-xs text-muted">
                        <div className="flex items-center justify-between">
                          <span>Target:</span>
                          <span className="capitalize font-medium text-ink">
                            {record.object_type} #{record.track_id}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span>Camera:</span>
                          <span className="font-mono text-body">{record.camera_id}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span>Timestamp:</span>
                          <span className="font-mono text-muted-soft text-[11px]">
                            {new Date(record.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-hairline flex items-center justify-between">
                      <span className="text-[11px] text-muted-soft">Frame #{record.frame_number}</span>
                      <a
                        href={cropUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-primary font-medium hover:underline flex items-center gap-1"
                      >
                        <span>Inspect Crop</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Watchlist Manager */}
        <div className="lg:col-span-4 space-y-6">
          <div className="p-6 rounded-xl bg-surface-card border border-hairline space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-primary" />
                <h3 className="font-serif text-xl font-normal text-ink">
                  Security Watchlist
                </h3>
              </div>
              <span className="text-xs font-mono text-muted">{watchlist.length} plates</span>
            </div>

            <p className="text-xs text-muted leading-relaxed">
              Plates on this list trigger instant CRITICAL priority alerts when detected crossing any border virtual fence.
            </p>

            {/* Add to Watchlist Form */}
            <form onSubmit={addWatchlistPlate} className="flex gap-2">
              <input
                type="text"
                placeholder="e.g. MH12AB1234"
                value={newWatchlistPlate}
                onChange={(e) => setNewWatchlistPlate(e.target.value)}
                className="flex-1 px-3 py-2 rounded-md bg-canvas border border-hairline text-xs font-mono uppercase text-ink focus:outline-none focus:border-primary"
              />
              <button
                type="submit"
                className="px-3 py-2 rounded-md bg-primary hover:bg-primary-active text-on-primary text-xs font-medium flex items-center gap-1 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add</span>
              </button>
            </form>

            {/* Watchlist Items */}
            <div className="space-y-2 pt-2">
              {watchlist.map((plate) => (
                <div
                  key={plate}
                  className="p-2.5 rounded-md bg-canvas border border-hairline flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2 font-mono font-bold text-ink">
                    <span className="w-2 h-2 rounded-full bg-error" />
                    <span>{plate}</span>
                  </div>
                  <button
                    onClick={() => removeWatchlistPlate(plate)}
                    className="text-muted hover:text-error transition-colors p-1"
                    title="Remove from watchlist"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* OCR Specs */}
          <div className="p-6 rounded-xl bg-surface-dark text-on-dark border border-surface-dark-elevated space-y-3 font-mono text-xs">
            <h4 className="font-serif text-lg font-normal text-on-dark mb-2">
              OCR Normalization Specs
            </h4>
            <div className="space-y-1.5 text-on-dark-soft text-[11.5px]">
              <p>• <strong>Pattern:</strong> <code className="text-primary">^[A-Z]{`{2}`}[0-9]{`{2}`}[A-Z]{`{0,2}`}[0-9]{`{4}`}$</code></p>
              <p>• <strong>Confusion Mapping:</strong> O ↔ 0, I ↔ 1, Z ↔ 2</p>
              <p>• <strong>Contrast:</strong> Adaptive CLAHE + Deskew</p>
              <p>• <strong>Worker Queue:</strong> Bounded Non-blocking Thread</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
