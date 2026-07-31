import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  CalendarDays,
  ChevronDown,
  CircleUserRound,
  Download,
  EyeOff,
  List,
  Map,
  MessageCircle,
  MoreHorizontal,
  PanelRight,
  Plus,
  Settings2,
  Sparkles,
  X,
} from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabScope } from "../shared/LabScope";
import "../../../src/index.css";

type Variant = "semantic" | "compact" | "text";

const variants = [
  {
    id: "semantic",
    label: "A · Semantic icon + text",
    summary: "Every workspace surface gets a recognizable meaning-first icon and a short label.",
  },
  {
    id: "compact",
    label: "B · Compact control rail",
    summary: "Persistent surfaces use icon buttons with tooltips; commands retain text where clarity matters.",
  },
  {
    id: "text",
    label: "C · Text-led command bar",
    summary: "Surface names do the navigation work; icons are reserved for unambiguous actions.",
  },
];

const days = [
  { day: 1, title: "Arrival and Le Marais", stops: ["Hotel Providence", "Place des Vosges", "Le Potager du Marais"], color: "#dc5a64" },
  { day: 2, title: "Louvre to the Seine", stops: ["Louvre Museum", "Palais Royal", "Seine sunset walk"], color: "#16867a" },
  { day: 3, title: "Montmartre slowly", stops: ["Sacré-Cœur", "Rue des Abbesses", "Bouillon Pigalle"], color: "#d18a2d" },
];

const surfaceControls = [
  { id: "itinerary", label: "Itinerary", Icon: List },
  { id: "map", label: "Map", Icon: Map },
  { id: "details", label: "Details", Icon: PanelRight },
  { id: "assistant", label: "Assistant", Icon: MessageCircle },
];

