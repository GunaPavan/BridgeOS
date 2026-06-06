import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Bridge OS brand palette — dark navy + coral/teal accents
        background: "#0A0F1E",
        surface: "#111827",
        primary: {
          DEFAULT: "#FF6B6B",
          50: "#FFEEEE",
          100: "#FFD9D9",
          500: "#FF6B6B",
          600: "#E85555",
          700: "#C03F3F",
        },
        accent: {
          DEFAULT: "#4ECDC4",
          500: "#4ECDC4",
          600: "#3BB8B0",
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
