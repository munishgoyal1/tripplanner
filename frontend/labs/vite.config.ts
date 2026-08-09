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
        accountSettings: resolve(__dirname, "lab-12-account-settings.html"),
        agenticPlanning: resolve(__dirname, "lab-19-agentic-planning.html"),
        catalog: resolve(__dirname, "catalog.html"),
        chatAgentWorkspace: resolve(__dirname, "lab-16-chat-agent-workspace.html"),
        chatAssistant: resolve(__dirname, "lab-4-chat-assistant.html"),
        completedLabs: resolve(__dirname, "completed-labs.html"),
        destinationGuide: resolve(__dirname, "lab-13-destination-guide.html"),
        firstVisit: resolve(__dirname, "lab-21-first-visit.html"),
        intercityMap: resolve(__dirname, "lab-14-intercity-map.html"),
        livePlan: resolve(__dirname, "lab-22-live-plan.html"),
        itineraryCanvas: resolve(__dirname, "lab-17-itinerary-canvas.html"),
        itineraryDensity: resolve(__dirname, "lab-11-itinerary-density.html"),
        itineraryInformation: resolve(__dirname, "lab-2-itinerary-information.html"),
        itinerarySummary: resolve(__dirname, "lab-3-itinerary-summary.html"),
        itineraryTripBook: resolve(__dirname, "lab-5-itinerary-trip-book.html"),
        localization: resolve(__dirname, "lab-24-localization.html"),
        mapCanvas: resolve(__dirname, "lab-18-map-canvas.html"),
        mapControls: resolve(__dirname, "lab-8-map-controls.html"),
        multiCityItinerary: resolve(__dirname, "lab-15-multi-city-itinerary.html"),
        paneControls: resolve(__dirname, "lab-10-pane-controls.html"),
        productThemes: resolve(__dirname, "lab-23-product-themes.html"),
        shellVisualRefresh: resolve(__dirname, "lab-9-shell-visual-refresh.html"),
        travelDocuments: resolve(__dirname, "lab-20-travel-documents.html"),
        tripSnapshot: resolve(__dirname, "lab-6-trip-snapshot.html"),
        workspaceCommandBar: resolve(__dirname, "lab-7-workspace-command-bar.html"),
        workspaceShell: resolve(__dirname, "lab-1-workspace-shell.html"),
      },
    },
  },
});