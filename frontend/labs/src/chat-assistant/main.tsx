import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  Check,
  Heart,
  Map,
  Maximize2,
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
  {
    id: "sidecar",
    label: "A · Docked sidecar",
    summary: "Assistant stays attached to the right edge while the itinerary and map remain usable.",
    footprint: "About half the workspace",
    continuity: "Best for planning while inspecting the trip",
  },
  {
    id: "focus",
    label: "B · Focus modal",
    summary: "A centered temporary workspace dims the trip and puts profile context beside the conversation.",
    footprint: "Large centered layer",
    continuity: "Best for one concentrated planning turn",
  },
  {
    id: "guided",
    label: "C · Guided takeover",
    summary: "Assistant replaces the workspace with a staged flow from trip brief to research and review.",
    footprint: "Entire workspace",
    continuity: "Best for a deliberate start-to-finish wizard",
  },
];

const priorities = ["Food worth a detour", "Art & design", "Neighborhood walks", "One special night"];

function WorkspaceBackdrop() {
  const [activeDay, setActiveDay] = useState(2);
  return (
    <div className="absolute inset-0 flex flex-col bg-slate-100">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-slate-200 bg-white px-3 shadow-sm">
        <button type="button" className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-ink">Paris · Oct 12–17</button>
        <span className="text-xs font-medium text-emerald-700">Draft saved · 4 of 7 bookings ready</span>
        <nav className="ml-auto flex items-center gap-1 text-xs text-slate-500" aria-label="Preview workspace controls">
          <button type="button" className="rounded-md bg-slate-100 px-2 py-1.5 font-semibold text-ink">Itinerary</button>
          <button type="button" className="rounded-md px-2 py-1.5 hover:bg-slate-100">Map</button>
          <button type="button" className="rounded-md px-2 py-1.5 hover:bg-slate-100">Details</button>
        </nav>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-[30%_1fr_24%]">
        <section className="overflow-y-auto border-r border-slate-200 bg-white p-4" aria-label="Preview itinerary">
          <p className="text-[10px] font-bold uppercase text-brand">Your Paris circuit</p>
          <h2 className="display mt-1 text-xl font-semibold text-ink">Five relaxed days</h2>
          <p className="mt-1 text-xs text-slate-500">2 travelers · boutique stay · vegetarian-friendly</p>
          {[1, 2, 3].map((day) => (
            <button key={day} type="button" onClick={() => setActiveDay(day)} className={`mt-4 block w-full border-l-2 pl-3 text-left ${activeDay === day ? "border-brand" : "border-slate-200"}`}>
              <span className="flex items-center justify-between"><strong className="text-xs text-ink">Day {day}</strong><small className="text-[10px] text-slate-400">{day === 1 ? "Arrival" : day === 2 ? "7h 20m schedule" : "6h 40m schedule"}</small></span>
              <span className="mt-2 block rounded-md bg-slate-50 p-2.5 ring-1 ring-slate-100"><strong className="block text-xs text-slate-700">{day === 1 ? "Le Marais arrival walk" : day === 2 ? "Louvre · Palais Royal · Seine" : "Montmartre · Pigalle"}</strong><small className="mt-1 block text-[10px] text-slate-500">Hotel departure · 3 planned stops · return</small></span>
            </button>
          ))}
        </section>
        <section className="relative overflow-hidden bg-[#dfe9e3]" aria-label={`Preview map showing Day ${activeDay}`}>
          <div className="absolute inset-0 opacity-70 [background-image:linear-gradient(32deg,transparent_46%,#aebfb6_47%,#aebfb6_49%,transparent_50%),linear-gradient(128deg,transparent_46%,#c1d0c8_47%,#c1d0c8_49%,transparent_50%)] [background-size:84px_84px]" />
          <div className="absolute left-[18%] top-4 flex gap-1 rounded-md bg-white p-1 shadow-card">
            {[1, 2, 3].map((day) => <button key={day} type="button" onClick={() => setActiveDay(day)} className={`rounded px-2 py-1 text-[10px] font-bold ${activeDay === day ? "bg-ink text-white" : "text-slate-500"}`}>Day {day}</button>)}
          </div>
          <div className="absolute left-[35%] top-[28%] grid h-8 w-8 place-items-center rounded-full bg-brand text-xs font-bold text-white ring-4 ring-white">1</div>
          <div className="absolute left-[56%] top-[47%] grid h-8 w-8 place-items-center rounded-full bg-accent text-xs font-bold text-white ring-4 ring-white">2</div>
          <div className="absolute bottom-6 left-5 rounded-md bg-white/95 px-3 py-2 text-xs shadow-card"><strong className="text-ink">Day {activeDay} circuit</strong><span className="ml-2 text-slate-500">8.4 km · 48 min travel</span></div>
        </section>
        <section className="overflow-hidden border-l border-slate-200 bg-white p-4" aria-label="Preview trip details">
          <div className="h-28 rounded-md bg-[linear-gradient(145deg,#cbd5d1,#f1f5f3)]" />
          <p className="mt-4 text-[10px] font-bold uppercase text-accent">Day {activeDay} focus</p>
          <h2 className="display mt-1 text-lg font-semibold text-ink">Paris neighborhood guide</h2>
          <p className="mt-2 text-xs leading-relaxed text-slate-600">Walkable routes, practical meal stops, and quieter evening options tuned to this trip.</p>
          <div className="mt-4 space-y-2 text-xs"><p className="rounded-md bg-slate-50 p-2.5 font-semibold text-slate-700">Louvre Museum · Confirmed</p><p className="rounded-md bg-slate-50 p-2.5 font-semibold text-slate-700">Le Potager du Marais · Needs booking</p></div>
        </section>
      </div>
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

function VariantDiagram({ variant }: { variant: Variant }) {
  return (
    <div className="relative h-20 overflow-hidden rounded-md border border-slate-200 bg-slate-100" aria-hidden>
      <div className="absolute inset-2 grid grid-cols-[28%_1fr_24%] gap-1 opacity-70">
        <span className="rounded-sm bg-white" />
        <span className="rounded-sm bg-emerald-100" />
        <span className="rounded-sm bg-white" />
      </div>
      {variant === "sidecar" && <div className="absolute inset-y-1 right-1 w-[48%] rounded-sm bg-ink shadow-lg"><span className="absolute left-2 top-2 h-1 w-12 rounded bg-white/60" /></div>}
      {variant === "focus" && <div className="absolute inset-0 bg-slate-900/25"><div className="absolute inset-x-[10%] inset-y-[12%] rounded-sm bg-white shadow-lg"><span className="absolute left-2 top-2 h-1 w-14 rounded bg-brand/70" /></div></div>}
      {variant === "guided" && <div className="absolute inset-0 grid grid-cols-[24%_1fr] bg-white"><span className="border-r border-slate-200 bg-brand-50" /><span className="m-3 rounded-sm bg-slate-100" /></div>}
    </div>
  );
}

function AppliedDefaultsBar() {
  return (
    <div className="border-b border-emerald-100 bg-emerald-50 px-4 py-3 text-xs text-emerald-900">
      <span className="font-semibold">Already applied:</span> boutique 4-star stay · vegetarian-friendly · balanced days
    </div>
  );
}

function GuidedSteps() {
  return (
    <aside className="border-b border-slate-200 bg-[#f7faf9] p-5 lg:border-b-0 lg:border-r">
      <p className="text-[10px] font-bold uppercase text-brand">Planning path</p>
      <ol className="mt-5 grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
        {[
          ["1", "Trip brief", "Confirm only what differs"],
          ["2", "Research", "Flights, stay and daily routes"],
          ["3", "Review", "Approve the complete first plan"],
        ].map(([number, title, detail], index) => (
          <li key={number} className={`flex gap-3 rounded-md p-3 ${index === 0 ? "bg-white shadow-card ring-1 ring-brand/20" : "text-slate-500"}`}>
            <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-bold ${index === 0 ? "bg-brand text-white" : "bg-slate-200 text-slate-500"}`}>{number}</span>
            <span><strong className="block text-xs text-ink">{title}</strong><small className="mt-0.5 block text-[10px] leading-relaxed">{detail}</small></span>
          </li>
        ))}
      </ol>
      <p className="mt-5 text-[11px] leading-relaxed text-slate-500">The trip workspace returns only after the first plan is ready for review.</p>
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
    ? "inset-y-0 right-0 w-full sm:w-[min(42rem,52vw)] sm:rounded-l-md"
    : variant === "guided"
      ? "inset-0"
      : "inset-x-[7%] inset-y-[5%]";
  const title = variant === "sidecar" ? "Plan alongside your trip" : variant === "guided" ? "Build your trip step by step" : "Focus on the trip brief";

  return (
    <div className={`absolute ${overlayClass} flex overflow-hidden bg-white shadow-[0_24px_70px_rgba(15,23,42,.28)] ring-1 ring-slate-900/10 ${variant === "focus" ? "rounded-md" : ""}`}>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-slate-500 hover:bg-slate-100" aria-label="Close assistant"><ArrowLeft size={17} /></button>
            <div className="min-w-0"><p className="truncate text-sm font-semibold text-ink">{title}</p><p className="truncate text-[11px] text-slate-400">Your preferences are already in context</p></div>
          </div>
          <div className="flex items-center gap-2">
            {variant !== "guided" && <button type="button" className="hidden items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 sm:flex"><Map size={14} /> View trip</button>}
            <button type="button" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100" aria-label="Close"><X size={17} /></button>
          </div>
        </header>
        {variant === "sidecar" && <div className="flex min-h-0 flex-1 flex-col"><AppliedDefaultsBar /><Conversation built={built} onBuild={setBuilt} /></div>}
        {variant === "focus" && <div className="grid min-h-0 flex-1 lg:grid-cols-[17rem_1fr]"><PreferenceSummary /><Conversation built={built} onBuild={setBuilt} /></div>}
        {variant === "guided" && <div className="grid min-h-0 flex-1 lg:grid-cols-[15rem_1fr]"><GuidedSteps /><Conversation built={built} onBuild={setBuilt} /></div>}
      </div>
    </div>
  );
}

function ChatAssistantLab() {
  const previewVariant = new URLSearchParams(window.location.search).get("preview");
  const fullPreview = variants.some((item) => item.id === previewVariant);
  const [variant, setVariant] = useState<Variant>(fullPreview ? previewVariant as Variant : "focus");
  const chooseVariant = useCallback((optionId: string) => {
    if (variants.some((item) => item.id === optionId)) setVariant(optionId as Variant);
  }, []);

  if (fullPreview) {
    return (
      <main className="relative h-[100dvh] min-h-[40rem] overflow-hidden bg-white">
        <WorkspaceBackdrop />
        {variant === "focus" && <div className="absolute inset-0 bg-slate-950/35 backdrop-blur-[1px]" />}
        <AssistantOverlay key={variant} variant={variant} />
        <a href="./chat-assistant.html" className="fixed bottom-4 left-4 z-[80] inline-flex items-center gap-2 rounded-md bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop ring-1 ring-white/30"><ArrowLeft size={14} /> Exit full-size preview</a>
      </main>
    );
  }

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

        <div className="mt-5 grid gap-3 md:grid-cols-3" role="tablist" aria-label="Assistant layout variants">
          {variants.map((item) => (
            <button key={item.id} type="button" role="tab" aria-selected={variant === item.id} onClick={() => chooseVariant(item.id)} className={`rounded-md bg-white p-3 text-left shadow-card ring-1 transition ${variant === item.id ? "ring-2 ring-brand" : "ring-slate-200 hover:ring-slate-300"}`}>
              <VariantDiagram variant={item.id as Variant} />
              <strong className="mt-3 block text-sm text-ink">{item.label}</strong>
              <span className="mt-1 block text-xs leading-relaxed text-slate-600">{item.summary}</span>
              <span className="mt-3 block border-t border-slate-100 pt-2 text-[10px] font-bold uppercase text-slate-400">{item.footprint}</span>
              <span className="mt-1 block text-[11px] text-accent">{item.continuity}</span>
            </button>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-semibold text-ink">Live preview · {variants.find((item) => item.id === variant)?.label}</p>
          <div className="flex flex-wrap items-center gap-3"><p className="text-xs text-slate-500">Switch options above, then use the same controls to compare the experience.</p><a href={`?preview=${variant}`} className="btn-primary"><Maximize2 size={14} /> Open full-size preview</a></div>
        </div>

        <section className="relative mt-2 h-[760px] max-h-[78vh] min-h-[620px] overflow-hidden rounded-md border border-slate-200 bg-white shadow-card" aria-label="Interactive assistant layout preview">
          <WorkspaceBackdrop />
          {variant === "focus" && <div className="absolute inset-0 bg-slate-950/35 backdrop-blur-[1px]" />}
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
