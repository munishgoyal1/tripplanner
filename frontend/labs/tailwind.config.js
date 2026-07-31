import baseConfig from "../tailwind.config.js";

export default {
  ...baseConfig,
  content: ["./src/**/*.{ts,tsx}", "./labs/**/*.{html,ts,tsx}"],
};