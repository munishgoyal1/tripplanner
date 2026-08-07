// Four ways to run the same live plan. A is Lab 21's option D unchanged apart from the
// theme, B rewrites what it asks of you, and C and D re-open the question: C removes the
// demo entirely by planning your destination from the first keystroke, D turns the receipt
// log into decisions you can overrule. All four cover landing, first plan and shared trip.

import { Check, Gauge, Info, Loader2, Sparkles, Undo2, Wand2 } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Masthead, SiteFooter } from "../first-visit/pieces";
import {
  baseTrip,
  decisions,
  faq,
  signInMoments,
  trips,
  tripById,
  type StageTrip,
} from "./fixture";
import {
  BrowserFrame,
  ClockNote,
  Composer,
  HotelStrip,
  ItineraryFull,
  LinkPreview,
  ModeCompareCard,
  ModeLegend,
  PendingDayCard,
  PriceTableLive,
  ReceiptLine,
  SavingsRow,
  SectionHead,
  ShareBar,
  SignInCard,
  StageControls,
  StageDayCard,
  StageProgress,
  StaleNotice,
  Stat,
  TrustList,
  daysBuilt,
  toneStyles,
  useStageRun,
  type Tone,
} from "./pieces";

export type LivePlanOption = "asis" | "plain" | "yours" | "argue";
export type LivePlanSurface = "landing" | "first-plan" | "share";

interface Props {
  option: LivePlanOption;
  surface: LivePlanSurface;
  stress?: boolean;
  tone?: Tone;
}

export function LivePlan({ option, surface, stress = false, tone }: Props) {
  const resolved: Tone = tone ?? "light";

  if (surface === "first-plan") return <FirstPlanSurface option={option} tone={resolved} stress={stress} />;
  if (surface === "share") return <ShareSurface option={option} tone={resolved} stress={stress} />;

  if (option === "asis") return <LandingAsIs tone={resolved} stress={stress} />;
  if (option === "plain") return <LandingPlain tone={resolved} stress={stress} />;
  if (option === "yours") return <LandingYours tone={resolved} stress={stress} />;
  return <LandingArgue tone={resolved} stress={stress} />;
}

/* ------------------------------------------------------------------ shared sections */

