import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const repoRoot = resolve(__dirname, "..", "..");

// The report is generated into the repo's corpus/ directory, outside this app's
// root. Serving it live rather than copying keeps the inspector honest: it can
// never show a report older than the last audit run.
function auditReportPlugin(): Plugin {
  const serve: Plugin["configureServer"] = (server) => {
    server.middlewares.use((req, res, next) => {
      if ((req.url ?? "").split("?")[0] !== "/audit-report.json") return next();
      try {
        const body = readFileSync(resolve(repoRoot, "corpus", "audit-report.json"));
        res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-cache" });
        res.end(body);
      } catch {
        res.writeHead(404, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "no-report" }));
      }
    });
  };
  return { name: "audit-report", configureServer: serve };
}

export default defineConfig({
  root: __dirname,
  plugins: [react(), auditReportPlugin()],
  server: {
    host: "127.0.0.1",
    port: Number(process.env.VITE_INSPECTOR_PORT || 5177),
    strictPort: true,
    hmr: process.env.VITE_HMR === "1",
  },
  build: {
    emptyOutDir: true,
    outDir: "dist",
    rollupOptions: { input: { inspector: resolve(__dirname, "index.html") } },
  },
});
