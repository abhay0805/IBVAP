import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Ultra-Simplistic & Clean Theme Tokens (Vercel / Linear inspired)
        canvas: "#FAFAFA",            // Clean Off-White Canvas
        "surface-card": "#FFFFFF",     // Pure White Card
        "surface-soft": "#F4F4F5",     // Soft Gray Floor
        "surface-dark": "#09090B",     // Pure Dark Surface for Video
        hairline: "#E4E4E7",           // Subtle 1px Border
        "hairline-soft": "#F4F4F5",

        // Accents
        primary: {
          DEFAULT: "#18181B",          // Charcoal Black CTA
          active: "#27272A",
          disabled: "#E4E4E7",
        },
        accent: {
          coral: "#CC785C",
          blue: "#2563EB",
          emerald: "#10B981",
          amber: "#F59E0B",
          red: "#EF4444",
        },

        // Text Colors
        ink: "#09090B",                // Deep Charcoal Ink
        body: "#52525B",               // Muted Body Text
        muted: "#71717A",              // Captions & Metadata
        "muted-soft": "#A1A1AA",
        "on-primary": "#FFFFFF",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "'Segoe UI'", "Roboto", "sans-serif"],
        mono: ["'JetBrains Mono'", "Consolas", "monospace"],
      },
      borderRadius: {
        xs: "4px",
        sm: "6px",
        md: "8px",
        lg: "12px",
        xl: "16px",
        pill: "9999px",
      },
    },
  },
  plugins: [],
};
export default config;
