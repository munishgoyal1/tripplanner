import { useEffect, useState } from "react";
import type { LabSelectionState } from "./labRecords";

type SelectionLoadStatus = "loading" | "loaded" | "error";

export function useLabSelections(): {
  selections: Record<string, LabSelectionState>;
  status: SelectionLoadStatus;
} {
  const [selections, setSelections] = useState<Record<string, LabSelectionState>>({});
  const [status, setStatus] = useState<SelectionLoadStatus>("loading");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/__labs/selections", { cache: "no-store", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Unable to load Lab decisions");
        return response.json() as Promise<Record<string, LabSelectionState>>;
      })
      .then((saved) => {
        setSelections(saved);
        setStatus("loaded");
      })
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") setStatus("error");
      });
    return () => controller.abort();
  }, []);

  return { selections, status };
}