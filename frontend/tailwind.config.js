/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1f2937",
        muted: "#6b7280",
        // Airbnb-ish warm coral as the primary action, with a deep teal accent
        // for secondary moments (focus, selection, links). Both stay AA-legible
        // on white.
        brand: {
          DEFAULT: "#e11d48",
          50: "#fff1f3",
          100: "#ffe0e6",
          500: "#e11d48",
          600: "#be123c",
          700: "#9f1239",
        },
        accent: {
          DEFAULT: "#0f766e",
          50: "#f0fdfa",
          500: "#0f766e",
          600: "#115e59",
        },
        surface: "#fafaf9",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        display: [
          "Fraunces",
          "ui-serif",
          "Georgia",
          "Cambria",
          "Times New Roman",
          "serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.04)",
        pop: "0 10px 30px rgba(15, 23, 42, 0.12)",
      },
      borderRadius: {
        "4xl": "2rem",
      },
    },
  },
  plugins: [],
};
