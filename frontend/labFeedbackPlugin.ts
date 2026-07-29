import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { Plugin } from "vite";

const endpoint = "/__labs/selections";
const feedbackPath = resolve(__dirname, "../docs/ux-experiments/LAB_SELECTIONS.local.json");

interface LabSelection {
  labId: string;
  labTitle: string;
  selection: string;
  selectionLabel: string;
  comment: string;
  updatedAt: string;
}

async function readSelections(): Promise<Record<string, LabSelection>> {
  try {
    return JSON.parse(await readFile(feedbackPath, "utf8")) as Record<string, LabSelection>;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {};
    throw error;
  }
}

function sendJson(response: import("node:http").ServerResponse, status: number, body: unknown) {
  response.statusCode = status;
  response.setHeader("Content-Type", "application/json");
  response.end(JSON.stringify(body));
}

export function labFeedbackPlugin(): Plugin {
  return {
    name: "tripplanner-lab-feedback",
    configureServer(server) {
      server.middlewares.use(endpoint, async (request, response) => {
        try {
          if (request.method === "GET") {
            sendJson(response, 200, await readSelections());
            return;
          }
          if (request.method !== "PUT") {
            sendJson(response, 405, { error: "Method not allowed" });
            return;
          }

          const chunks: Buffer[] = [];
          let size = 0;
          for await (const chunk of request) {
            const buffer = Buffer.from(chunk);
            size += buffer.length;
            if (size > 32_768) {
              sendJson(response, 413, { error: "Feedback is too large" });
              return;
            }
            chunks.push(buffer);
          }
          const selection = JSON.parse(Buffer.concat(chunks).toString("utf8")) as LabSelection;
          if (!selection.labId || !selection.labTitle || !selection.selection || !selection.selectionLabel) {
            sendJson(response, 400, { error: "Incomplete lab selection" });
            return;
          }

          const selections = await readSelections();
          selections[selection.labId] = { ...selection, updatedAt: new Date().toISOString() };
          await mkdir(dirname(feedbackPath), { recursive: true });
          await writeFile(feedbackPath, `${JSON.stringify(selections, null, 2)}\n`, "utf8");
          sendJson(response, 200, selections[selection.labId]);
        } catch (error) {
          server.config.logger.error(`Unable to save lab feedback: ${String(error)}`);
          sendJson(response, 500, { error: "Unable to save lab feedback" });
        }
      });
    },
  };
}