function BelowTheFold({ trip, tone }: { trip: StageTrip; tone: Tone }) {
  return (
    <div className={tone === "dark" ? "bg-white" : ""}>
      <section className="border-b border-slate-200 px-6 py-8">
        <SectionHead
          tone="light"
          eyebrow="What you just watched"
          title="Every number carries its source"
          body="The stage is a live run of the same engine the workspace uses. Here is the receipt."
        />
        <div className="mt-4 grid gap-3 lg:grid-cols-[1.5fr_1fr]">
          <PriceTableLive trip={trip} tone="light" />
          <div className="space-y-3">
            <HotelStrip hotels={trip.hotels} tone="light" detail />
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200 px-6 py-8">
        <SectionHead
          tone="light"
          eyebrow="How it decided to move you"
          title="Flight, rail, road and coach — priced on every hop"
          body="A trip is decided by how you get between places. Each hop is compared door to door, and the options it rejected stay visible."
        />
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {trip.compares.map((compare) => (
            <ModeCompareCard key={compare.id} compare={compare} tone="light" />
          ))}
        </div>
      </section>

      <section className="border-b border-slate-200 px-6 py-8">
        <SectionHead tone="light" eyebrow="What it will and will not do" title="The honest edges" />
        <div className="mt-4 grid gap-5 lg:grid-cols-[1fr_1fr]">
          <TrustList tone="light" />
          <dl className="space-y-3">
            {faq.map((entry) => (
              <div key={entry.q}>
                <dt className="text-xs font-semibold text-ink">{entry.q}</dt>
                <dd className="mt-0.5 text-xs leading-relaxed text-slate-600">{entry.a}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
      <SiteFooter tone="light" />
    </div>
  );
}

function StageShell({
  tone,
  children,
}: {
  tone: Tone;
  children: ReactNode;
}) {
  if (tone === "dark") {
    return (
      <div className="relative overflow-hidden bg-[#080b11]">
        <div className="pointer-events-none absolute -left-24 -top-40 h-96 w-96 rounded-full bg-brand/25 blur-3xl" aria-hidden />
        <div className="pointer-events-none absolute -right-24 top-10 h-96 w-96 rounded-full bg-teal-400/20 blur-3xl" aria-hidden />
        {children}
      </div>
    );
  }
  return (
    <div className="relative overflow-hidden bg-[linear-gradient(180deg,#f8fafc_0,#ffffff_26rem)]">
      <div className="pointer-events-none absolute -left-24 -top-40 h-96 w-96 rounded-full bg-brand/10 blur-3xl" aria-hidden />
      <div className="pointer-events-none absolute -right-24 top-10 h-96 w-96 rounded-full bg-teal-300/20 blur-3xl" aria-hidden />
      {children}
    </div>
  );
}

function DayGrid({
  trip,
  tone,
  built,
  pendingLabel,
}: {
  trip: StageTrip;
  tone: Tone;
  built: number;
  pendingLabel?: string;
}) {
  const shown = Math.max(1, built);
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {trip.days.slice(0, shown).map((day) => (
        <StageDayCard key={day.day} day={day} tone={tone} />
      ))}
      {Array.from({ length: Math.max(0, trip.days.length - shown) }).map((_, index) => (
        <PendingDayCard
          key={`pending-${index}`}
          tone={tone}
          label={index === 0 && pendingLabel ? `${pendingLabel} day ${shown + 1} of ${trip.days.length}…` : undefined}
        />
      ))}
    </div>
  );
}

/* ------------------------------------------------- A · the stage exactly as it shipped */

function LandingAsIs({ tone, stress }: { tone: Tone; stress: boolean }) {
  const s = toneStyles[tone];
  const trip = baseTrip;
  const { step, running, replay } = useStageRun(trip.receipts.length);
  const built = running ? daysBuilt(trip.receipts, step) : trip.days.length;

  return (
    <div className={`min-h-full ${tone === "dark" ? "bg-[#080b11]" : "bg-white"}`}>
      <StageShell tone={tone}>
        <Masthead tone={tone} cta="Sign in" links={["Live plan", "How it works", "Destinations"]} />

        <section className="relative px-6 pb-8 pt-10" data-lab-change="Entry point">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase ${tone === "dark" ? "bg-emerald-400/15 text-emerald-300 ring-1 ring-emerald-400/30" : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"}`}>
              <span className={`h-1.5 w-1.5 rounded-full bg-emerald-500 ${running ? "animate-pulse" : ""}`} aria-hidden />
              {running ? "Planning live" : "Plan complete"}
            </span>
            <span className={`text-[11px] ${s.muted}`}>No account. No signup. This is the product running, not a video.</span>
          </div>

          <h1 className={`display mt-3 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl ${s.heading}`}>
            Watch it plan a trip.<br />Then take the plan.
          </h1>

          <div className="mt-6 grid gap-3 lg:grid-cols-[0.95fr_1.05fr]">
            <div className={`rounded-2xl p-4 ${s.panel} ${s.panelRing}`}>
              <div className="flex items-center justify-between gap-2">
                <p className={`font-mono text-[11px] uppercase tracking-wide ${s.muted}`}>agent · lisbon + porto · 6 days · 2 travellers</p>
                <StageControls tone={tone} running={false} onReplay={replay} onFinish={replay} />
              </div>
              <ol className="mt-3 space-y-1.5" aria-live="polite">
                {trip.receipts.slice(0, step).map((receipt) => (
                  <ReceiptLine key={receipt.at} receipt={receipt} tone={tone} />
                ))}
                {running && (
                  <li className={`flex items-center gap-2 font-mono text-[11px] ${s.muted}`}>
                    <Loader2 size={11} className="animate-spin" aria-hidden /> working…
                  </li>
                )}
              </ol>
              {stress && <div className="mt-3"><StaleNotice tone={tone} /></div>}
            </div>

            <div className="space-y-3">
              <DayGrid trip={trip} tone={tone} built={built} />
              <SavingsRow trip={trip} tone={tone} />
              <div className={`rounded-2xl p-4 ${s.panel} ${s.panelRing}`}>
                <p className={`text-sm font-semibold ${s.heading}`}>Make it yours</p>
                <p className={`mt-1 text-xs ${s.body}`}>Replace Lisbon with anywhere. It re-plans from scratch in front of you.</p>
                <div className="mt-3">
                  <Composer tone={tone} placeholder="Kyoto in April with a 6-year-old…" action="Take over" />
                </div>
              </div>
            </div>
          </div>
        </section>
      </StageShell>
      <BelowTheFold trip={trip} tone={tone} />
    </div>
  );
}

/* ---------------------------------------------------- B · the same stage, said plainly */

function LandingPlain({ tone, stress }: { tone: Tone; stress: boolean }) {
  const s = toneStyles[tone];
  const trip = baseTrip;
  const { step, running, replay, finish } = useStageRun(trip.receipts.length);
  const built = running ? daysBuilt(trip.receipts, step) : trip.days.length;

  return (
    <div className="min-h-full bg-white">
      <StageShell tone={tone}>
        <Masthead tone={tone} cta="Sign in" links={["See it plan", "How it works", "Destinations"]} />

        <section className="relative px-6 pb-8 pt-10" data-lab-change="Entry point">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-bold uppercase text-emerald-700 ring-1 ring-emerald-200">
              <span className={`h-1.5 w-1.5 rounded-full bg-emerald-500 ${running ? "animate-pulse" : ""}`} aria-hidden />
              {running ? "Planning a real trip now" : "Finished · 6 days planned"}
            </span>
            <span className={`text-[11px] ${s.muted}`}>Live, not a recording. Nothing here needs an account.</span>
          </div>

          <h1 className={`display mt-3 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl ${s.heading}`}>
            This is the planner working.<br />On a real trip, right now.
          </h1>
          <p className={`mt-2 max-w-2xl text-sm leading-relaxed ${s.body}`}>
            Six days across Lisbon and Porto — two hotels, a flight in, a train between the cities and
            a car for the one day that needs one. When it finishes, put in your own destination and it
            plans that instead.
          </p>

          <div className="mt-6 grid gap-3 lg:grid-cols-[0.95fr_1.05fr]">
            <div className={`rounded-2xl p-4 ${s.panel} ${s.panelRing}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className={`font-mono text-[11px] uppercase tracking-wide ${s.muted}`}>lisbon + porto · 6 days · 2 travellers</p>
                <StageControls tone={tone} running={running} onReplay={replay} onFinish={finish} />
              </div>
              <div className="mt-2.5">
                <StageProgress step={step} total={trip.receipts.length} tone={tone} />
              </div>
              <ol className="mt-3 space-y-1.5" aria-live="polite">
                {trip.receipts.slice(0, step).map((receipt) => (
                  <ReceiptLine key={receipt.at} receipt={receipt} tone={tone} />
                ))}
                {running && (
                  <li className={`flex items-center gap-2 font-mono text-[11px] ${s.muted}`}>
                    <Loader2 size={11} className="animate-spin" aria-hidden /> working…
                  </li>
                )}
              </ol>
              {stress && <div className="mt-3"><StaleNotice tone={tone} /></div>}
              <div className="mt-3">
                <ModeLegend tone={tone} />
              </div>
            </div>

            <div className="space-y-3">
              <DayGrid trip={trip} tone={tone} built={built} pendingLabel="Building" />
              <SavingsRow trip={trip} tone={tone} caption />
              <div className={`rounded-2xl p-4 ${s.panel} ${s.panelRing}`}>
                <p className={`text-sm font-semibold ${s.heading}`}>Plan yours instead of Lisbon</p>
                <p className={`mt-1 text-xs ${s.body}`}>
                  Same planner, your destination and dates. It takes about a minute and you can watch
                  it the same way.
                </p>
                <div className="mt-3">
                  <Composer
                    tone={tone}
                    placeholder="Kyoto in April with a 6-year-old…"
                    action="Plan mine"
                    note="No account needed. It never books anything and never holds your card."
                  />
                </div>
              </div>
            </div>
          </div>
        </section>
      </StageShell>
      <BelowTheFold trip={trip} tone={tone} />
    </div>
  );
}

/* ------------------------------------------ C · no demo at all — it plans yours at once */

function DestinationPicker({
  tone,
  current,
  onSelect,
}: {
  tone: Tone;
  current: string;
  onSelect: (id: string) => void;
}) {
  const s = toneStyles[tone];
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className={`text-[11px] font-semibold ${s.muted}`}>Try:</span>
      {trips.map((trip) => (
        <button
          key={trip.id}
          type="button"
          onClick={() => onSelect(trip.id)}
          aria-pressed={current === trip.id}
          className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition ${current === trip.id ? "bg-ink text-white" : `${s.chip} hover:opacity-80`}`}
        >
          {trip.label}
        </button>
      ))}
    </div>
  );
}

