import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./hooks/**/*.{js,ts,jsx,tsx}",
    "./lib/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        bg:       "rgb(var(--c-bg) / <alpha-value>)",
        surface:  "rgb(var(--c-surface) / <alpha-value>)",
        elevated: "rgb(var(--c-elevated) / <alpha-value>)",
        border:   "rgb(var(--c-border) / <alpha-value>)",
        tx:       "rgb(var(--c-text) / <alpha-value>)",
        "tx-2":   "rgb(var(--c-text2) / <alpha-value>)",
        "tx-3":   "rgb(var(--c-text3) / <alpha-value>)",
        accent:       "#6366f1",
        "accent-h":   "#818cf8",
        income:   "#10b981",
        expense:  "#f43f5e",
        savings:  "#3b82f6",
        warn:     "#f59e0b",
      },
      animation: {
        "fade-in":    "fadeIn 0.2s ease-out forwards",
        "slide-up":   "slideUp 0.25s ease-out forwards",
        "slide-right":"slideRight 0.3s ease-out forwards",
        "bounce-dot": "bounceDot 1.2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn:  { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp: {
          "0%":   { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideRight: {
          "0%":   { opacity: "0", transform: "translateX(100%)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        bounceDot: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%":      { transform: "translateY(-4px)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
