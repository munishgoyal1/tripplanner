import { useEffect, useState } from "react";
import { Check, Clock3, MessageCircle, Sparkles, UsersRound, X } from "lucide-react";
import {
  fetchPreferences,
  savePreferences,
  fetchProfileSuggestions,
  resolveProfileSuggestion,
  type ProfileSuggestion,
} from "../api";

type FamilySuggestionState = "new" | "saving" | "saved" | "dismissed";

function FamilyLearningCard({
  state,
  onRemember,
  onDismiss,
}: {
  state: FamilySuggestionState;
  onRemember: () => void;
  onDismiss: () => void;
}) {
  if (state === "saved") {
    return <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800"><Check size={15} className="mt-0.5 shrink-0" aria-hidden /><span><strong className="font-semibold">Remembered for future trips.</strong> Rhea prefers relaxed mornings.</span></div>;
  }
  if (state === "dismissed") {
    return <div className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500"><X size={15} className="mt-0.5 shrink-0" aria-hidden /><span>Nothing saved. We will not ask again about this fact.</span></div>;
  }
  return (
    <section className="rounded-xl border border-violet-200 bg-violet-50/70 p-3" aria-label="Suggested family detail">
      <div className="flex items-start gap-2">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white text-violet-700 ring-1 ring-violet-200"><Sparkles size={14} aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><p className="text-xs font-semibold text-ink">A small thing I noticed</p><span className="inline-flex items-center gap-1 text-[10px] font-semibold text-violet-700"><Clock3 size={11} aria-hidden /> Suggested from chat</span></div>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">Rhea mentioned she likes relaxed mornings. Should I remember that for future trips?</p>
          <div className="mt-2 flex flex-wrap gap-2"><button type="button" onClick={onRemember} disabled={state === "saving"} className="inline-flex items-center gap-1.5 rounded-full bg-violet-700 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-violet-800 disabled:opacity-50"><Check size={13} aria-hidden /> Remember</button><button type="button" onClick={onDismiss} disabled={state === "saving"} className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-300 hover:bg-white disabled:opacity-50">Not now</button></div>
        </div>
      </div>
      <p className="mt-2 border-t border-violet-200 pt-2 text-[10px] text-violet-800">You decide what is saved. Change or remove it anytime.</p>
    </section>
  );
}

export default function TravellerProfile() {
  const [suggestions, setSuggestions] = useState<ProfileSuggestion[]>([]);
  const [familySuggestion, setFamilySuggestion] = useState<FamilySuggestionState>("new");

  useEffect(() => {
    fetchProfileSuggestions()
      .then(setSuggestions)
      .catch(() => setSuggestions([]));
  }, []);

  const familyMemberSuggestions = suggestions.filter((item) => item.kind === "family_member");

  function resolveFamilyMemberSuggestion(id: string, action: "save" | "dismiss") {
    setSuggestions((current) => current.filter((item) => item.id !== id));
    resolveProfileSuggestion(id, action).then(setSuggestions).catch(() => undefined);
  }

  async function rememberFamilySuggestion() {
    setFamilySuggestion("saving");
    try {
      const current = await fetchPreferences();
      const fact = "Rhea prefers relaxed mornings.";
      const aboutMe = current.about_me.includes(fact)
        ? current.about_me
        : `${current.about_me.trim()}${current.about_me.trim() ? " " : ""}${fact}`;
      await savePreferences({ about_me: aboutMe });
      setFamilySuggestion("saved");
    } catch {
      setFamilySuggestion("new");
    }
  }

  return (
    <div className="space-y-4 text-sm">
      {familyMemberSuggestions.length > 0 && (
        <div className="rounded-xl bg-amber-50/70 p-3 ring-1 ring-amber-200">
          <p className="text-xs font-medium text-amber-800">Noticed in chat · not saved yet</p>
          <p className="mt-0.5 text-[11px] text-amber-700/80">Nothing here is part of your profile until you keep it.</p>
          <ul className="mt-2 space-y-2">
            {familyMemberSuggestions.map((item) => (
              <li key={item.id} className="rounded-lg bg-white p-2.5 ring-1 ring-amber-100">
                <p className="text-xs font-semibold text-ink">{item.summary}</p>
                <div className="mt-1.5 flex items-center gap-2">
                  <button type="button" onClick={() => resolveFamilyMemberSuggestion(item.id, "save")} className="h-7 rounded-full bg-ink px-3 text-[11px] font-semibold text-white">Keep</button>
                  <button type="button" onClick={() => resolveFamilyMemberSuggestion(item.id, "dismiss")} className="h-7 rounded-full px-3 text-[11px] font-semibold text-slate-500 ring-1 ring-slate-200">Discard</button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
        <div className="mb-2 flex items-center gap-2"><MessageCircle size={14} className="text-brand" aria-hidden /><p className="text-xs font-semibold text-slate-700">Learned while planning</p><span className="ml-auto text-[10px] font-semibold uppercase tracking-wide text-slate-400">Reversible</span></div>
        <FamilyLearningCard state={familySuggestion} onRemember={rememberFamilySuggestion} onDismiss={() => setFamilySuggestion("dismissed")} />
      </div>
      {familyMemberSuggestions.length === 0 && familySuggestion !== "new" && (
        <p className="flex items-center gap-2 text-xs text-slate-400"><UsersRound size={14} aria-hidden /> Mention people travelling with you in chat and I'll ask before saving anything else.</p>
      )}
    </div>
  );
}