function LandingYours({ tone, stress }: { tone: Tone; stress: boolean }) {
  const s = toneStyles[tone];
  const [tripId, setTripId] = useState(baseTrip.id);
  const trip = tripById(tripId);
  const { step, running, replay, finish } = useStageRun(trip.receipts.length, trip.id);
  const built = running ? daysBuilt(trip.receipts, step) : trip.days.length;

  return (
    <div className="min-h-full bg-white">
      <StageShell tone={tone}>
        <Masthead tone={tone} cta="Sign in" links={["How it works", "Destinations", "What it costs"]} />

        <section className="relative px-6 pb-8 pt-10" data-lab-change="Entry point">
          <h1 className={`display max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl ${s.heading}`}>
            Where are you going?
          </h1>
          <p className={`mt-2 max-w-2xl text-sm leading-relaxed ${s.body}`}>
            Type it and the planner starts on your trip, not a sample. There is no demo to watch and
            nothing to take over — the plan below is already yours.
          </p>

          <div className="mt-5 max-w-2xl">
            <Composer
              tone={tone}
              value={trip.request}
              placeholder="Two cities in Italy, five days, under £1,400…"
              action="Plan it"
            />
            <div className="mt-2">
              <DestinationPicker tone={tone} current={tripId} onSelect={setTripId} />
            </div>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-brand/10 px-2.5 py-1 text-[11px] font-bold uppercase text-brand ring-1 ring-brand/20">
              <span className={`h-1.5 w-1.5 rounded-full bg-brand ${running ? "animate-pulse" : ""}`} aria-hidden />
              {running ? `Planning your ${trip.label} trip` : `Your ${trip.label} plan is ready`}
            </span>
            <StageControls tone={tone} running={running} onReplay={replay} onFinish={finish} skipLabel="Skip to the plan" />
            <ClockNote tone={tone}>Saved in this browser · no account yet</ClockNote>
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="space-y-3">
              <DayGrid trip={trip} tone={tone} built={built} pendingLabel="Building" />
              <SavingsRow trip={trip} tone={tone} caption />
            </div>
            <div className="space-y-3">
              <div className={`rounded-2xl p-4 ${s.panel} ${s.panelRing}`}>
                <div className="flex items-center justify-between gap-2">
                  <p className={`font-mono text-[11px] uppercase tracking-wide ${s.muted}`}>{trip.id} · {trip.dateRange} · {trip.travellers}</p>
                  <StageProgress step={step} total={trip.receipts.length} tone={tone} />
                </div>
                <ol className="mt-3 space-y-1.5" aria-live="polite">
                  {trip.receipts.slice(0, step).map((receipt) => (
                    <ReceiptLine key={receipt.at} receipt={receipt} tone={tone} />
                  ))}
                </ol>
                {stress && <div className="mt-3"><StaleNotice tone={tone} /></div>}
              </div>
              <HotelStrip hotels={trip.hotels} tone={tone} />
              {trip.compares.slice(0, 1).map((compare) => (
                <ModeCompareCard key={compare.id} compare={compare} tone={tone} />
              ))}
            </div>
          </div>
        </section>
      </StageShell>
      <BelowTheFold trip={trip} tone={tone} />
    </div>
  );
}

