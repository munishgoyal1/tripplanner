import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  Check,
  Heart,
  Map,
  MessageCircle,
  Minus,
  Plus,
  Send,
  SlidersHorizontal,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import "../../../src/index.css";

type Variant = "sidecar" | "focus" | "guided";
type Pace = "easy" | "balanced" | "full";

const variants = [
  { id: "sidecar", label: "A · Wide sidecar" },
  { id: "focus", label: "B · Focus overlay" },
  { id: "guided", label: "C · Guided canvas" },
];

const priorities = ["Food worth a detour", "Art & design", "Neighborhood walks", "One special night"];

function WorkspaceBackdrop() {
  return (
    <div className="absolute inset-0 grid grid-cols-[28%_1fr_25%] bg-slate-100" aria-hidden>
      <section className="border-r border-slate-200 bg-white p-5">
        <div className="h-5 w-28 rounded bg-slate-200" />
        {[1, 2, 3].map((day) => (
          <div key={day} className="mt-6 border-l-2 border-slate-200 pl-4">
            <div className="h-3 w-16 rounded bg-slate-200" />
            <div className="mt-3 h-14 rounded-md bg-slate-100" />
            <div className="mt-2 h-14 rounded-md bg-slate-100" />
          </div>
        ))}
      </section>
      <section className="relative overflow-hidden bg-[#e5ebe7]">
        <div className="absolute inset-0 opacity-50 [background-image:linear-gradient(32deg,transparent_46%,#b7c7bf_47%,#b7c7bf_49%,transparent_50%),linear-gradient(128deg,transparent_46%,#c7d4ce_47%,#c7d4ce_49%,transparent_50%)] [background-size:84px_84px]" />
        <div className="absolute left-[38%] top-[30%] h-4 w-4 rounded-full bg-brand ring-4 ring-white" />
        <div className="absolute left-[57%] top-[48%] h-4 w-4 rounded-full bg-accent ring-4 ring-white" />
        <div className="absolute bottom-8 left-8 rounded-md bg-white/90 px-3 py-2 text-xs font-semibold text-slate-500 shadow-card">Paris · 5 days</div>
      </section>
      <section className="border-l border-slate-200 bg-white p-5">
        <div className="h-32 rounded-md bg-slate-100" />
        <div className="mt-4 h-4 w-32 rounded bg-slate-200" />
        <div className="mt-3 h-2 w-full rounded bg-slate-100" />
        <div className="mt-2 h-2 w-4/5 rounded bg-slate-100" />
      </section>
    </div>
  );
}

function PreferenceSummary() {
  return (
    <aside className="border-b border-slate-200 bg-[#f7faf9] p-4 lg:border-b-0 lg:border-r">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase text-accent">Using your travel profile</p>
          <h3 className="mt-1 text-sm font-semibold text-ink">Your usual defaults</h3>
        </div>
        <button type="button" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-white" aria-label="Adjust saved preferences"><SlidersHorizontal size={15} /></button>
      </div>
      <dl className="mt-5 space-y-4 text-xs">
        <div><dt className="font-semibold text-slate-400">Travel style</dt><dd className="mt-1 text-slate-700">Balanced days, local neighborhoods, no rushed mornings</dd></div>
        <div><dt className="font-semibold text-slate-400">Stay</dt><dd className="mt-1 text-slate-700">Boutique 4-star · walkable · quiet room</dd></div>
        <div><dt className="font-semibold text-slate-400">Food</dt><dd className="mt-1 text-slate-700">Vegetarian-friendly · local favorites over tasting menus</dd></div>
        <div><dt className="font-semibold text-slate-400">Flights</dt><dd className="mt-1 text-slate-700">Direct when practical · economy</dd></div>
      </dl>
      <p className="mt-5 border-t border-emerald-100 pt-4 text-[11px] leading-relaxed text-slate-500">Only trip-specific changes below apply to Paris. Your long-term defaults stay unchanged.</p>
    </aside>
  );
}

