import { useEffect, useState } from "react";
import { Check, Clock3, MessageCircle, Sparkles, UsersRound, X } from "lucide-react";
import {
  fetchPreferences,
  savePreferences,
  fetchProfileSuggestions,
  resolveProfileSuggestion,
  type FamilyMember,
  type Preferences,
  type ProfileSuggestion,
} from "../api";

const RELATIONSHIP_LABEL: Record<FamilyMember["relationship"], string> = {
  self: "You",
  spouse: "Spouse",
  partner: "Partner",
  child: "Child",
  parent: "Parent",
  sibling: "Sibling",
  friend: "Friend",
  other: "Traveller",
};

function memberTags(member: FamilyMember): string[] {
  return [...(member.dietary ?? []), ...(member.mobility ?? []), ...(member.interests ?? [])];
}

function MemberCard({ member }: { member: FamilyMember }) {
  const tags = memberTags(member);
  return (
    <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
      <div className="flex items-baseline gap-2">
        <strong className="text-xs font-semibold text-ink">{member.name || RELATIONSHIP_LABEL[member.relationship]}</strong>
        <span className="text-[11px] text-slate-400">{RELATIONSHIP_LABEL[member.relationship]}{member.age ? ` · ${member.age}` : ""}</span>
      </div>
      {tags.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {tags.map((tag) => <span key={tag} className="rounded-full bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-600 ring-1 ring-slate-200">{tag}</span>)}
        </div>
      )}
      {member.notes && <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">{member.notes}</p>}
    </div>
  );
}

function SharedByEveryone({ prefs }: { prefs: Preferences }) {
  const tags = [prefs.trip_style, prefs.budget_level, ...prefs.dietary].filter(Boolean);
  if (tags.length === 0) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <p className="text-xs font-semibold text-slate-700">Shared by everyone</p>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {tags.map((tag) => <span key={tag} className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-slate-600 ring-1 ring-slate-200">{tag.replace(/[-_]/g, " ")}</span>)}
      </div>
    </div>
  );
}

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
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [suggestions, setSuggestions] = useState<ProfileSuggestion[]>([]);
  const [familySuggestion, setFamilySuggestion] = useState<FamilySuggestionState>("new");

  useEffect(() => {
    fetchPreferences().then(setPrefs).catch(() => setPrefs(null));
    fetchProfileSuggestions()
      .then(setSuggestions)
      .catch(() => setSuggestions([]));
  }, []);

  const members = (prefs?.family_members ?? []).filter((m) => m.relationship !== "self");

  const familyMemberSuggestions = suggestions.filter((item) => item.kind === "family_member");

  function resolveFamilyMemberSuggestion(id: string, action: "save" | "dismiss") {
    setSuggestions((current) => current.filter((item) => item.id !== id));
    resolveProfileSuggestion(id, action).then(setSuggestions).catch(() => undefined);
  }

  async function rememberFamilySuggestion() {
    setFamilySuggestion("saving");
    try {
      const current = prefs ?? (await fetchPreferences());
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
      {prefs && <SharedByEveryone prefs={prefs} />}
      {members.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold text-slate-700">Each traveller</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {members.map((member, index) => <MemberCard key={member.name || `${member.relationship}-${index}`} member={member} />)}
          </div>
        </div>
      )}
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
