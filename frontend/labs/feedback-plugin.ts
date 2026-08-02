import type { Plugin } from "vite";
import {
  readSelections,
  writeSelections,
  type ImplementationRecord,
  type LabSelection,
} from "./lab-selection-store";

const endpoint = "/__labs/selections";

function sendJson(response: import("node:http").ServerResponse, status: number, body: unknown) {
  response.statusCode = status;
  response.setHeader("Content-Type", "application/json");
  response.setHeader("Cache-Control", "no-store");
  response.end(JSON.stringify(body));
}

export function buildImplementationHistory(
  previous: LabSelection | undefined,
  selection: LabSelection,
  updatedAt: string,
): ImplementationRecord[] {
  const history = previous?.implementations?.length
    ? previous.implementations
    : previous?.implementation
      ? [{ ...previous.implementation, version: 1 }]
      : previous?.selection && ["implemented-review", "completed"].includes(previous.disposition || "")
        ? [{
            version: 1,
            selection: previous.selection,
            selectionLabel: previous.selectionLabel,
            comment: previous.comment,
            recordedAt: previous.updatedAt,
          }]
        : [];

  if (selection.disposition !== "implemented-review") return history;

  const implemented: ImplementationRecord = {
    version: previous?.disposition === "implemented-review" && history.length
      ? history[history.length - 1].version
      : history.length + 1,
    selection: selection.selection,
    selectionLabel: selection.selectionLabel,
    comment: selection.comment,
    recordedAt: updatedAt,
  };
  return previous?.disposition === "implemented-review" && history.length
    ? [...history.slice(0, -1), implemented]
    : [...history, implemented];
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
          if (!selection.labId || !selection.labTitle || selection.disposition !== "discarded" && (!selection.selection || !selection.selectionLabel)) {
            sendJson(response, 400, { error: "Incomplete lab selection" });
            return;
          }
          if (selection.disposition && !["ready", "implemented-review", "parked", "completed", "discarded"].includes(selection.disposition)) {
            sendJson(response, 400, { error: "Invalid lab disposition" });
            return;
          }

          const selections = await readSelections();
          const previous = selections[selection.labId];
          const updatedAt = new Date().toISOString();
          const stateChangedAt = previous?.disposition === selection.disposition
            ? previous.stateChangedAt || previous.updatedAt
            : updatedAt;
          const implementations = buildImplementationHistory(previous, selection, updatedAt);
          const latestImplementation = implementations[implementations.length - 1];
          const implementation = latestImplementation
            ? {
                selection: latestImplementation.selection,
                selectionLabel: latestImplementation.selectionLabel,
                comment: latestImplementation.comment,
                recordedAt: latestImplementation.recordedAt,
              }
            : undefined;
          selections[selection.labId] = selection.disposition === "discarded"
            ? {
                labId: selection.labId,
                labTitle: selection.labTitle,
                selection: "",
                selectionLabel: "",
                comment: "",
                disposition: "discarded",
                stateChangedAt,
                updatedAt,
              }
            : { ...selection, implementation, implementations, stateChangedAt, updatedAt };
          await writeSelections(selections);
          sendJson(response, 200, selections[selection.labId]);
        } catch (error) {
          server.config.logger.error(`Unable to save lab feedback: ${String(error)}`);
          sendJson(response, 500, { error: "Unable to save lab feedback" });
        }
      });
    },
  };
}