function ChoicePrompt({ onBuild }: { onBuild: (summary: string) => void }) {
  const [pace, setPace] = useState<Pace>("balanced");
  const [selected, setSelected] = useState<string[]>([priorities[0], priorities[2]]);
  const [travelers, setTravelers] = useState(2);
  const [direct, setDirect] = useState(true);

  const togglePriority = (priority: string) => {
    setSelected((current) => current.includes(priority) ? current.filter((item) => item !== priority) : [...current, priority]);
  };

  const submit = () => {
    const paceLabel = pace === "easy" ? "easy" : pace === "full" ? "full" : "balanced";
    onBuild(`${travelers} travelers · ${paceLabel} pace · ${selected.join(", ")} · ${direct ? "prefer direct flights" : "best flight value"}`);
  };

  return (
    <div className="mt-4 rounded-md border border-slate-200 bg-white p-4 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-ink">Anything different for this trip?</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">I have enough to start. Change only what matters, or use your defaults.</p>
        </div>
        <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold text-emerald-700 ring-1 ring-emerald-200">1 quick step</span>
      </div>

      <fieldset className="mt-5">
        <legend className="text-xs font-semibold text-slate-700">Pace</legend>
        <div className="mt-2 grid grid-cols-3 gap-2">
          {([['easy', 'Easy'], ['balanced', 'Balanced'], ['full', 'Full days']] as [Pace, string][]).map(([value, label]) => (
            <label key={value} className={`cursor-pointer rounded-md px-3 py-2 text-center text-xs font-semibold ring-1 ${pace === value ? "bg-brand-50 text-brand ring-brand/30" : "text-slate-600 ring-slate-200 hover:ring-slate-300"}`}>
              <input className="sr-only" type="radio" name="pace" value={value} checked={pace === value} onChange={() => setPace(value)} />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="mt-5">
        <legend className="text-xs font-semibold text-slate-700">Make room for</legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {priorities.map((priority) => {
            const active = selected.includes(priority);
            return <button key={priority} type="button" aria-pressed={active} onClick={() => togglePriority(priority)} className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ring-1 ${active ? "bg-accent-50 text-accent ring-accent/30" : "bg-white text-slate-600 ring-slate-200"}`}>{active && <Check size={12} />}{priority}</button>;
          })}
        </div>
      </fieldset>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <div className="flex h-11 items-center justify-between rounded-md bg-slate-50 px-3 ring-1 ring-inset ring-slate-200">
          <span className="text-xs font-semibold text-slate-700">Travelers</span>
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => setTravelers((value) => Math.max(1, value - 1))} className="grid h-7 w-7 place-items-center rounded-full bg-white text-slate-600 ring-1 ring-slate-200" aria-label="Remove traveler"><Minus size={13} /></button>
            <span className="w-4 text-center text-sm font-semibold">{travelers}</span>
            <button type="button" onClick={() => setTravelers((value) => Math.min(8, value + 1))} className="grid h-7 w-7 place-items-center rounded-full bg-white text-slate-600 ring-1 ring-slate-200" aria-label="Add traveler"><Plus size={13} /></button>
          </div>
        </div>
        <button type="button" aria-pressed={direct} onClick={() => setDirect((value) => !value)} className="flex h-11 items-center justify-between rounded-md bg-slate-50 px-3 text-left ring-1 ring-inset ring-slate-200">
          <span className="text-xs font-semibold text-slate-700">Prefer direct flights</span>
          <span className={`relative h-6 w-10 rounded-full transition ${direct ? "bg-accent" : "bg-slate-300"}`}><span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${direct ? "left-5" : "left-1"}`} /></span>
        </button>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
        <button type="button" className="text-xs font-semibold text-slate-500 hover:text-ink">Skip · use all saved defaults</button>
        <button type="button" onClick={submit} className="btn-primary"><Sparkles size={14} /> Build my trip</button>
      </div>
    </div>
  );
}

function Conversation({ built, onBuild }: { built: string | null; onBuild: (summary: string) => void }) {
  return (
    <section className="flex min-h-0 flex-1 flex-col bg-[#fcfcfb]">
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="ml-auto max-w-[80%] rounded-md bg-ink px-4 py-3 text-sm leading-relaxed text-white">Plan Paris from Delhi for five days in October. Keep it relaxed and make it feel special.</div>
        <div className="mt-5 flex max-w-2xl items-start gap-3">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-brand text-white"><Sparkles size={15} /></span>
          <div>
            <p className="text-sm leading-relaxed text-slate-700">I’ll use your saved boutique-stay, vegetarian-friendly, and balanced-day preferences. October is flexible, so I’ll compare the strongest five-day window before I lock flights and the daily route.</p>
            {!built ? <ChoicePrompt onBuild={onBuild} /> : (
              <>
                <div className="mt-4 rounded-md bg-accent-50 px-4 py-3 text-xs leading-relaxed text-accent ring-1 ring-accent/20"><span className="font-semibold">Trip brief confirmed:</span> {built}</div>
                <div className="mt-4 rounded-md border border-emerald-200 bg-white p-4 shadow-card">
                  <div className="flex items-center gap-2 text-emerald-700"><Check size={15} /><p className="text-xs font-bold uppercase">Ready to build</p></div>
                  <p className="display mt-2 text-lg font-semibold text-ink">Paris · 5 days · balanced and neighborhood-led</p>
                  <p className="mt-2 text-xs leading-relaxed text-slate-600">I’ll now choose the best flight window, one concrete stay, practical daily circuits, and named meal stops. You can refine every choice afterward.</p>
                  <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-slate-500"><span className="pill">Saved preferences applied</span><span className="pill">Trip changes isolated</span><span className="pill">No unanswered blockers</span></div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
      <div className="border-t border-slate-200 bg-white/95 p-3 sm:p-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-md bg-slate-50 p-2 ring-1 ring-inset ring-slate-200">
          <textarea rows={1} placeholder="Change anything or add a constraint…" className="min-h-10 flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm outline-none placeholder:text-slate-400" />
          <button type="button" className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-brand text-white" aria-label="Send message"><Send size={16} /></button>
        </div>
      </div>
    </section>
  );
}

function AssistantOverlay({ variant }: { variant: Variant }) {
  const [built, setBuilt] = useState<string | null>(null);
  const overlayClass = variant === "sidecar"
    ? "inset-y-3 right-3 w-[min(72rem,78vw)]"
    : variant === "guided"
      ? "inset-3"
      : "inset-x-[7%] inset-y-[5%]";
  const bodyClass = variant === "sidecar"
    ? "grid min-h-0 flex-1 lg:grid-cols-[16rem_1fr]"
    : variant === "guided"
      ? "grid min-h-0 flex-1 lg:grid-cols-[19rem_1fr]"
      : "grid min-h-0 flex-1 lg:grid-cols-[17rem_1fr]";

  return (
    <div className={`absolute ${overlayClass} flex overflow-hidden rounded-md bg-white shadow-[0_24px_70px_rgba(15,23,42,.28)] ring-1 ring-slate-900/10`}>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-slate-500 hover:bg-slate-100" aria-label="Close assistant"><ArrowLeft size={17} /></button>
            <div className="min-w-0"><p className="truncate text-sm font-semibold text-ink">Plan a new trip</p><p className="truncate text-[11px] text-slate-400">Your preferences are already in context</p></div>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="hidden items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 sm:flex"><Map size={14} /> View trip</button>
            <button type="button" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100" aria-label="Close"><X size={17} /></button>
          </div>
        </header>
        <div className={bodyClass}><PreferenceSummary /><Conversation built={built} onBuild={setBuilt} /></div>
      </div>
    </div>
  );
}

function ChatAssistantLab() {
  const [variant, setVariant] = useState<Variant>("focus");
  const chooseVariant = useCallback((optionId: string) => {
    if (variants.some((item) => item.id === optionId)) setVariant(optionId as Variant);
  }, []);

  return (
    <main className="min-h-full bg-slate-50 px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[92rem]">
        <header className="flex flex-wrap items-end justify-between gap-5 border-b border-slate-200 pb-5">
          <div>
            <div className="flex items-center gap-2 text-brand"><MessageCircle size={17} /><p className="text-[10px] font-bold uppercase">Active UX Lab</p></div>
            <h1 className="display mt-2 text-3xl font-semibold text-ink">Assistant-led trip kickoff</h1>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">Test how the Assistant can ask one compact, personalized question before building a complete first itinerary. The controls are live.</p>
          </div>
          <a href="./catalog.html" className="btn-ghost"><ArrowLeft size={14} /> UX Labs</a>
        </header>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex rounded-md bg-white p-1 shadow-card ring-1 ring-slate-200" role="tablist" aria-label="Overlay variants">
            {variants.map((item) => <button key={item.id} type="button" role="tab" aria-selected={variant === item.id} onClick={() => chooseVariant(item.id)} className={`rounded px-3 py-2 text-xs font-semibold ${variant === item.id ? "bg-ink text-white" : "text-slate-500 hover:bg-slate-50"}`}>{item.label}</button>)}
          </div>
          <p className="text-xs text-slate-500"><span className="font-semibold text-emerald-700">Recommended B:</span> focused conversation with enough itinerary context left visible.</p>
        </div>

        <section className="relative mt-4 h-[760px] max-h-[78vh] min-h-[620px] overflow-hidden rounded-md border border-slate-200 bg-white shadow-card" aria-label="Interactive assistant overlay preview">
          <WorkspaceBackdrop />
          <div className="absolute inset-0 bg-slate-950/30 backdrop-blur-[1px]" />
          <AssistantOverlay key={variant} variant={variant} />
        </section>

        <section className="mt-6 grid gap-3 md:grid-cols-3">
          <article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><Heart size={16} className="text-brand" /><h2 className="mt-3 text-sm font-semibold text-ink">Personal first</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Show what the planner already knows, then ask only for trip-specific changes.</p></article>
          <article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><ThumbsUp size={16} className="text-accent" /><h2 className="mt-3 text-sm font-semibold text-ink">Fast by default</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Every prompt has a sensible preselection and a direct path to build.</p></article>
          <article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><ThumbsDown size={16} className="text-slate-500" /><h2 className="mt-3 text-sm font-semibold text-ink">No questionnaire mode</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Questions stay consolidated; low-impact gaps are inferred and disclosed.</p></article>
        </section>

        <div className="mt-6"><DecisionCapture labId="chat-assistant-overlay" labTitle="Assistant-led trip kickoff" options={variants} activeOption={variant} onChoose={chooseVariant} /></div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><ChatAssistantLab /></React.StrictMode>);
