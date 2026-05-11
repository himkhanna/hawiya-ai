/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brand palette per demo-ui.md §4.
        ink: "#0A0E1A",
        paper: "#F5F1EA",
        crimson: "#8B1E2D",
        gold: "#B8954A",
        teal: "#2D5F5D",
      },
      fontFamily: {
        // Brand fonts per demo-ui.md §4 (self-hosted via @fontsource).
        sans: ['"Inter Tight"', "system-ui", "sans-serif"],
        serif: ['"Fraunces"', "Georgia", "serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
        arabic: ['"Amiri"', '"Times New Roman"', "serif"],
      },
    },
  },
  plugins: [],
};
