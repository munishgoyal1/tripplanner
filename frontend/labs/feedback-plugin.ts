import type { Plugin } from "vite";
import {
  readSelections,
  withSelectionStoreLock,
  writeSelections,
  type HandoffRecord,
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
      : [];

  if (
    !["implemented-review", "completed"].includes(selection.disposition || "")
    || ["implemented-review", "completed"].includes(previous?.disposition || "")
    || !selection.implementationSummary?.trim()
  ) {
    return history;
  }

  const implemented: ImplementationRecord = {
    version: Math.max(0, ...history.map((record) => record.version)) + 1,
    handoffVersion: Math.max(0, ...(selection.handoffs || []).map((handoff) => handoff.version)) || undefined,
    selection: selection.selection,
    selectionLabel: selection.selectionLabel,
    comment: selection.comment,
    summary: selection.implementationSummary,
    recordedAt: updatedAt,
  };
  return [...history, implemented];
}

export function buildHandoffHistory(
  previous: LabSelection | undefined,
  selection: LabSelection,
  updatedAt: string,
): HandoffRecord[] {
  const history = previous?.handoffs?.length
    ? previous.handoffs
    : previous?.selection
      ? [{
          version: 1,
          selection: previous.selection,
          selectionLabel: previous.selectionLabel,
          comment: previous.comment,
          disposition: previous.disposition || "ready" as const,
          recordedAt: previous.updatedAt,
        }]
      : [];
  return [...history, {
    version: Math.max(0, ...history.map((handoff) => handoff.version)) + 1,
    selection: selection.selection,
    selectionLabel: selection.selectionLabel,
    comment: selection.comment,
    disposition: selection.disposition || "ready",
    recordedAt: updatedAt,
  }];
}

export function labFeedbackPlugin(): Plugin {
  return {
    name: "tripplanner-lab-feedback",
    configureServer(server) {
      server.middlewares.use(endpoint, async (request, response) => {
        try {
          if (request.method === "GET") {
            sendJson(response, 200, await withSelectionStoreLock(() => readSelections()));
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
          if (selection.disposition && !["ready", "implemented-review", "parked", "completed", "discarded"].includes(selection.disposition)) {
            sendJson(response, 400, { error: "Invalid lab disposition" });
            return;
          }

          const savedSelection = await withSelectionStoreLock(async () => {
            const selections = await readSelections();
            const previous = selections[selection.labId];
            const entersImplementedState = ["implemented-review", "completed"].includes(selection.disposition || "")
              && !["implemented-review", "completed"].includes(previous?.disposition || "");
            if (entersImplementedState && !selection.implementationSummary?.trim()) {
              throw new Error("Implementation evidence is required when entering an implemented state.");
            }
            const updatedAt = new Date().toISOString();
            const stateChangedAt = previous?.disposition === selection.disposition
              ? previous.stateChangedAt || previous.updatedAt
              : updatedAt;
            const handoffs = buildHandoffHistory(previous, selection, updatedAt);
            const selectionWithHandoffs = { ...selection, handoffs };
            const implementations = buildImplementationHistory(previous, selectionWithHandoffs, updatedAt);
            const latestImplementation = implementations[implementations.length - 1];
            const implementation = latestImplementation
              ? {
                  selection: latestImplementation.selection,
                  selectionLabel: latestImplementation.selectionLabel,
                  comment: latestImplementation.comment,
                  summary: latestImplementation.summary,
                  handoffVersion: latestImplementation.handoffVersion,
                  recordedAt: latestImplementation.recordedAt,
                }
              : undefined;
            selections[selection.labId] = {
              ...selection,
              handoffs,
              implementation,
              implementations,
              stateChangedAt,
              updatedAt,
            };
            await writeSelections(selections);
            return selections[selection.labId];
          });
          sendJson(response, 200, savedSelection);
        } catch (error) {
          server.config.logger.error(`Unable to save lab feedback: ${String(error)}`);
          sendJson(response, 500, { error: "Unable to save lab feedback" });
        }
      });
    },
  };
}