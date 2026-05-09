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
        // Tier 1 uses system fonts; Tier 2 swaps in Fraunces / Inter Tight / Amiri.
        sans: [
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: ["ui-monospace", "Cascadia Mono", "Consolas", "monospace"],
        serif: ["Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
