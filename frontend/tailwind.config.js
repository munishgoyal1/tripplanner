const token = (name) => `oklch(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: token("background"),
        foreground: token("foreground"),
        card: token("card"),
        paper: token("paper"),
        sand: token("sand"),
        clay: token("clay"),
        "clay-soft": token("clay-soft"),
        sage: token("sage"),
        "sage-soft": token("sage-soft"),
        ochre: token("ochre"),
        border: token("border"),
        sidebar: token("sidebar"),
        ink: token("ink"),
        muted: token("muted-foreground"),
        brand: {
          DEFAULT: token("primary"),
          50: token("clay-soft"),
          100: token("clay-soft"),
          500: token("primary"),
          600: token("primary-strong"),
          700: token("primary-strong"),
        },
        accent: {
          DEFAULT: token("sage"),
          50: token("sage-soft"),
          500: token("sage"),
          600: token("sage-strong"),
        },
        surface: token("sand"),
      },
      fontFamily: {
        sans: [
          "Work Sans",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        display: [
          "Instrument Serif",
          "ui-serif",
          "Georgia",
          "Cambria",
          "Times New Roman",
          "serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px oklch(0.28 0.05 45 / 0.06), 0 8px 24px -12px oklch(0.28 0.05 45 / 0.18)",
        pop: "0 2px 4px oklch(0.28 0.05 45 / 0.06), 0 18px 40px -18px oklch(0.28 0.05 45 / 0.28)",
      },
      borderRadius: {
        "4xl": "2rem",
      },
    },
  },
  plugins: [],
};
