import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    emptyOutDir: true,
    outDir: "labs/dist",
    rollupOptions: {
      input: {
        catalog: resolve(__dirname, "catalog.html"),
        chatAssistant: resolve(__dirname, "chat-assistant.html"),
        itineraryDensity: resolve(__dirname, "itinerary-density.html"),
        itineraryInformation: resolve(__dirname, "itinerary-information.html"),
        itinerarySummary: resolve(__dirname, "itinerary-summary.html"),
        workspaceShell: resolve(__dirname, "workspace-shell.html"),
      },
    },
  },
});