/* ------------------------------------------------ D · the decisions, and your right to overrule */

function DecisionCard({
  decision,
  tone,
  overruled,
  onOverrule,
  onUndo,
}: {
  decision: (typeof decisions)[number];
  tone: Tone;
  overruled: boolean;
  onOverrule: () => void;
  onUndo: () => void;
}) {
  const s = toneStyles[tone];
  return (
    <article className={`overflow-hidden rounded-2xl ${s.panel} ${s.panelRing}`}>
      <div className="p-3.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className={`text-[11px] font-mono ${s.muted}`}>{decision.at} · {decision.subject}</p>
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${overruled ? "bg-amber-50 text-amber-800 ring-1 ring-amber-200" : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"}`}>
            {overruled ? <Undo2 size={10} aria-hidden /> : <Check size={10} aria-hidden />}
            {overruled ? "You overruled this" : decision.verdict}
          </span>
        </div>
        <p className={`mt-1.5 text-sm leading-relaxed ${s.body}`}>{decision.reason}</p>
        <p className={`mt-1.5 inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold ${s.chip}`}>
          <Gauge size={11} aria-hidden /> Rule applied: {decision.rule}
        </p>
      </div>

      <ul className={`divide-y border-t ${tone === "dark" ? "divide-white/10 border-white/10" : "divide-slate-100 border-slate-200"}`}>
        {decision.options.map((option) => (
          <li key={option.label} className={`flex items-start gap-2 px-3.5 py-2 ${option.picked && !overruled ? (tone === "dark" ? "bg-emerald-400/[0.07]" : "bg-emerald-50/60") : ""}`}>
            <span className={`mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full ${option.picked && !overruled ? "bg-emerald-500" : tone === "dark" ? "bg-white/20" : "bg-slate-300"}`} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className={`text-[11px] font-semibold ${s.heading}`}>
                {option.label}
                <span className={`ml-1.5 font-normal ${s.muted}`}>{option.door} · {option.cost}</span>
              </p>
              <p className={`text-[11px] leading-relaxed ${s.muted}`}>{option.verdict}</p>
            </div>
          </li>
        ))}
      </ul>

      {overruled ? (
        <div className={`border-t px-3.5 py-3 ${tone === "dark" ? "border-white/10 bg-amber-400/[0.06]" : "border-slate-200 bg-amber-50/60"}`}>
          <p className={`text-xs font-semibold ${s.heading}`}>{decision.outcome.headline}</p>
          <ul className="mt-1.5 space-y-1">
            {decision.outcome.changes.map((change) => (
              <li key={change} className={`flex gap-1.5 text-[11px] leading-relaxed ${s.body}`}>
                <span className={`mt-1 h-1 w-1 shrink-0 rounded-full ${s.muted} bg-current`} aria-hidden />
                {change}
              </li>
            ))}
          </ul>
          <p className={`mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed ${tone === "dark" ? "text-amber-200" : "text-amber-800"}`}>
            <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
            {decision.outcome.warning}
          </p>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <span className={`text-sm font-bold tabular-nums ${s.heading}`}>{decision.outcome.total}</span>
            <span className={`text-[11px] font-semibold ${decision.outcome.delta.startsWith("−") ? "text-emerald-600" : "text-amber-700"}`}>{decision.outcome.delta}</span>
            <button type="button" onClick={onUndo} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${s.chip}`}>
              <Undo2 size={11} aria-hidden /> Put it back
            </button>
          </div>
        </div>
      ) : (
        <div className={`border-t px-3.5 py-2.5 ${tone === "dark" ? "border-white/10" : "border-slate-200"}`}>
          <button
            type="button"
            onClick={onOverrule}
            className="inline-flex items-center gap-1.5 rounded-xl bg-ink px-3 py-1.5 text-[12px] font-semibold text-white transition hover:opacity-90"
          >
            {decision.overrule}
          </button>
          <span className={`ml-2 text-[11px] ${s.muted}`}>It re-plans and tells you what that costs.</span>
        </div>
      )}
    </article>
  );
}

function useOverrule() {
  const [overruled, setOverruled] = useState<string | null>(null);
  const active = decisions.find((decision) => decision.id === overruled) ?? null;
  return { overruled, setOverruled, active };
}

function LandingArgue({ tone, stress }: { tone: Tone; stress: boolean }) {
  const s = toneStyles[tone];
  const trip = baseTrip;
  const { step, running, replay, finish } = useStageRun(decisions.length + 1);
  const shown = decisions.slice(0, step);
  const { overruled, setOverruled, active } = useOverrule();

  return (
    <div className="min-h-full bg-white">
      <StageShell tone={tone}>
        <Masthead tone={tone} cta="Sign in" links={["Its decisions", "How it works", "Destinations"]} />

        <section className="relative px-6 pb-8 pt-10" data-lab-change="Entry point">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-brand/10 px-2.5 py-1 text-[11px] font-bold uppercase text-brand ring-1 ring-brand/20">
              <Sparkles size={11} aria-hidden />
              {running ? "Showing its reasoning" : "3 decisions, all reversible"}
            </span>
            <StageControls tone={tone} running={running} onReplay={replay} onFinish={finish} skipLabel="Show all three" />
          </div>

          <h1 className={`display mt-3 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl ${s.heading}`}>
            It planned this trip.<br />Now argue with it.
          </h1>
          <p className={`mt-2 max-w-2xl text-sm leading-relaxed ${s.body}`}>
            Six days, two cities, two hotels and four ways of getting between them. Every judgement
            call is below with the options it rejected. Overrule any one and watch the plan re-settle
            — including what it costs you.
          </p>

          <div className="mt-6 grid gap-3 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="space-y-3">
              {shown.map((decision) => (
                <DecisionCard
                  key={decision.id}
                  decision={decision}
                  tone={tone}
                  overruled={overruled === decision.id}
                  onOverrule={() => setOverruled(decision.id)}
                  onUndo={() => setOverruled(null)}
                />
              ))}
              {running && (
                <div className={`flex items-center gap-2 rounded-2xl px-3.5 py-3 text-[11px] font-mono ${s.panel} ${s.panelRing} ${s.muted}`}>
                  <Loader2 size={12} className="animate-spin" aria-hidden /> working out the next decision…
                </div>
              )}
            </div>

            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2">
                <Stat tone={tone} label="Days" value="6" />
                <Stat tone={tone} label="Hotels" value="2" />
                <Stat tone={tone} label="Total" value={active ? active.outcome.total : trip.best} />
              </div>
              {active && (
                <p className="flex items-start gap-1.5 rounded-xl bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-800 ring-1 ring-amber-200">
                  <Undo2 size={12} className="mt-0.5 shrink-0" aria-hidden />
                  The plan below is re-settled around your change. {active.outcome.delta} against the
                  planner's own answer.
                </p>
              )}
              <DayGrid trip={trip} tone={tone} built={trip.days.length} />
              <HotelStrip hotels={trip.hotels} tone={tone} />
              {stress && <StaleNotice tone={tone} />}
              <div className={`rounded-2xl p-4 ${s.panel} ${s.panelRing}`}>
                <p className={`text-sm font-semibold ${s.heading}`}>Plan yours with the same rules</p>
                <p className={`mt-1 text-xs ${s.body}`}>
                  Whole-journey time over time in the air. Hotel cost plus the transport it forces.
                  Arrival at the gate, not at the town.
                </p>
                <div className="mt-3">
                  <Composer
                    tone={tone}
                    placeholder="Kyoto in April with a 6-year-old…"
                    action="Plan mine"
                    note="No account needed. Every decision it makes stays visible and reversible."
                  />
                </div>
              </div>
            </div>
          </div>
        </section>
      </StageShell>
      <BelowTheFold trip={trip} tone={tone} />
    </div>
  );
}

/* ------------------------------------------------------------- surface: the first plan */

const guestUrl = "tripplanner.app/g/8f2c-lisbon-porto";

function FirstPlanSurface({ option, tone, stress }: { option: LivePlanOption; tone: Tone; stress: boolean }) {
  const s = toneStyles[tone];
  const trip = baseTrip;
  const moment = signInMoments[option];
  const { overruled, setOverruled, active } = useOverrule();
  const decisionLed = option === "argue";

  return (
    <div className={`min-h-full ${tone === "dark" ? "bg-[#080b11]" : "bg-slate-50"}`}>
      <Masthead tone={tone} cta="Sign in" links={["Your trips", "How it works", "Destinations"]} />
      <div className="px-6 py-6">
        <BrowserFrame url={guestUrl} tone={tone}>
          <div className={`p-4 ${tone === "dark" ? "bg-[#080b11]" : "bg-white"}`}>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className={`text-[10px] font-bold uppercase ${s.accent}`}>Your plan · guest link, kept 30 days</p>
                <h2 className={`display mt-0.5 text-2xl font-semibold ${s.heading}`}>{trip.title}</h2>
                <p className={`mt-0.5 text-xs ${s.body}`}>{trip.dateRange} · {trip.travellers} · {trip.summary}</p>
              </div>
              <div className="text-right">
                <p className={`text-2xl font-bold tabular-nums ${s.heading}`}>{active ? active.outcome.total : trip.best}</p>
                <p className={`text-[11px] ${s.muted}`}>down from {trip.first}</p>
              </div>
            </div>

            {stress && <div className="mt-3"><StaleNotice tone={tone} /></div>}

            <div className="mt-4 grid gap-3 lg:grid-cols-[1.15fr_0.85fr]">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className={`text-xs font-bold uppercase ${s.muted}`}>The six days</p>
                  <ModeLegend tone={tone} />
                </div>
                <ItineraryFull trip={trip} tone={tone} />
              </div>

              <div className="space-y-3">
                <SavingsRow trip={trip} tone={tone} caption />
                <div>
                  <p className={`mb-1.5 text-xs font-bold uppercase ${s.muted}`}>Where you sleep</p>
                  <HotelStrip hotels={trip.hotels} tone={tone} detail />
                </div>

                {decisionLed ? (
                  <div className="space-y-2">
                    <p className={`text-xs font-bold uppercase ${s.muted}`}>Its decisions, still reversible</p>
                    {decisions.map((decision) => (
                      <DecisionCard
                        key={decision.id}
                        decision={decision}
                        tone={tone}
                        overruled={overruled === decision.id}
                        onOverrule={() => setOverruled(decision.id)}
                        onUndo={() => setOverruled(null)}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className={`text-xs font-bold uppercase ${s.muted}`}>How it moved you</p>
                    {trip.compares.map((compare) => (
                      <ModeCompareCard key={compare.id} compare={compare} tone={tone} />
                    ))}
                  </div>
                )}

                <PriceTableLive trip={trip} tone={tone} compact />
                <SignInCard moment={moment} tone={tone} />
              </div>
            </div>
          </div>
        </BrowserFrame>
      </div>
      <SiteFooter tone={tone} />
    </div>
  );
}

/* ------------------------------------------------------------ surface: the shared trip */

function ShareSurface({ option, tone, stress }: { option: LivePlanOption; tone: Tone; stress: boolean }) {
  const s = toneStyles[tone];
  const trip = baseTrip;
  const decisionLed = option === "argue";
  const yoursLed = option === "yours";

  return (
    <div className={`min-h-full ${tone === "dark" ? "bg-[#080b11]" : "bg-white"}`}>
      <Masthead tone={tone} cta="Plan your own" links={["How it works", "Destinations", "What it costs"]} />

      <section className={`border-b px-6 py-6 ${s.divider}`}>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className={`text-[10px] font-bold uppercase ${s.accent}`}>Shared plan · read only</p>
            <h1 className={`display mt-0.5 text-3xl font-semibold ${s.heading}`}>{trip.title}</h1>
            <p className={`mt-1 text-sm ${s.body}`}>{trip.dateRange} · {trip.travellers} · {trip.summary}</p>
          </div>
          <div className="text-right">
            <p className={`text-3xl font-bold tabular-nums ${s.heading}`}>{trip.best}</p>
            <p className={`text-[11px] ${s.muted}`}>{trip.sources} · saved {trip.saved}</p>
          </div>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-4">
          <Stat tone={tone} label="Cities" value="Lisbon, Porto" />
          <Stat tone={tone} label="Hotels" value="2 · H1 and H2" />
          <Stat tone={tone} label="How you move" value="Flight, rail, road, tram" />
          <Stat tone={tone} label="Places" value="21 planned" />
        </div>
        {stress && <div className="mt-3"><StaleNotice tone={tone} /></div>}
      </section>

      <section className="border-b px-6 py-6 border-slate-200">
        <div className="grid gap-3 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <SectionHead tone={tone} eyebrow="The plan" title="Six days, two cities" />
              <ModeLegend tone={tone} />
            </div>
            <ItineraryFull trip={trip} tone={tone} />
          </div>
          <div className="space-y-3">
            <HotelStrip hotels={trip.hotels} tone={tone} detail />
            <PriceTableLive trip={trip} tone={tone} compact />
            <ShareBar trip={trip} tone={tone} />
            <div>
              <p className={`mb-1.5 text-xs font-bold uppercase ${s.muted}`}>What a message app renders</p>
              <LinkPreview trip={trip} />
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200 px-6 py-6">
        <SectionHead
          tone={tone}
          eyebrow={decisionLed ? "Why it looks like this" : "How it moved you"}
          title={decisionLed ? "The decisions travel with the link" : "Flight, rail, road and coach, priced on every hop"}
          body={
            decisionLed
              ? "This is the part no other shared itinerary carries: whoever opens the link can see why the train beat the flight, and what the planner refused."
              : yoursLed
                ? "Anyone opening this link sees the same comparison the planner ran, with the rejected options intact."
                : "Each hop was compared door to door. The losing options stay visible so the choice can be checked."
          }
        />
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {decisionLed
            ? decisions.map((decision) => (
                <div key={decision.id} className={`rounded-xl p-3 ${s.panel} ${s.panelRing}`}>
                  <p className={`text-xs font-semibold ${s.heading}`}>{decision.subject}</p>
                  <p className={`mt-0.5 inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700`}>
                    <Check size={10} aria-hidden /> {decision.verdict}
                  </p>
                  <p className={`mt-1.5 text-[11px] leading-relaxed ${s.body}`}>{decision.reason}</p>
                  <p className={`mt-1.5 inline-flex items-center gap-1 text-[11px] ${s.muted}`}>
                    <Gauge size={11} aria-hidden /> {decision.rule}
                  </p>
                </div>
              ))
            : trip.compares.map((compare) => <ModeCompareCard key={compare.id} compare={compare} tone={tone} />)}
        </div>
      </section>

      <section className="px-6 py-6">
        <div className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4 ${s.panel} ${s.panelRing}`}>
          <div>
            <p className={`flex items-center gap-1.5 text-sm font-semibold ${s.heading}`}>
              <Wand2 size={15} aria-hidden /> Plan your own version of this
            </p>
            <p className={`mt-0.5 text-xs ${s.body}`}>
              Copy it and change the dates, the cities or who is coming. No account needed to start.
            </p>
          </div>
          <div className="min-w-[18rem] flex-1">
            <Composer tone={tone} size="sm" placeholder="Lisbon and Porto, but in April…" action="Plan mine" />
          </div>
        </div>
      </section>
      <SiteFooter tone={tone} />
    </div>
  );
}
