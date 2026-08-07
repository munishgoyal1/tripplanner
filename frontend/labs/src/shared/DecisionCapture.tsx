import { Check, CheckCircle2, Save } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { LAB_SELECTION_SAVED_EVENT } from "./useLabSelections";

interface DecisionOption {
  id: string;
  label: string;
}

interface SavedSelection {
  selection: string;
  selectionLabel?: string;
  comment: string;
  disposition?: LabDisposition;
  handoffs?: HandoffRecord[];
  implementationSummary?: string;
  implementation?: ImplementationRecord;
  implementations?: ImplementationRecord[];
  stateChangedAt?: string;
  updatedAt?: string;
}

interface ImplementationRecord {
  version?: number;
  selection: string;
  selectionLabel: string;
  comment: string;
  handoffVersion?: number;
  summary?: string;
  recordedAt: string;
}

interface HandoffRecord {
  version: number;
  selection: string;
  selectionLabel: string;
  comment: string;
  disposition: LabDisposition;
  recordedAt: string;
}

function handoffHistory(selection: SavedSelection, options: DecisionOption[]): HandoffRecord[] {
  if (selection.handoffs?.length) return [...selection.handoffs].sort((first, second) => second.version - first.version);
  if (!selection.selection) return [];
  return [{
    version: 1,
    selection: selection.selection,
    selectionLabel: selection.selectionLabel
      || options.find((option) => option.id === selection.selection)?.label
      || selection.selection,
    comment: selection.comment,
    disposition: selection.disposition || "ready",
    recordedAt: selection.updatedAt || new Date().toISOString(),
  }];
}

function implementationHistory(
  selection: SavedSelection,
): ImplementationRecord[] {
  if (selection.implementations?.length) return [...selection.implementations].sort((first, second) => (second.version || 0) - (first.version || 0));
  if (selection.implementation) return [{ ...selection.implementation, version: 1 }];
  return [];
}

type LabDisposition = "ready" | "implemented-review" | "parked" | "completed" | "discarded";

const LAB_STATES: { value: LabDisposition; label: string }[] = [
  { value: "ready", label: "In progress" },
  { value: "implemented-review", label: "Implemented - Review" },
  { value: "parked", label: "Parked" },
  { value: "completed", label: "Completed" },
  { value: "discarded", label: "Discarded" },
];

interface DecisionCaptureProps {
  labId: string;
  labTitle: string;
  options: DecisionOption[];
  activeOption: string;
  onChoose: (optionId: string) => void;
}

