import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          DEFAULT: "#0A0C10",
          panel: "#12151C",
          panel2: "#171B24",
          border: "#1F2430",
        },
        ink: {
          DEFAULT: "#E6E8EB",
          muted: "#8B93A7",
          faint: "#5B6274",
        },
        signal: {
          conviction: "#22C55E",
          early: "#3B82F6",
          watch: "#F59E0B",
          avoid: "#6B7280",
          danger: "#EF4444",
        },
      },
      fontFamily: {
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
      },
      borderRadius: {
        DEFAULT: "6px",
      },
    },
  },
  plugins: [],
};
export default config;
