import React from "react";
import { LucideIcon } from "lucide-react";

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  trend?: string;
  highlight?: boolean;
  coralAccent?: boolean;
}

export function MetricCard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
}: MetricCardProps) {
  return (
    <div className="p-5 bg-white border border-zinc-200 rounded-xl shadow-sm hover:border-zinc-300 transition-all">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-zinc-500">
          {title}
        </span>
        <div className="p-1.5 bg-zinc-50 border border-zinc-200 rounded-md text-zinc-600">
          <Icon className="w-4 h-4" />
        </div>
      </div>

      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold text-zinc-900 tracking-tight">
          {value}
        </span>
        {trend && (
          <span className="text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
            {trend}
          </span>
        )}
      </div>

      {subtitle && (
        <p className="mt-2 text-xs text-zinc-500 font-normal">
          {subtitle}
        </p>
      )}
    </div>
  );
}