function SurfaceControl({ variant, id, label, Icon, active, onToggle }: {
  variant: Variant;
  id: string;
  label: string;
  Icon: typeof List;
  active: boolean;
  onToggle: (id: string) => void;
}) {
  if (variant === "text") {
    return <button type="button" onClick={() => onToggle(id)} className={`h-8 border-b-2 px-2 text-xs font-semibold ${active ? "border-[#d94d61] text-[#172433]" : "border-transparent text-[#66727d] hover:text-[#172433]"}`} aria-pressed={active}>{label}</button>;
  }
  return (
    <button
      type="button"
      onClick={() => onToggle(id)}
      className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition ${active ? "bg-[#172433] text-white" : "text-[#66727d] hover:bg-[#edf1f0] hover:text-[#172433]"}`}
      aria-pressed={active}
      aria-label={label}
      title={label}
    >
      <Icon size={14} aria-hidden />
      {variant === "semantic" && <span className="hidden lg:inline">{label}</span>}
    </button>
  );
}

function Workspace({ variant }: { variant: Variant }) {
  const [activeDay, setActiveDay] = useState(2);
  const [visible, setVisible] = useState<Record<string, boolean>>({ itinerary: true, map: true, details: true, assistant: false });
  const [menuOpen, setMenuOpen] = useState(false);
  const toggle = (id: string) => setVisible((current) => ({ ...current, [id]: !current[id] }));

  return (
    <div className="flex h-full min-h-[38rem] flex-col overflow-hidden bg-[#eef1ef] text-[#172433]" style={{ fontFamily: "'DM Sans', sans-serif" }}>
      <header className="relative z-30 flex min-h-12 shrink-0 flex-wrap items-center gap-2 border-b border-[#dce2df] bg-[#fbfcfb]/95 px-3 py-2 shadow-[0_1px_4px_rgba(23,36,51,.06)] backdrop-blur sm:flex-nowrap sm:py-0">
        <button type="button" className="inline-flex h-8 items-center gap-2 rounded-md border border-[#d6ddda] bg-white px-2.5 text-xs font-semibold shadow-sm">
          Paris · Oct 12–17 <ChevronDown size={13} aria-hidden />
        </button>
        <span className="hidden text-[11px] font-medium text-[#18806f] lg:inline">Saved · 4 of 7 bookings ready</span>
        <div className="order-last flex w-full items-center justify-between gap-1 sm:order-none sm:ml-auto sm:w-auto" aria-label="Workspace surfaces">
          {surfaceControls.map((control) => <SurfaceControl key={control.id} {...control} variant={variant} active={visible[control.id]} onToggle={toggle} />)}
        </div>
        <span className="mx-1 h-5 w-px bg-[#dce2df]" />
        {variant === "text" ? (
          <>
            <button type="button" className="h-8 px-2 text-xs font-semibold text-[#66727d] hover:text-[#172433]">New trip</button>
            <button type="button" className="h-8 px-2 text-xs font-semibold text-[#66727d] hover:text-[#172433]">Export</button>
          </>
        ) : (
          <>
            <button type="button" className="grid h-8 w-8 place-items-center rounded-md text-[#66727d] hover:bg-[#edf1f0]" title="New trip" aria-label="New trip"><Plus size={15} /></button>
            <button type="button" className="grid h-8 w-8 place-items-center rounded-md text-[#66727d] hover:bg-[#edf1f0]" title="Export trip" aria-label="Export trip"><Download size={15} /></button>
          </>
        )}
        <button type="button" className="grid h-8 w-8 place-items-center rounded-md text-[#66727d] hover:bg-[#edf1f0]" aria-label="Travel preferences"><Settings2 size={15} /></button>
        <button type="button" className="grid h-8 w-8 place-items-center rounded-md text-[#18806f] hover:bg-[#edf1f0]" aria-label="Account"><CircleUserRound size={16} /></button>
      </header>

      <div className={`grid min-h-0 flex-1 max-md:!grid-cols-1 ${visible.itinerary && visible.details ? "grid-cols-[minmax(14rem,24%)_1fr_minmax(14rem,27%)]" : visible.itinerary ? "grid-cols-[minmax(14rem,27%)_1fr]" : visible.details ? "grid-cols-[1fr_minmax(14rem,29%)]" : "grid-cols-1"}`}>
        {visible.itinerary && (
          <section className="min-h-0 overflow-y-auto border-r border-[#dce2df] bg-[#fbfcfb] max-md:hidden" aria-label="Itinerary preview">
            <div className="border-b border-[#e6eae8] px-4 py-4">
              <p className="text-[10px] font-bold uppercase text-[#d94d61]">Paris in five days</p>
              <h2 className="mt-1 text-xl font-semibold" style={{ fontFamily: "'Newsreader', serif" }}>A relaxed city circuit</h2>
              <p className="mt-1 text-xs text-[#66727d]">2 travelers · boutique stay · vegetarian</p>
            </div>
            {days.map((item) => (
              <button key={item.day} type="button" onClick={() => setActiveDay(item.day)} className={`block w-full border-b border-[#e6eae8] px-4 py-3 text-left ${activeDay === item.day ? "bg-white" : "hover:bg-white/70"}`}>
                <span className="flex items-center gap-2"><i className="h-2 w-2 rounded-full" style={{ background: item.color }} /><strong className="text-xs">Day {item.day}</strong><small className="ml-auto text-[10px] text-[#89928f]">6h 40m</small></span>
                <span className="mt-1.5 block text-sm font-semibold">{item.title}</span>
                <span className="mt-2 block text-[11px] leading-5 text-[#66727d]">{item.stops.join(" · ")}</span>
              </button>
            ))}
          </section>
        )}

        <section className="relative min-w-0 overflow-hidden bg-[#dce8e1]" aria-label="Map preview">
          <div className="absolute inset-0 opacity-75 [background-image:linear-gradient(30deg,transparent_47%,#b7c7be_48%,#b7c7be_49%,transparent_50%),linear-gradient(120deg,transparent_46%,#c3d0ca_47%,#c3d0ca_49%,transparent_50%)] [background-size:92px_92px]" />
          <div className="absolute left-4 top-4 flex rounded-md border border-white/80 bg-white/95 p-1 shadow-sm">
            {days.map((item) => <button key={item.day} type="button" onClick={() => setActiveDay(item.day)} className={`rounded px-2 py-1 text-[10px] font-bold ${activeDay === item.day ? "bg-[#172433] text-white" : "text-[#66727d]"}`}>Day {item.day}</button>)}
          </div>
          <div className="absolute left-[31%] top-[27%] grid h-8 w-8 place-items-center rounded-full bg-[#d94d61] text-xs font-bold text-white ring-4 ring-white">1</div>
          <div className="absolute left-[57%] top-[44%] grid h-8 w-8 place-items-center rounded-full bg-[#16867a] text-xs font-bold text-white ring-4 ring-white">2</div>
          <div className="absolute bottom-4 left-4 rounded-md border border-white bg-white/95 px-3 py-2 text-xs shadow-sm"><strong>Day {activeDay} circuit</strong><span className="ml-2 text-[#66727d]">8.4 km · 48 min travel</span></div>
          {!visible.map && <div className="absolute inset-0 grid place-items-center bg-[#f7f9f8]/95"><button type="button" onClick={() => toggle("map")} className="inline-flex items-center gap-2 text-sm font-semibold"><Map size={16} /> Show map</button></div>}
        </section>

        {visible.details && (
          <aside className="min-h-0 overflow-y-auto border-l border-[#dce2df] bg-[#fbfcfb] max-md:hidden" aria-label="Details preview">
            <div className="h-36 bg-[linear-gradient(145deg,#b9cbc3,#edf3ef)]" />
            <div className="p-4">
              <p className="text-[10px] font-bold uppercase text-[#16867a]">Day {activeDay} focus</p>
              <h2 className="mt-1 text-xl font-semibold" style={{ fontFamily: "'Newsreader', serif" }}>Louvre Museum</h2>
              <p className="mt-2 text-xs leading-5 text-[#66727d]">Timed-entry visit with the quieter Porte des Lions arrival and a practical lunch nearby.</p>
              <div className="mt-4 border-y border-[#e6eae8] py-3 text-xs"><div className="flex justify-between"><span className="text-[#66727d]">Booking</span><strong className="text-[#b26713]">Needs confirmation</strong></div><div className="mt-2 flex justify-between"><span className="text-[#66727d]">Planned time</span><strong>10:00 · 2h 30m</strong></div></div>
              <button type="button" onClick={() => setMenuOpen(!menuOpen)} className="mt-4 inline-flex h-8 items-center gap-2 rounded-md bg-[#172433] px-3 text-xs font-semibold text-white">Actions <MoreHorizontal size={14} /></button>
              {menuOpen && <div className="mt-2 w-44 rounded-md border border-[#dce2df] bg-white p-1 text-xs shadow-lg"><button className="block w-full rounded px-2 py-1.5 text-left hover:bg-[#edf1f0]">Change day</button><button className="block w-full rounded px-2 py-1.5 text-left hover:bg-[#edf1f0]">Open in Maps</button><button className="block w-full rounded px-2 py-1.5 text-left text-[#b43d50] hover:bg-[#fff0f2]">Remove stop</button></div>}
            </div>
          </aside>
        )}
      </div>

      <div className={`fixed inset-0 z-50 place-items-center p-6 ${visible.assistant ? "grid" : "hidden"}`}>
        <button type="button" onClick={() => toggle("assistant")} aria-label="Close Assistant" className="absolute inset-0 bg-[#172433]/35 backdrop-blur-[1px]" />
        <section role="dialog" aria-modal="true" aria-label="Trip Assistant" className="relative z-10 grid h-[calc(100vh-3rem)] max-h-[42rem] w-[calc(100vw-2rem)] max-w-[58rem] grid-cols-1 overflow-hidden rounded-lg bg-white shadow-[0_24px_70px_rgba(23,36,51,.3)] md:grid-cols-[15rem_1fr]">
          <aside className="hidden border-r border-[#dce2df] bg-[#f3f7f5] p-4 md:block"><Sparkles size={17} className="text-[#16867a]" /><h3 className="mt-3 text-sm font-semibold">Using your profile</h3><p className="mt-2 text-xs leading-5 text-[#66727d]">Balanced pace<br />Boutique stays<br />Vegetarian-friendly<br />No rushed mornings</p></aside>
          <div className="flex flex-col"><header className="flex h-12 items-center border-b border-[#e6eae8] px-4"><strong className="text-sm">Trip Assistant</strong><button type="button" onClick={() => toggle("assistant")} className="ml-auto grid h-8 w-8 place-items-center rounded-md hover:bg-[#edf1f0]" aria-label="Close Assistant"><X size={15} /></button></header><div className="flex-1 p-5"><div className="max-w-[80%] rounded-md bg-[#f0f4f2] p-3 text-sm leading-6">I can rebalance Day {activeDay}, compare another hotel, or check any booking before you commit.</div></div><div className="border-t border-[#e6eae8] p-3"><div className="rounded-md border border-[#d6ddda] px-3 py-2 text-sm text-[#89928f]">Ask about this trip...</div></div></div>
        </section>
      </div>
    </div>
  );
}

