"use client";

import React, { useEffect, useRef } from "react";
import { Terminal, Copy, Check, Trash2 } from "lucide-react";

interface TerminalConsoleProps {
  logs: string[];
  isRunning?: boolean;
  onClear?: () => void;
  title?: string;
}

export function TerminalConsole({
  logs,
  isRunning = false,
  onClear,
  title = "RAW // AI SUBPROCESS INFERENCE LOG",
}: TerminalConsoleProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = React.useState(false);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const copyLogs = () => {
    navigator.clipboard.writeText(logs.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-[#020408] border border-[#1E293B] overflow-hidden flex flex-col font-mono text-xs text-white">
      {/* Console Header */}
      <div className="px-4 py-3 bg-[#0A0F1D] border-b border-[#1E293B] flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Terminal className="w-3.5 h-3.5 text-[#00E5FF]" />
          <span className="font-extrabold text-[11px] uppercase tracking-widest text-[#00E5FF]">{title}</span>
          {isRunning && (
            <span className="flex items-center gap-1.5 px-2 py-0.5 bg-[#00E676] text-black text-[10px] font-bold uppercase animate-pulse">
              <span className="w-1.5 h-1.5 bg-black" />
              INFERENCE RUNNING
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={copyLogs}
            className="p-1 hover:text-[#00E5FF] text-[#94A3B8] transition-colors flex items-center gap-1 text-[11px]"
            title="Copy logs"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-[#00E676]" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
          {onClear && (
            <button
              onClick={onClear}
              className="p-1 hover:text-[#FF1744] text-[#94A3B8] transition-colors"
              title="Clear console"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Output Console */}
      <div
        ref={scrollRef}
        className="bg-[#020408] p-4 h-[320px] overflow-y-auto space-y-1 font-mono text-[11.5px] leading-relaxed dark-scroll"
      >
        {logs.length === 0 ? (
          <div className="text-[#64748B] italic py-10 text-center uppercase tracking-wider text-xs">
            // AWAITING INFERENCE EXECUTION LOGS...
          </div>
        ) : (
          logs.map((line, idx) => {
            let lineClass = "text-[#94A3B8]";
            if (line.includes("EVENT") || line.includes("ALERT") || line.includes("BREACH")) {
              lineClass = "text-[#FF1744] font-bold";
            } else if (line.includes("ERROR") || line.includes("[ERR]")) {
              lineClass = "text-[#FF1744] font-bold";
            } else if (line.includes("OK") || line.includes("completed")) {
              lineClass = "text-[#00E676] font-bold";
            } else if (line.includes("INFO") || line.includes("Starting")) {
              lineClass = "text-[#00E5FF]";
            }
            return (
              <div key={idx} className="flex items-start gap-3">
                <span className="text-[#334155] select-none w-6 text-right font-mono text-[10px]">
                  {idx + 1}
                </span>
                <span className={`flex-1 break-all ${lineClass}`}>{line}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
