import { useEffect, useState } from "react";
import { Check, Clock3, MessageCircle, Pencil, Plus, Sparkles, Trash2, UsersRound, X } from "lucide-react";
import {
  fetchPreferences,
  savePreferences,
  saveFamilyMember,
  removeFamilyMember,
  fetchProfileSuggestions,
  resolveProfileSuggestion,
  type FamilyMember,
  type FamilyMemberEdit,
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

const RELATIONSHIP_OPTIONS = Object.keys(RELATIONSHIP_LABEL).filter((r) => r !== "self") as FamilyMember["relationship"][];

function memberTags(member: FamilyMember): string[] {
  return [...(member.dietary ?? []), ...(member.mobility ?? []), ...(member.interests ?? [])];
}

function memberKey(member: Pick<FamilyMember, "relationship" | "name">): string {
  return `${member.relationship}|${(member.name || "").toLowerCase()}`;
}

interface MemberDraft {
  relationship: FamilyMember["relationship"];
  name: string;
  age: string;
  dietary: string;
  mobility: string;
  interests: string;
  notes: string;
}

function toDraft(member?: FamilyMember): MemberDraft {
  return {
    relationship: member?.relationship ?? "other",
    name: member?.name ?? "",
    age: member?.age != null ? String(member.age) : "",
    dietary: (member?.dietary ?? []).join(", "),
    mobility: (member?.mobility ?? []).join(", "),
    interests: (member?.interests ?? []).join(", "),
    notes: member?.notes ?? "",
  };
}

function parseCommaList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function MemberEditor({ draft, onChange, onSave, onCancel, saving }: {
  draft: MemberDraft;
  onChange: (next: MemberDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) {
  return (
    <div className="space-y-2 rounded-lg bg-white p-3 ring-2 ring-brand/40">
      <div className="flex gap-2">
        <select className="input h-8 w-28 text-xs" value={draft.relationship} onChange={(e) => onChange({ ...draft, relationship: e.target.value as FamilyMember["relationship"] })}>
          {RELATIONSHIP_OPTIONS.map((rel) => <option key={rel} value={rel}>{RELATIONSHIP_LABEL[rel]}</option>)}
        </select>
        <input className="input h-8 flex-1 text-xs" placeholder="Name" value={draft.name} onChange={(e) => onChange({ ...draft, name: e.target.value })} />
        <input className="input h-8 w-16 text-xs" type="number" min={0} max={120} placeholder="Age" value={draft.age} onChange={(e) => onChange({ ...draft, age: e.target.value })} />
      </div>
      <input className="input h-8 w-full text-xs" placeholder="Dietary (comma-separated)" value={draft.dietary} onChange={(e) => onChange({ ...draft, dietary: e.target.value })} />
      <input className="input h-8 w-full text-xs" placeholder="Mobility (comma-separated)" value={draft.mobility} onChange={(e) => onChange({ ...draft, mobility: e.target.value })} />
      <input className="input h-8 w-full text-xs" placeholder="Interests (comma-separated)" value={draft.interests} onChange={(e) => onChange({ ...draft, interests: e.target.value })} />
      <input className="input h-8 w-full text-xs" placeholder="Notes" value={draft.notes} onChange={(e) => onChange({ ...draft, notes: e.target.value })} />
      <div className="flex justify-end gap-2 pt-1">
        <button type="button" onClick={onCancel} disabled={saving} className="h-7 rounded-full px-3 text-[11px] font-semibold text-slate-500 ring-1 ring-slate-200 disabled:opacity-50">Cancel</button>
        <button type="button" onClick={onSave} disabled={saving || !draft.name.trim()} className="h-7 rounded-full bg-brand px-3 text-[11px] font-semibold text-white disabled:opacity-40">{saving ? "Saving…" : "Save"}</button>
      </div>
    </div>
  );
}

function MemberCard({ member, onEdit, onRemove }: { member: FamilyMember; onEdit: () => void; onRemove: () => void }) {
  const tags = memberTags(member);
  return (
    <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <strong className="text-xs font-semibold text-ink">{member.name || RELATIONSHIP_LABEL[member.relationship]}</strong>
          <span className="text-[11px] text-slate-400">{RELATIONSHIP_LABEL[member.relationship]}{member.age ? ` · ${member.age}` : ""}</span>
        </div>
        <div className="flex shrink-0 gap-1">
          <button type="button" onClick={onEdit} aria-label={`Edit ${member.name || RELATIONSHIP_LABEL[member.relationship]}`} className="grid h-6 w-6 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-ink"><Pencil size={12} aria-hidden /></button>
          <button type="button" onClick={onRemove} aria-label={`Remove ${member.name || RELATIONSHIP_LABEL[member.relationship]}`} className="grid h-6 w-6 place-items-center rounded-md text-slate-400 hover:bg-rose-50 hover:text-rose-600"><Trash2 size={12} aria-hidden /></button>
        </div>
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
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<MemberDraft | null>(null);
  const [savingMember, setSavingMember] = useState(false);

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

  function startEdit(member?: FamilyMember) {
    setEditingKey(member ? memberKey(member) : "__new__");
    setDraft(toDraft(member));
  }

  function cancelEdit() {
    setEditingKey(null);
    setDraft(null);
  }

  async function saveDraft(original?: FamilyMember) {
    if (!draft || !draft.name.trim()) return;
    setSavingMember(true);
    try {
      const edit: FamilyMemberEdit = {
        original_relationship: original?.relationship,
        original_name: original?.name,
        relationship: draft.relationship,
        name: draft.name.trim(),
        age: draft.age.trim() ? Number(draft.age) : null,
        dietary: parseCommaList(draft.dietary),
        mobility: parseCommaList(draft.mobility),
        interests: parseCommaList(draft.interests),
        notes: draft.notes.trim(),
      };
      const family_members = await saveFamilyMember(edit);
      setPrefs((current) => (current ? { ...current, family_members } : current));
      cancelEdit();
    } finally {
      setSavingMember(false);
    }
  }

  async function removeMember(member: FamilyMember) {
    const family_members = await removeFamilyMember(member.relationship, member.name || "");
    setPrefs((current) => (current ? { ...current, family_members } : current));
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
      <div>
        <p className="mb-2 text-xs font-semibold text-slate-700">Each traveller</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {members.map((member, index) => {
            const key = member.name ? memberKey(member) : `${member.relationship}-${index}`;
            return editingKey === key && draft ? (
              <MemberEditor key={key} draft={draft} onChange={setDraft} onSave={() => saveDraft(member)} onCancel={cancelEdit} saving={savingMember} />
            ) : (
              <MemberCard key={key} member={member} onEdit={() => startEdit(member)} onRemove={() => removeMember(member)} />
            );
          })}
          {editingKey === "__new__" && draft && (
            <MemberEditor draft={draft} onChange={setDraft} onSave={() => saveDraft()} onCancel={cancelEdit} saving={savingMember} />
          )}
        </div>
        {editingKey === null && (
          <button type="button" onClick={() => startEdit()} className="mt-2 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-semibold text-brand ring-1 ring-brand/30 hover:bg-brand/5"><Plus size={13} aria-hidden /> Add traveller</button>
        )}
      </div>
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