export function DecisionCapture({ labId, labTitle, options, activeOption, onChoose }: DecisionCaptureProps) {
  const draftKey = `tripplanner-ux-lab-handoff-${labId}`;
  const [comment, setComment] = useState("");
  const [saved, setSaved] = useState<SavedSelection | null>(null);
  const [implementations, setImplementations] = useState<ImplementationRecord[]>([]);
  const [handoffs, setHandoffs] = useState<HandoffRecord[]>([]);
  const [disposition, setDisposition] = useState<LabDisposition>("ready");
  const [status, setStatus] = useState<"loading" | "idle" | "saving" | "saved" | "offline">("loading");
  const onChooseRef = useRef(onChoose);
  const optionsRef = useRef(options);
  onChooseRef.current = onChoose;
  optionsRef.current = options;

  useEffect(() => {
    let localDraft: SavedSelection | null = null;
    try {
      localDraft = JSON.parse(localStorage.getItem(draftKey) || "null") as SavedSelection | null;
      if (localDraft) {
        setComment(localDraft.comment || "");
        setDisposition(localDraft.disposition || "ready");
        setHandoffs(handoffHistory(localDraft, optionsRef.current));
        setImplementations(implementationHistory(localDraft));
        onChooseRef.current(localDraft.selection);
      }
    } catch {
      localStorage.removeItem(draftKey);
    }

    const controller = new AbortController();
    fetch("/__labs/selections", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Unable to load saved selection");
        return response.json() as Promise<Record<string, SavedSelection>>;
      })
      .then((selections) => {
        const existing = selections[labId];
        if (existing) {
          setSaved(existing);
          setHandoffs(handoffHistory(existing, optionsRef.current));
          setImplementations(implementationHistory(existing));
          const draftIsNewer = Boolean(
            localDraft?.updatedAt
            && (!existing.updatedAt || localDraft.updatedAt > existing.updatedAt),
          );
          if (!draftIsNewer) {
            setComment(existing.comment || "");
            setDisposition(existing.disposition || "ready");
            if (existing.selection) onChooseRef.current(existing.selection);
          }
        }
        setStatus("idle");
      })
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") setStatus("offline");
      });
    return () => controller.abort();
  }, [draftKey, labId]);

  const selectedLabel = options.find((option) => option.id === activeOption)?.label || activeOption;
  const dirty = saved?.selection !== activeOption
    || saved?.comment !== comment
    || saved?.disposition !== disposition;
  const isReimplementation = implementations.length > 0;
  const showSaveConfirmation = status === "saved" && Boolean(saved) && !dirty;

  const keepDraft = (
    selection: string,
    nextComment: string,
    nextDisposition = disposition,
  ) => {
    localStorage.setItem(draftKey, JSON.stringify({
      selection,
      comment: nextComment,
      disposition: nextDisposition,
      handoffs,
      implementations,
      updatedAt: new Date().toISOString(),
    }));
  };

  const choose = (optionId: string) => {
    onChoose(optionId);
    keepDraft(optionId, comment);
  };

  const updateComment = (nextComment: string) => {
    setComment(nextComment);
    keepDraft(activeOption, nextComment);
  };

  const save = async () => {
    keepDraft(activeOption, comment, disposition);
    setStatus("saving");
    const controller = new AbortController();
    const saveTimeout = window.setTimeout(() => controller.abort(), 10_000);
    try {
      const response = await fetch("/__labs/selections", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          labId,
          labTitle,
          selection: activeOption,
          selectionLabel: selectedLabel,
          comment,
          disposition,
        }),
      });
      if (!response.ok) throw new Error("Unable to save selection");
      const savedSelection = await response.json() as SavedSelection;
      setSaved(savedSelection);
      setHandoffs(handoffHistory(savedSelection, optionsRef.current));
      setImplementations(implementationHistory(savedSelection));
      setStatus("saved");
      window.dispatchEvent(new CustomEvent(LAB_SELECTION_SAVED_EVENT, {
        detail: { labId, selection: savedSelection },
      }));
    } catch {
      setStatus("offline");
    } finally {
      window.clearTimeout(saveTimeout);
    }
  };

  return (
    <section className="rounded-md bg-white p-4 shadow-card ring-1 ring-slate-200" aria-labelledby={`${labId}-decision-title`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase text-brand">Your handoff</p>
          <h2 id={`${labId}-decision-title`} className="mt-0.5 text-base font-semibold text-ink">Choose a direction and set its next step</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">The chosen option, handoff notes, and Lab status stay together in the workspace record. Implementation is limited to the Change scope above unless your notes explicitly add another change.</p>
        </div>
        {saved && !dirty && (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-bold uppercase text-emerald-700 ring-1 ring-emerald-200"><Check size={11} aria-hidden /> Saved</span>
        )}
      </div>

      {implementations.length > 0 && (
        <div className="mt-4 rounded-md bg-sky-50 px-3 py-3 ring-1 ring-sky-200">
          <p className="text-[10px] font-bold uppercase text-sky-700">What was implemented</p>
          <div className="mt-2 grid gap-2">
            {implementations.map((implemented, index) => (
              <article key={`${implemented.version || index + 1}-${implemented.recordedAt}`} className="rounded-md bg-white px-3 py-2.5 ring-1 ring-sky-200">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-xs font-bold text-sky-800">Implementation {implemented.version || index + 1}</p>
                  <time className="text-[10px] text-slate-500" dateTime={implemented.recordedAt}>{new Date(implemented.recordedAt).toLocaleString()}</time>
                </div>
                <p className="mt-1 text-sm font-semibold text-ink">{implemented.selectionLabel}</p>
                {implemented.handoffVersion && <p className="mt-0.5 text-[10px] font-semibold text-slate-500">From handoff version {implemented.handoffVersion}</p>}
                <p className="mt-2 text-[10px] font-bold uppercase text-slate-500">Exact saved notes</p>
                <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-slate-700">{implemented.comment || "No implementation notes were saved."}</p>
                {implemented.summary && <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-700"><strong>Implemented:</strong> {implemented.summary}</p>}
              </article>
            ))}
          </div>
          <div className="mt-3 border-t border-sky-200 pt-3">
            <p className="text-[10px] font-bold uppercase text-sky-700">Final implementation summary</p>
            <p className="mt-1 text-xs leading-relaxed text-slate-700">
              {implementations.map((implemented, index) => {
                const notes = implemented.comment.trim().replace(/\s+/g, " ") || "No implementation notes were saved.";
                return `Version ${implemented.version || index + 1}: ${implemented.selectionLabel} - ${notes}`;
              }).join(" | ")}
            </p>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-600">Every option remains available to inspect and compare. Browsing another option does not change this history until that implementation reaches review.</p>
        </div>
      )}

      {handoffs.length > 0 && (
        <div className="mt-4 rounded-md bg-slate-50 px-3 py-3 ring-1 ring-slate-200">
          <p className="text-[10px] font-bold uppercase text-slate-600">Saved handoff history</p>
          <div className="mt-2 grid gap-2">
            {handoffs.map((handoff) => (
              <article key={`${handoff.version}-${handoff.recordedAt}`} className="rounded-md bg-white px-3 py-2 ring-1 ring-slate-200">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-xs font-bold text-ink">Handoff version {handoff.version}</p>
                  <time className="text-[10px] text-slate-500" dateTime={handoff.recordedAt}>{new Date(handoff.recordedAt).toLocaleString()}</time>
                </div>
                <p className="mt-1 text-sm font-semibold text-ink">{handoff.selectionLabel}</p>
                <p className="mt-0.5 text-[10px] font-bold uppercase text-slate-500">{handoff.disposition}</p>
                <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-slate-700">{handoff.comment || "No handoff notes were saved."}</p>
              </article>
            ))}
          </div>
        </div>
      )}

      <fieldset className="mt-4">
        <legend className="text-xs font-semibold text-slate-700">Preferred option</legend>
        <div className="mt-2 grid gap-2 sm:grid-cols-3">
          {options.map((option) => (
            <label key={option.id} className={`flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-xs font-medium ring-1 ${activeOption === option.id ? "bg-brand-50 text-brand ring-brand/30" : "bg-white text-slate-600 ring-slate-200 hover:ring-brand/20"}`}>
              <input type="radio" name={`${labId}-selection`} value={option.id} checked={activeOption === option.id} onChange={() => choose(option.id)} className="accent-brand" />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      <label className="mt-4 block text-xs font-semibold text-slate-700" htmlFor={`${labId}-comment`}>Handoff notes</label>
      <textarea id={`${labId}-comment`} value={comment} onChange={(event) => updateComment(event.target.value)} rows={5} placeholder="Describe modifications, additional inputs, details to preserve, and implementation or validation instructions for this option." className="mt-2 w-full resize-y rounded-md border-0 bg-slate-50 px-3 py-2.5 text-sm leading-relaxed text-ink ring-1 ring-inset ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-brand/40" />

      <div className="mt-4 grid gap-3">
        <fieldset>
          <legend className="text-xs font-semibold text-slate-700">Lab state</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {LAB_STATES.map((state) => (
              <label key={state.value} className={`cursor-pointer rounded-md px-3 py-2 text-xs font-semibold ring-1 ${disposition === state.value ? "bg-brand text-white ring-brand" : "bg-white text-slate-600 ring-slate-200 hover:ring-brand/30"}`}>
                <input
                  type="radio"
                  name={`${labId}-state`}
                  value={state.value}
                  checked={disposition === state.value}
                  onChange={() => {
                    setDisposition(state.value);
                    keepDraft(activeOption, comment, state.value);
                  }}
                  className="sr-only"
                />
                {state.label}
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      {showSaveConfirmation && (
        <div role="status" aria-live="polite" className={`mt-3 flex items-start gap-2 rounded-md px-3 py-2.5 ring-1 ${isReimplementation ? "bg-teal-50 text-teal-900 ring-teal-200" : "bg-emerald-50 text-emerald-900 ring-emerald-200"}`}>
          <CheckCircle2 size={16} className="mt-0.5 shrink-0" aria-hidden />
          <div>
            <p className="text-xs font-bold">{isReimplementation ? "Re-implementation handoff saved" : "Implementation handoff saved"}</p>
            <p className="mt-0.5 text-xs leading-relaxed">Saved {selectedLabel} and its exact notes as handoff version {handoffs.length}.</p>
          </div>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className={`text-xs ${status === "offline" ? "text-amber-700" : "text-slate-400"}`}>
          {status === "loading" && "Loading saved handoff…"}
          {status === "saving" && "Saving handoff…"}
          {status === "saved" && disposition === "ready" && "Ready handoff saved for implementation."}
          {status === "saved" && disposition === "implemented-review" && "Implementation is ready for owner review."}
          {status === "saved" && disposition === "parked" && "Lab parked with its chosen option and notes."}
          {status === "saved" && disposition === "completed" && "Owner sign-off recorded; Lab completed with its decision and notes preserved."}
          {status === "saved" && disposition === "discarded" && "Lab marked discarded; its review history remains preserved."}
          {status === "offline" && "Save did not complete. The draft is kept in this browser; restart the Labs server, then retry."}
          {status === "idle" && (dirty ? "Workspace save pending; browser draft kept" : saved ? "Saved in this workspace" : "Nothing saved yet")}
        </p>
        <button type="button" onClick={save} disabled={status === "saving"} className="btn-primary disabled:cursor-not-allowed disabled:opacity-50"><Save size={14} aria-hidden /> Save handoff version</button>
      </div>
    </section>
  );
}