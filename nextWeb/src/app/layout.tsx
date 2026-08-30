import type { Metadata } from "next";
import "./globals.css";
import { TopNav } from "@/components/TopNav";

export const metadata: Metadata = {
  title: "IBVAP — Integrated Border Video Analytics Platform",
  description: "AI-powered perimeter defense, virtual tripwire detection, and automatic license plate recognition.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="bg-canvas">
      <body className="min-h-screen bg-canvas text-ink antialiased flex flex-col selection:bg-primary/20 selection:text-ink">
        <TopNav />
        <main className="flex-1 max-w-[1400px] w-full mx-auto px-4 md:px-8 py-8">
          {children}
        </main>
        <footer className="bg-surface-dark text-on-dark-soft py-12 border-t border-surface-dark-elevated mt-16">
          <div className="max-w-[1400px] mx-auto px-4 md:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="font-serif text-lg text-on-dark font-normal">IBVAP</span>
              <span className="text-xs text-on-dark-soft">· Border Watchtower Defense Platform</span>
            </div>
            <p className="text-xs text-on-dark-soft">
              Computer Vision & ANPR Engine v2.6 · Verified End-to-End
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
