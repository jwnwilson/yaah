import type { Config } from "tailwindcss";

const token = (name: string) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: token("--canvas"),
        panel: token("--panel"),
        surface: { DEFAULT: token("--surface"), hover: token("--surface-hover") },
        fg: token("--fg"),
        muted: token("--muted"),
        subtle: token("--subtle"),
        line: { DEFAULT: token("--line"), strong: token("--line-strong") },
        accent: { DEFAULT: token("--accent"), fg: token("--accent-fg"), subtle: token("--accent-subtle") },
        success: { DEFAULT: token("--success"), subtle: token("--success-subtle") },
        warning: { DEFAULT: token("--warning"), subtle: token("--warning-subtle") },
        danger: { DEFAULT: token("--danger"), subtle: token("--danger-subtle"), fg: token("--danger-fg") },
        info: { DEFAULT: token("--info"), subtle: token("--info-subtle") },
      },
      fontFamily: {
        sans: ["InterVariable", "Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
