import { Check, Save } from "lucide-react";
import { useEffect, useState } from "react";

interface DecisionOption {
  id: string;
  label: string;
}

interface SavedSelection {
  selection: string;
  comment: string;
  updatedAt?: string;
}

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
  const [status, setStatus] = useState<"loading" | "idle" | "saving" | "saved" | "offline">("loading");

  useEffect(() => {
    let localDraft: SavedSelection | null = null;
    try {
      localDraft = JSON.parse(localStorage.getItem(draftKey) || "null") as SavedSelection | null;
      if (localDraft) {
        setComment(localDraft.comment || "");
        onChoose(localDraft.selection);
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
        const localIsNewer = localDraft?.updatedAt && existing?.updatedAt
          ? localDraft.updatedAt > existing.updatedAt
          : Boolean(localDraft && !existing);
        if (existing && !localIsNewer) {
          setComment(existing.comment || "");
          setSaved(existing);
          onChoose(existing.selection);
        }
        setStatus("idle");
      })
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") setStatus("offline");
      });
    return () => controller.abort();
  }, [draftKey, labId, onChoose]);

  const selectedLabel = options.find((option) => option.id === activeOption)?.label || activeOption;
  const dirty = saved?.selection !== activeOption || saved?.comment !== comment;

  const keepDraft = (selection: string, nextComment: string) => {
    localStorage.setItem(draftKey, JSON.stringify({ selection, comment: nextComment, updatedAt: new Date().toISOString() }));
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
    keepDraft(activeOption, comment);
    setStatus("saving");
    try {
      const response = await fetch("/__labs/selections", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ labId, labTitle, selection: activeOption, selectionLabel: selectedLabel, comment }),
      });
      if (!response.ok) throw new Error("Unable to save selection");
      setSaved({ selection: activeOption, comment });
      setStatus("saved");
    } catch {
      setStatus("offline");
    }
  };

  return (
    <section className="rounded-md bg-white p-4 shadow-card ring-1 ring-slate-200" aria-labelledby={`${labId}-decision-title`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase text-brand">Your handoff</p>
          <h2 id={`${labId}-decision-title`} className="mt-0.5 text-base font-semibold text-ink">Select a direction and leave instructions</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">Saved to a local workspace file that Copilot can read when you say “pick and execute.”</p>
        </div>
        {saved && !dirty && (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-bold uppercase text-emerald-700 ring-1 ring-emerald-200"><Check size={11} aria-hidden /> Saved</span>
        )}
      </div>

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

      <label className="mt-4 block text-xs font-semibold text-slate-700" htmlFor={`${labId}-comment`}>Modifications and implementation instructions</label>
      <textarea id={`${labId}-comment`} value={comment} onChange={(event) => updateComment(event.target.value)} rows={4} placeholder="What should change in this option? Mention anything to keep, remove, combine, or test." className="mt-2 w-full resize-y rounded-md border-0 bg-slate-50 px-3 py-2.5 text-sm leading-relaxed text-ink ring-1 ring-inset ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-brand/40" />

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className={`text-xs ${status === "offline" ? "text-amber-700" : "text-slate-400"}`}>
          {status === "loading" && "Loading saved handoff…"}
          {status === "saving" && "Saving handoff…"}
          {status === "saved" && "Handoff saved. You can now ask Copilot to pick and execute it."}
          {status === "offline" && "Draft kept in this browser. Restart the Labs server, then retry Save handoff."}
          {status === "idle" && (dirty ? "Workspace save pending; browser draft kept" : saved ? "Saved in this workspace" : "Nothing saved yet")}
        </p>
        <button type="button" onClick={save} disabled={status === "saving" || !dirty} className="btn-primary disabled:cursor-not-allowed disabled:opacity-50"><Save size={14} aria-hidden /> Save handoff</button>
      </div>
    </section>
  );
}