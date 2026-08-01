import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { labFeedbackPlugin } from "./feedback-plugin";

export default defineConfig({
  root: __dirname,
  plugins: [react(), labFeedbackPlugin()],
  css: {
    postcss: __dirname,
  },
  server: {
    host: "127.0.0.1",
    port: Number(process.env.VITE_LABS_PORT || 5175),
    strictPort: true,
    hmr: process.env.VITE_HMR === "1",
  },
  preview: {
    host: "127.0.0.1",
    port: 4175,
    strictPort: true,
  },
  build: {
    emptyOutDir: true,
    outDir: "dist",
    rollupOptions: {
      input: {
        accountSettings: resolve(__dirname, "account-settings.html"),
        catalog: resolve(__dirname, "catalog.html"),
        chatAssistant: resolve(__dirname, "chat-assistant.html"),
        completedLabs: resolve(__dirname, "completed-labs.html"),
        destinationGuide: resolve(__dirname, "destination-guide.html"),
        intercityMap: resolve(__dirname, "intercity-map.html"),
        itineraryDensity: resolve(__dirname, "itinerary-density.html"),
        itineraryInformation: resolve(__dirname, "itinerary-information.html"),
        itinerarySummary: resolve(__dirname, "itinerary-summary.html"),
        itineraryTripBook: resolve(__dirname, "itinerary-trip-book.html"),
        mapControls: resolve(__dirname, "map-controls.html"),
        multiCityItinerary: resolve(__dirname, "multi-city-itinerary.html"),
        paneControls: resolve(__dirname, "pane-controls.html"),
        shellVisualRefresh: resolve(__dirname, "shell-visual-refresh.html"),
        tripSnapshot: resolve(__dirname, "trip-snapshot.html"),
        workspaceCommandBar: resolve(__dirname, "workspace-command-bar.html"),
        workspaceShell: resolve(__dirname, "workspace-shell.html"),
      },
    },
  },
});