function ShellVisualRefreshLab() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("preview");
  const initial = variants.some((item) => item.id === requested) ? requested as Variant : "semantic";
  const [variant, setVariant] = useState<Variant>(initial);
  const fullPreview = params.has("preview");
  const choose = useCallback((id: string) => {
    if (variants.some((item) => item.id === id)) setVariant(id as Variant);
  }, []);

  if (fullPreview) return <main className="h-[100dvh] overflow-hidden"><Workspace variant={variant} /><a href="./shell-visual-refresh.html" className="fixed bottom-4 left-4 z-[80] inline-flex items-center gap-2 rounded-md bg-[#172433] px-3 py-2 text-xs font-semibold text-white shadow-lg"><ArrowLeft size={14} /> Exit full-size preview</a></main>;

  return (
    <main className="min-h-full bg-[#f4f6f5] px-4 py-7 sm:px-6 lg:px-8" style={{ fontFamily: "'DM Sans', sans-serif" }}>
      <div className="mx-auto max-w-[92rem]">
        <header className="flex flex-wrap items-end justify-between gap-5 border-b border-[#dce2df] pb-5">
          <div><div className="flex items-center gap-2 text-[#d94d61]"><Sparkles size={16} /><p className="text-[10px] font-bold uppercase">Active UX Lab</p></div><h1 className="mt-2 text-3xl font-semibold text-[#172433]" style={{ fontFamily: "'Newsreader', serif" }}>Workspace visual refresh</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-[#66727d]">Compare a quieter, more modern shell and decide how pane controls should communicate meaning. Production behavior is unchanged by this experiment.</p></div>
          <a href="./catalog.html" className="inline-flex items-center gap-2 text-xs font-semibold text-[#66727d]"><ArrowLeft size={14} /> Back to All Labs</a>
        </header>
        <LabScope labId="shell-visual-refresh" />
        <div className="mt-5 grid gap-3 md:grid-cols-3" role="tablist" aria-label="Shell control variants">
          {variants.map((item) => <button key={item.id} type="button" role="tab" aria-selected={variant === item.id} onClick={() => choose(item.id)} className={`rounded-md bg-white p-4 text-left shadow-sm ring-1 transition ${variant === item.id ? "ring-2 ring-[#d94d61]" : "ring-[#dce2df] hover:ring-[#aeb9b4]"}`}><strong className="text-sm text-[#172433]">{item.label}</strong><span className="mt-1.5 block text-xs leading-5 text-[#66727d]">{item.summary}</span></button>)}
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-semibold text-[#172433]">Live full-app preview · {variants.find((item) => item.id === variant)?.label}</p><a href={`?preview=${variant}`} className="inline-flex h-8 items-center gap-2 rounded-md bg-[#172433] px-3 text-xs font-semibold text-white">Open full-size preview</a></div>
        <section className="mt-2 h-[760px] max-h-[78vh] min-h-[620px] overflow-hidden rounded-md border border-[#dce2df] bg-white shadow-sm" aria-label="Interactive workspace refresh preview"><Workspace variant={variant} /></section>
        <section className="mt-6 grid gap-3 md:grid-cols-3">
          <article className="border-t-2 border-[#d94d61] bg-white p-4"><List size={16} className="text-[#d94d61]" /><h2 className="mt-3 text-sm font-semibold text-[#172433]">Meaning before position</h2><p className="mt-1 text-xs leading-5 text-[#66727d]">Itinerary uses a list symbol and Details uses an inspector symbol, avoiding left/right placement as meaning.</p></article>
          <article className="border-t-2 border-[#16867a] bg-white p-4"><EyeOff size={16} className="text-[#16867a]" /><h2 className="mt-3 text-sm font-semibold text-[#172433]">Stable surface state</h2><p className="mt-1 text-xs leading-5 text-[#66727d]">Active styling communicates visibility; controls never move when a pane is hidden.</p></article>
          <article className="border-t-2 border-[#d18a2d] bg-white p-4"><CalendarDays size={16} className="text-[#d18a2d]" /><h2 className="mt-3 text-sm font-semibold text-[#172433]">Quiet operational density</h2><p className="mt-1 text-xs leading-5 text-[#66727d]">A restrained palette and flatter hierarchy preserve scan speed without making the planner feel generic.</p></article>
        </section>
        <div className="mt-6"><DecisionCapture labId="shell-visual-refresh" labTitle="Workspace visual refresh" options={variants} activeOption={variant} onChoose={choose} /></div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><ShellVisualRefreshLab /></React.StrictMode>);
