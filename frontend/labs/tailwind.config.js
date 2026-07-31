import baseConfig from "../tailwind.config.js";

export default {
  ...baseConfig,
  content: ["./labs/**/*.html", "./labs/src/**/*.{ts,tsx}"],
};
