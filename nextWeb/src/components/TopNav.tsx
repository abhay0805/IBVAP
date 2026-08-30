"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Shield, Radio, Activity, Eye, Sliders, Play, Camera } from "lucide-react";
import { SystemStats } from "@/lib/types";

export function TopNav() {
  const pathname = usePathname();
  const [stats, setStats] = useState<SystemStats | null>(null);

  useEffect(() => {
    async function fetchNavStats() {
      try {
        const res = await fetch("/api/stats");
        if (res.ok) {
          const data = await res.json();
          setStats(data);
        }
      } catch (err) {
        console.error("Error fetching nav stats:", err);
      }
    }
    fetchNavStats();
    const interval = setInterval(fetchNavStats, 4000);
    return () => clearInterval(interval);
  }, []);

  const activeCamId = stats?.activeCameraId || "BOP-CAM-01";

  const navItems = [
    { name: "Live Operations", href: "/", icon: Activity },
    { name: "Incidents", href: "/events", icon: Shield },
    { name: "ANPR Recon", href: "/anpr", icon: Eye },
    { name: "Virtual Fence", href: "/lab", icon: Sliders },
    { name: "Settings", href: "/config", icon: Radio },
  ];

  return (
    <header className="sticky top-0 z-50 h-14 bg-white border-b border-zinc-200 px-4 md:px-8 flex items-center justify-between font-sans">
      {/* Brand Title */}
      <div className="flex items-center gap-8">
        <Link href="/" className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-zinc-900" />
          <span className="font-bold text-base text-zinc-900 tracking-tight">IBVAP</span>
          <span className="text-xs text-zinc-400 font-normal">v2.6</span>
        </Link>

        {/* Minimal Navigation */}
        <nav className="hidden lg:flex items-center gap-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  isActive
                    ? "bg-zinc-100 text-zinc-900 font-semibold"
                    : "text-zinc-500 hover:text-zinc-900 hover:bg-zinc-50"
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? "text-zinc-900" : "text-zinc-400"}`} />
                {item.name}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-3">
        {/* Simple Camera Status */}
        <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 bg-zinc-50 border border-zinc-200 rounded-md text-xs">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          <span className="text-zinc-700 text-[11px] font-medium">
            {activeCamId} Active
          </span>
        </div>

        {/* Simple Black Button */}
        <Link
          href="/lab"
          className="flex items-center gap-1.5 px-3.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-white text-xs font-medium rounded-md transition-all shadow-sm active:scale-[0.98]"
        >
          <Play className="w-3.5 h-3.5 fill-current" />
          <span>Trigger Scan</span>
        </Link>
      </div>
    </header>
  );
}
