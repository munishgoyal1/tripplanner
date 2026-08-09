/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#10324a",
        muted: "#557687",
        brand: {
          DEFAULT: "#d63c75",
          50: "#fff2f7",
          100: "#fce1eb",
          500: "#d63c75",
          600: "#b92d62",
          700: "#96244f",
        },
        accent: {
          DEFAULT: "#0877b9",
          50: "#eef9fc",
          500: "#0877b9",
          600: "#07649b",
        },
        surface: "#f7fbfa",
      },
      fontFamily: {
        sans: [
          "Space Grotesk",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        display: [
          "Newsreader",
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
