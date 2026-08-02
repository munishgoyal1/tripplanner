import { useEffect, useState } from "react";
import type { LabSelectionState } from "./labRecords";

type SelectionLoadStatus = "loading" | "loaded" | "error";
export const LAB_SELECTION_SAVED_EVENT = "tripplanner:lab-selection-saved";

interface LabSelectionSavedDetail {
  labId: string;
  selection: LabSelectionState;
}

export function useLabSelections(): {
  selections: Record<string, LabSelectionState>;
  status: SelectionLoadStatus;
} {
  const [selections, setSelections] = useState<Record<string, LabSelectionState>>({});
  const [status, setStatus] = useState<SelectionLoadStatus>("loading");

  useEffect(() => {
    const controller = new AbortController();
    const handleSaved = (event: Event) => {
      const { labId, selection } = (event as CustomEvent<LabSelectionSavedDetail>).detail;
      setSelections((current) => ({ ...current, [labId]: selection }));
      setStatus("loaded");
    };
    window.addEventListener(LAB_SELECTION_SAVED_EVENT, handleSaved);
    fetch("/__labs/selections", { cache: "no-store", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Unable to load Lab decisions");
        return response.json() as Promise<Record<string, LabSelectionState>>;
      })
      .then((saved) => {
        setSelections((current) => ({ ...saved, ...current }));
        setStatus("loaded");
      })
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") {
          setStatus((current) => current === "loaded" ? current : "error");
        }
      });
    return () => {
      controller.abort();
      window.removeEventListener(LAB_SELECTION_SAVED_EVENT, handleSaved);
    };
  }, []);

  return { selections, status };
}