import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Heart,
  Map,
  Maximize2,
  MessageCircle,
  Minus,
  Plus,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import "../../../src/index.css";

type Variant = "edge" | "sheet" | "popover";
type Pace = "easy" | "balanced" | "full";

const variants = [
  {
    id: "edge",
    label: "A · Collapsible edge drawer",
    summary: "A focused right drawer slides over Details, then collapses into a slim Assistant rail.",
    footprint: "420 px wide · full height",
    continuity: "Best balance of conversation room and fast workspace recovery",
  },
  {
    id: "sheet",
    label: "B · Corner conversation sheet",
    summary: "A lower-right sheet leaves most of the map and itinerary visible and collapses to one button.",
    footprint: "480 px wide · 68% height",
    continuity: "Best for short follow-ups while comparing the map",
  },
  {
    id: "popover",
    label: "C · Prompt popover + rail",
    summary: "Only the active prompt opens beside a persistent rail; completed planning recedes immediately.",
    footprint: "400 px prompt · 48 px rail",
    continuity: "Best for giving Itinerary, Map, and Details maximum priority",
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

function VariantDiagram({ variant }: { variant: Variant }) {
  return (
    <div className="relative h-20 overflow-hidden rounded-md border border-slate-200 bg-slate-100" aria-hidden>
      <div className="absolute inset-2 grid grid-cols-[28%_1fr_24%] gap-1 opacity-70">
        <span className="rounded-sm bg-white" />
        <span className="rounded-sm bg-emerald-100" />
        <span className="rounded-sm bg-white" />
      </div>
      {variant === "edge" && <div className="absolute inset-y-1 right-1 w-[38%] rounded-sm bg-ink shadow-lg"><span className="absolute left-2 top-2 h-1 w-12 rounded bg-white/60" /></div>}
      {variant === "sheet" && <div className="absolute bottom-1 right-1 h-[68%] w-[44%] rounded-sm bg-white shadow-lg ring-1 ring-slate-300"><span className="absolute left-2 top-2 h-1 w-10 rounded bg-brand/70" /></div>}
      {variant === "popover" && <><div className="absolute inset-y-1 right-1 w-2 rounded-sm bg-ink" /><div className="absolute bottom-2 right-4 h-[64%] w-[38%] rounded-sm bg-white shadow-lg ring-1 ring-slate-300"><span className="absolute left-2 top-2 h-1 w-9 rounded bg-accent/70" /></div></>}
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
        <button type="button" onClick={() => onBuild("2 travelers · balanced pace · saved priorities · prefer direct flights")} className="text-xs font-semibold text-slate-500 hover:text-ink">Skip · use all saved defaults</button>
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

function AssistantLauncher({ variant, onOpen }: { variant: Variant; onOpen: () => void }) {
  if (variant === "edge" || variant === "popover") {
    return (
      <aside className="absolute inset-y-3 right-3 z-30 flex w-12 flex-col items-center rounded-md bg-ink py-3 text-white shadow-pop ring-1 ring-white/20">
        <button type="button" onClick={onOpen} className="relative grid h-9 w-9 place-items-center rounded-md bg-brand" aria-label="Open Assistant">
          <MessageCircle size={17} /><span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-emerald-400 ring-2 ring-ink" />
        </button>
        <span className="mt-4 [writing-mode:vertical-rl] text-[10px] font-bold uppercase text-white/70">Assistant ready</span>
        <button type="button" onClick={onOpen} className="mt-auto grid h-8 w-8 place-items-center rounded-md text-white/70 hover:bg-white/10" aria-label="Expand Assistant"><ChevronRight size={16} className="rotate-180" /></button>
      </aside>
    );
  }
  return <button type="button" onClick={onOpen} className="absolute bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full bg-ink px-4 py-3 text-xs font-semibold text-white shadow-pop ring-1 ring-white/30"><MessageCircle size={16} /> Assistant <span className="h-2 w-2 rounded-full bg-emerald-400" /></button>;
}

function AssistantOverlay({ variant }: { variant: Variant }) {
  const [built, setBuilt] = useState<string | null>(null);
  const [open, setOpen] = useState(true);
  const overlayClass = variant === "edge"
    ? "inset-y-3 right-3 w-[min(26rem,calc(100%-1.5rem))] rounded-md"
    : variant === "sheet"
      ? "bottom-4 right-4 h-[68%] min-h-[31rem] w-[min(30rem,calc(100%-2rem))] rounded-md"
      : "bottom-4 right-16 h-[72%] min-h-[34rem] w-[min(25rem,calc(100%-5rem))] rounded-md";
  const title = variant === "edge" ? "Plan alongside your trip" : variant === "sheet" ? "Trip conversation" : "One quick trip prompt";

  if (!open) return <AssistantLauncher variant={variant} onOpen={() => setOpen(true)} />;

  return (
    <>
      {variant === "popover" && (
        <aside className="absolute inset-y-3 right-3 z-30 flex w-12 flex-col items-center rounded-md bg-ink py-3 text-white shadow-pop ring-1 ring-white/20">
          <button type="button" onClick={() => setOpen(false)} className="relative grid h-9 w-9 place-items-center rounded-md bg-brand" aria-label="Collapse Assistant to rail"><MessageCircle size={17} /><span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-emerald-400 ring-2 ring-ink" /></button>
          <span className="mt-4 [writing-mode:vertical-rl] text-[10px] font-bold uppercase text-white/70">Active prompt</span>
        </aside>
      )}
      <div className={`absolute z-30 ${overlayClass} flex overflow-hidden bg-white shadow-[0_24px_70px_rgba(15,23,42,.28)] ring-1 ring-slate-900/10`}>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4">
            <div className="flex min-w-0 items-center gap-3">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-brand-50 text-brand"><Sparkles size={15} /></span>
              <div className="min-w-0"><p className="truncate text-sm font-semibold text-ink">{title}</p><p className="truncate text-[11px] text-slate-400">{built ? "Brief complete · workspace is ready" : "Your preferences are already in context"}</p></div>
            </div>
            <div className="flex items-center gap-2">
              {built && <button type="button" onClick={() => setOpen(false)} className="hidden items-center gap-1 rounded-md px-2 py-1.5 text-xs font-semibold text-accent hover:bg-accent-50 sm:flex"><Map size={14} /> Return to trip</button>}
              <button type="button" onClick={() => setOpen(false)} className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100" aria-label="Collapse Assistant" title="Collapse Assistant"><X size={17} /></button>
            </div>
          </header>
          <div className="flex min-h-0 flex-1 flex-col"><AppliedDefaultsBar /><Conversation built={built} onBuild={setBuilt} /></div>
        </div>
      </div>
    </>
  );
}

function ChatAssistantLab() {
  const previewVariant = new URLSearchParams(window.location.search).get("preview");
  const fullPreview = variants.some((item) => item.id === previewVariant);
  const [variant, setVariant] = useState<Variant>(fullPreview ? previewVariant as Variant : "edge");
  const chooseVariant = useCallback((optionId: string) => {
    if (variants.some((item) => item.id === optionId)) setVariant(optionId as Variant);
  }, []);

  if (fullPreview) {
    return (
      <main className="relative h-[100dvh] min-h-[40rem] overflow-hidden bg-white">
        <WorkspaceBackdrop />
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
            <h1 className="display mt-2 text-3xl font-semibold text-ink">Assistant overlap after planning</h1>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">Compare three minimally intrusive ways to slide Assistant in for prompts and return visual priority to Itinerary, Map, and Details afterward. Build the brief, collapse it, reopen it, and inspect the same live workspace in every option.</p>
          </div>
          <LabNavigation current="active" />
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
          <AssistantOverlay key={variant} variant={variant} />
        </section>

        <section className="mt-6 grid gap-3 md:grid-cols-3">
          <article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><Heart size={16} className="text-brand" /><h2 className="mt-3 text-sm font-semibold text-ink">Judge the open state</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Can you answer the complete preference prompt without losing the trip context you need?</p></article>
          <article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><ThumbsUp size={16} className="text-accent" /><h2 className="mt-3 text-sm font-semibold text-ink">Judge the return</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Build the brief, use Return to trip, and confirm all three workspace panels regain priority.</p></article>
          <article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><ThumbsDown size={16} className="text-slate-500" /><h2 className="mt-3 text-sm font-semibold text-ink">Judge re-entry cost</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Reopen Assistant from its rail or button and decide whether the affordance is obvious but quiet.</p></article>
        </section>

        <div className="mt-6"><DecisionCapture labId="chat-assistant-overlay" labTitle="Assistant overlap after planning" options={variants} activeOption={variant} onChoose={chooseVariant} /></div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><ChatAssistantLab /></React.StrictMode>);
