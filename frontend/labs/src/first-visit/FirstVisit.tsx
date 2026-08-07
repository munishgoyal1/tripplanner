// Four production-scale first-visit experiences plus today's baseline. Each option renders
// three surfaces — the landing page, the first-plan handoff including the sign-in moment,
// and the public shared-trip page — because the first visit is not one screen.

import { ArrowRight, Check, Clock3, Globe, Link2, Loader2, RotateCcw, Sparkles, TriangleAlert, UserRound } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import {
  agentReceipts,
  capabilities,
  examplePrompts,
  faq,
  product,
  proof,
  sampleDays,
  signInMoments,
  steps,
} from "./fixture";
import {
  CheckLine,
  Composer,
  DayCard,
  DestinationGrid,
  Masthead,
  PriceTable,
  PromptChips,
  ProofMap,
  SavingsBar,
  SectionHead,
  SiteFooter,
  TrustList,
  toneStyles,
  type Tone,
} from "./pieces";
import { trip } from "../shared/tripFixture";

export type FirstVisitOption = "prompt" | "magazine" | "intake" | "stage" | "today";
export type FirstVisitSurface = "landing" | "first-plan" | "share";

const NAV_LINKS = ["How it works", "Sample trip", "Destinations", "What it costs"];

interface Props {
  option: FirstVisitOption;
  surface: FirstVisitSurface;
  stress?: boolean;
}

export function FirstVisit({ option, surface, stress = false }: Props) {
  const tone: Tone = option === "stage" ? "dark" : "light";

  if (option === "today") {
    if (surface === "landing") return <TodayLanding />;
    if (surface === "first-plan") return <TodayFirstPlan />;
    return <TodayShare />;
  }

  if (surface === "first-plan") return <FirstPlan option={option} tone={tone} stress={stress} />;
  if (surface === "share") return <SharePage option={option} tone={tone} stress={stress} />;

  if (option === "prompt") return <LandingPrompt stress={stress} />;
  if (option === "magazine") return <LandingMagazine stress={stress} />;
  if (option === "intake") return <LandingIntake stress={stress} />;
  return <LandingStage stress={stress} />;
}

function StaleNotice({ tone }: { tone: Tone }) {
  return (
    <p className={`flex items-start gap-1.5 rounded-lg px-3 py-2 text-[11px] leading-relaxed ${tone === "dark" ? "bg-amber-400/10 text-amber-200 ring-1 ring-amber-400/30" : "bg-amber-50 text-amber-800 ring-1 ring-amber-200"}`}>
      <TriangleAlert size={13} className="mt-0.5 shrink-0" aria-hidden />
      Flight prices from Duffel are 22 minutes old and one hotel rate could not be re-checked. The
      page says so instead of showing a number it cannot defend.
    </p>
  );
}

/* ------------------------------------------------------------------ A · Prompt-first */

function LandingPrompt({ stress }: { stress: boolean }) {
  const tone: Tone = "light";
  const s = toneStyles[tone];
  return (
    <div className="min-h-full bg-white">
      <Masthead tone={tone} links={NAV_LINKS} />

      <section className="border-b border-slate-200 bg-[linear-gradient(180deg,#fff_0,#fff7f8_100%)] px-6 py-12 text-center">
        <p className="text-[11px] font-bold uppercase tracking-wide text-brand">Plans, not search results</p>
        <h1 className="display mx-auto mt-2 max-w-3xl text-4xl font-semibold leading-tight text-ink sm:text-5xl">
          {product.promise}
        </h1>
        <p className={`mx-auto mt-3 max-w-2xl text-[15px] leading-relaxed ${s.body}`}>{product.subPromise}</p>

        <div className="mx-auto mt-6 max-w-2xl text-left" data-lab-change="Entry point">
          <Composer
            tone={tone}
            placeholder="Where are you going, when, and who with?"
            note={<span className="flex items-center gap-1.5"><Check size={12} aria-hidden /> No account needed. Your trip stays in this browser until you sign in.</span>}
          />
          <PromptChips tone={tone} prompts={examplePrompts} />
        </div>
      </section>

      <section className="border-b border-slate-200 px-6 py-8">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <SectionHead
            tone={tone}
            eyebrow="Made 6 minutes ago, not a mock-up"
            title={proof.headline}
            body={proof.subline}
          />
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">{proof.pricesCheckedAt}</span>
        </div>
        {stress && <div className="mt-3"><StaleNotice tone={tone} /></div>}
        <div className="mt-4 grid gap-3 lg:grid-cols-4">
          {sampleDays.map((_, index) => (
            <DayCard key={index} dayIndex={index} tone={tone} stops={3} />
          ))}
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-[1.4fr_1fr]">
          <PriceTable tone={tone} />
          <div className="space-y-3">
            <ProofMap tone={tone} />
            <SavingsBar tone={tone} />
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200 px-6 py-8">
        <SectionHead tone={tone} eyebrow="What comes back" title="Three promises, in this order" />
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {capabilities.map((capability) => (
            <article key={capability.title} className="rounded-xl bg-white p-4 shadow-card ring-1 ring-slate-200">
              <Sparkles size={16} className="text-brand" aria-hidden />
              <p className="mt-2 text-sm font-semibold text-ink">{capability.title}</p>
              <p className={`mt-1 text-xs leading-relaxed ${s.body}`}>{capability.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="border-b border-slate-200 px-6 py-8">
        <SectionHead tone={tone} eyebrow="How it works" title="Three steps, one of them yours" />
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {steps.map((step) => (
            <div key={step.step} className="rounded-xl border border-slate-200 p-4">
              <span className="grid h-6 w-6 place-items-center rounded-full bg-ink text-[11px] font-bold text-white">{step.step}</span>
              <p className="mt-2 text-sm font-semibold text-ink">{step.title}</p>
              <p className={`mt-1 text-xs leading-relaxed ${s.body}`}>{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      <TrustAndFaq tone={tone} />
      <section className="px-6 py-10 text-center">
        <h2 className="display text-2xl font-semibold text-ink">Try it with your next trip</h2>
        <div className="mx-auto mt-4 max-w-xl text-left">
          <Composer tone={tone} placeholder="Where are you going, when, and who with?" />
        </div>
      </section>
      <SiteFooter tone={tone} />
    </div>
  );
}

/* --------------------------------------------------------------- B · Proof-first */

function LandingMagazine({ stress }: { stress: boolean }) {
  const tone: Tone = "light";
  const s = toneStyles[tone];
  return (
    <div className="relative min-h-full bg-white pb-16">
      <Masthead tone={tone} links={["Lisbon", "Kyoto", "Amalfi", "All destinations", "How it works"]} />

      <section className="relative overflow-hidden" data-lab-change="Proof before the ask">
        <div
          className="h-72 w-full"
          style={{ background: "linear-gradient(115deg,#0f766e 0%,#0369a1 38%,#f43f5e 100%)" }}
          aria-hidden
        />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(0,0,0,0.05)_0%,rgba(0,0,0,0.55)_100%)]" aria-hidden />
        <div className="absolute inset-x-0 bottom-0 px-6 pb-6">
          <p className="text-[11px] font-bold uppercase tracking-wide text-white/80">Plan of the week · unedited</p>
          <h1 className="display mt-1 max-w-3xl text-3xl font-semibold leading-tight text-white sm:text-4xl">
            {proof.headline}. Read it before you type anything.
          </h1>
          <p className="mt-2 max-w-2xl text-[13px] text-white/85">{proof.subline} · {proof.builtAt}</p>
        </div>
      </section>

      <section className="px-6 py-8">
        <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
          <div>
            <SectionHead tone={tone} eyebrow="The actual plan" title="Four days, placed by the engine" body="Times, transfers and opening hours are the plan's, not a writer's." />
            {stress && <div className="mt-3"><StaleNotice tone={tone} /></div>}
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {sampleDays.map((_, index) => (
                <DayCard key={index} dayIndex={index} tone={tone} stops={4} />
              ))}
            </div>
          </div>
          <div className="space-y-3">
            <ProofMap tone={tone} height="h-52" />
            <SavingsBar tone={tone} />
            <div className="rounded-xl border border-slate-200 p-3">
              <p className="text-xs font-semibold text-ink">Why this hotel</p>
              <p className={`mt-1 text-xs leading-relaxed ${s.body}`}>
                Alfama over Baixa: every anchor sight lands inside a 20-minute walk, which removes
                three taxi legs and one 78-minute transfer that broke the pace rule.
              </p>
              <ul className="mt-2 space-y-1">
                <CheckLine tone={tone}>Sintra rejected on day 2 — transfer too long</CheckLine>
                <CheckLine tone={tone}>Dinner kept before 20:00 on all four nights</CheckLine>
              </ul>
            </div>
          </div>
        </div>
        <div className="mt-4">
          <PriceTable tone={tone} />
        </div>
      </section>

      <section className="border-t border-slate-200 px-6 py-8">
        <SectionHead tone={tone} eyebrow="Start from a plan" title="Six destinations with a plan already built" body="Each one is its own page: readable without an account, indexable, and one click from becoming yours." />
        <div className="mt-4">
          <DestinationGrid tone={tone} />
        </div>
      </section>

      <TrustAndFaq tone={tone} />
      <SiteFooter tone={tone} />

      <div className="sticky bottom-0 left-0 right-0 border-t border-slate-200 bg-white/95 px-6 py-3 shadow-pop backdrop-blur" data-lab-change="Entry point">
        <div className="mx-auto flex max-w-3xl items-center gap-3">
          <p className="hidden shrink-0 text-xs font-semibold text-ink sm:block">Plan yours</p>
          <div className="min-w-0 flex-1">
            <Composer tone={tone} size="sm" placeholder="Lisbon in October for two, food-led…" action="Plan it" />
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- C · Guided intake */

function LandingIntake({ stress }: { stress: boolean }) {
  const tone: Tone = "light";
  const s = toneStyles[tone];
  const [where, setWhere] = useState("Lisbon");
  const [month, setMonth] = useState("October");
  const [nights, setNights] = useState(4);
  const [adults, setAdults] = useState(2);
  const [budget, setBudget] = useState("Mid");
  const [pace, setPace] = useState("Slow mornings");

  const sentence = `${nights} nights in ${where} in ${month} for ${adults} ${adults === 1 ? "traveller" : "travellers"}, ${budget.toLowerCase()} budget, ${pace.toLowerCase()}.`;

  return (
    <div className="min-h-full bg-white">
      <Masthead tone={tone} links={NAV_LINKS} />

      <section className="border-b border-slate-200 bg-[linear-gradient(180deg,#fff_0,#f6f8fa_100%)] px-6 py-10">
        <div className="grid gap-6 lg:grid-cols-[1.05fr_1fr]">
          <div data-lab-change="Entry point">
            <p className="text-[11px] font-bold uppercase tracking-wide text-brand">Four answers, one plan</p>
            <h1 className="display mt-2 max-w-xl text-3xl font-semibold leading-tight text-ink sm:text-4xl">
              You don't have to know what to type.
            </h1>
            <p className={`mt-2 max-w-xl text-sm leading-relaxed ${s.body}`}>
              Answer what you know. Skip what you don't — everything here is optional, and the
              planner fills the gaps with what it can defend.
            </p>

            <div className="mt-5 rounded-2xl bg-white p-4 shadow-pop ring-1 ring-slate-200">
              <Field label="Where">
                <div className="flex flex-wrap gap-1.5">
                  {["Lisbon", "Kyoto", "Amalfi Coast", "Somewhere warm"].map((city) => (
                    <Chip key={city} active={where === city} onClick={() => setWhere(city)}>{city}</Chip>
                  ))}
                  <span className="rounded-full px-2.5 py-1 text-[11px] font-medium text-slate-400 ring-1 ring-slate-200">or type a place…</span>
                </div>
              </Field>

              <Field label="When">
                <div className="flex flex-wrap items-center gap-1.5">
                  {["April", "June", "October", "Flexible"].map((value) => (
                    <Chip key={value} active={month === value} onClick={() => setMonth(value)}>{value}</Chip>
                  ))}
                  <span className="ml-1 inline-flex items-center gap-1 rounded-full ring-1 ring-slate-200">
                    <Stepper label="Fewer nights" onClick={() => setNights((n) => Math.max(2, n - 1))}>−</Stepper>
                    <span className="min-w-[4.5rem] text-center text-[11px] font-semibold tabular-nums text-ink">{nights} nights</span>
                    <Stepper label="More nights" onClick={() => setNights((n) => Math.min(21, n + 1))}>+</Stepper>
                  </span>
                </div>
              </Field>

              <Field label="Who">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1 rounded-full ring-1 ring-slate-200">
                    <Stepper label="Fewer adults" onClick={() => setAdults((n) => Math.max(1, n - 1))}>−</Stepper>
                    <span className="min-w-[4.5rem] text-center text-[11px] font-semibold tabular-nums text-ink">{adults} adults</span>
                    <Stepper label="More adults" onClick={() => setAdults((n) => Math.min(8, n + 1))}>+</Stepper>
                  </span>
                  <Chip active={false} onClick={() => undefined}>+ Add children</Chip>
                  <span className={`text-[11px] ${s.muted}`}>Ages change opening hours and queue rules, so it asks once.</span>
                </div>
              </Field>

              <Field label="Budget and pace">
                <div className="flex flex-wrap gap-1.5">
                  {["Lean", "Mid", "Generous"].map((value) => (
                    <Chip key={value} active={budget === value} onClick={() => setBudget(value)}>{value}</Chip>
                  ))}
                  <span className="mx-1 h-5 w-px bg-slate-200" aria-hidden />
                  {["Slow mornings", "Balanced", "See everything"].map((value) => (
                    <Chip key={value} active={pace === value} onClick={() => setPace(value)}>{value}</Chip>
                  ))}
                </div>
              </Field>

              <div className="mt-4 rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
                <p className="text-[10px] font-bold uppercase text-slate-400">This is what it will read</p>
                <p className="mt-1 text-[13px] font-medium text-ink">{sentence}</p>
              </div>

              <div className="mt-3">
                <Composer tone={tone} value={sentence} placeholder={sentence} action="Plan this trip" note="No account needed. Edit any of it once the plan exists." />
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
              <p className="text-sm font-semibold text-ink">What it decides for you</p>
              <ul className="mt-2 space-y-1.5">
                <CheckLine tone={tone}>Which neighbourhood keeps every anchor sight inside a 20-minute walk</CheckLine>
                <CheckLine tone={tone}>Which day each sight lands on, given opening hours and the forecast</CheckLine>
                <CheckLine tone={tone}>Which flight pairing is worth €66 more, and which is not</CheckLine>
                <CheckLine tone={tone}>What the whole trip costs before you commit to any of it</CheckLine>
              </ul>
            </div>
            {stress && <StaleNotice tone={tone} />}
            <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-ink">{proof.headline}</p>
                <span className="text-[11px] text-slate-400">{proof.builtAt}</span>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <DayCard dayIndex={0} tone={tone} stops={3} />
                <DayCard dayIndex={2} tone={tone} stops={3} />
              </div>
              <div className="mt-3">
                <SavingsBar tone={tone} />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200 px-6 py-8">
        <SectionHead tone={tone} eyebrow="The sample in full" title="Every price, with its source" />
        <div className="mt-4 grid gap-3 lg:grid-cols-[1.4fr_1fr]">
          <PriceTable tone={tone} />
          <ProofMap tone={tone} height="h-full" />
        </div>
      </section>

      <TrustAndFaq tone={tone} />
      <SiteFooter tone={tone} />
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="border-b border-slate-100 py-2.5 last:border-0">
      <p className="text-[10px] font-bold uppercase text-slate-400">{label}</p>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition ${
        active ? "bg-ink text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-slate-300"
      }`}
    >
      {children}
    </button>
  );
}

function Stepper({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" aria-label={label} onClick={onClick} className="h-6 w-6 rounded-full text-sm font-semibold text-slate-500 hover:bg-slate-100">
      {children}
    </button>
  );
}

/* ------------------------------------------------------------ D · Live agent stage */

function useStageProgress(total: number) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (step >= total) return;
    const timer = window.setTimeout(() => setStep((value) => value + 1), step === 0 ? 400 : 850);
    return () => window.clearTimeout(timer);
  }, [step, total]);
  return { step, replay: () => setStep(0) };
}

function LandingStage({ stress }: { stress: boolean }) {
  const tone: Tone = "dark";
  const s = toneStyles[tone];
  const { step, replay } = useStageProgress(agentReceipts.length);
  const receipts = agentReceipts.slice(0, step);
  const running = step < agentReceipts.length;
  // Every card must be filled by the time the run says "complete", or a finished plan
  // reads as a stuck one.
  const daysShown = running
    ? Math.min(sampleDays.length, Math.floor((step * sampleDays.length) / agentReceipts.length))
    : sampleDays.length;

  return (
    <div className="min-h-full bg-[#080b11]">
      <div className="relative overflow-hidden">
        <div className="pointer-events-none absolute -left-24 -top-40 h-96 w-96 rounded-full bg-brand/25 blur-3xl" aria-hidden />
        <div className="pointer-events-none absolute -right-24 top-10 h-96 w-96 rounded-full bg-teal-400/20 blur-3xl" aria-hidden />

        <Masthead tone={tone} cta="Sign in" links={["Live plan", "How it works", "Destinations"]} />

        <section className="relative px-6 pb-8 pt-10" data-lab-change="Entry point">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/15 px-2.5 py-1 text-[11px] font-bold uppercase text-emerald-300 ring-1 ring-emerald-400/30">
              <span className={`h-1.5 w-1.5 rounded-full bg-emerald-400 ${running ? "animate-pulse" : ""}`} aria-hidden />
              {running ? "Planning live" : "Plan complete"}
            </span>
            <span className={`text-[11px] ${s.muted}`}>No account. No signup. This is the product running, not a video.</span>
          </div>

          <h1 className="display mt-3 max-w-3xl text-4xl font-semibold leading-tight text-white sm:text-5xl">
            Watch it plan a trip.<br />Then take the plan.
          </h1>

          <div className="mt-6 grid gap-3 lg:grid-cols-[0.95fr_1.05fr]">
            <div className={`rounded-2xl p-4 ${s.panel} ${s.panelRing}`}>
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-[11px] uppercase tracking-wide text-slate-400">agent · lisbon · 4 days · 2 travellers</p>
                <button
                  type="button"
                  onClick={replay}
                  className="inline-flex items-center gap-1 rounded-full bg-white/10 px-2 py-1 text-[11px] font-semibold text-slate-200 hover:bg-white/20"
                >
                  <RotateCcw size={11} aria-hidden /> Replay
                </button>
              </div>
              <ol className="mt-3 space-y-1.5" aria-live="polite">
                {receipts.map((receipt) => (
                  <li key={receipt.at} className="flex gap-2 font-mono text-[11px] leading-relaxed">
                    <span className="shrink-0 text-emerald-300/80">{receipt.at}</span>
                    <span className="text-slate-300">{receipt.text}</span>
                  </li>
                ))}
                {running && (
                  <li className="flex items-center gap-2 font-mono text-[11px] text-slate-500">
                    <Loader2 size={11} className="animate-spin" aria-hidden /> working…
                  </li>
                )}
              </ol>
              {stress && (
                <p className="mt-3 rounded-lg bg-amber-400/10 px-3 py-2 font-mono text-[11px] text-amber-200 ring-1 ring-amber-400/30">
                  1:31 · Duffel timed out on the return leg. Kept the 22-minute-old price and marked it stale rather than guessing.
                </p>
              )}
            </div>

            <div className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-2">
                {sampleDays.slice(0, Math.max(1, daysShown)).map((_, index) => (
                  <DayCard key={index} dayIndex={index} tone={tone} stops={3} />
                ))}
                {daysShown < sampleDays.length &&
                  Array.from({ length: sampleDays.length - Math.max(1, daysShown) }).map((_, index) => (
                    <div key={`pending-${index}`} className="rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/5">
                      <div className="h-2.5 w-24 rounded bg-white/10" />
                      <div className="mt-2 space-y-1.5">
                        <div className="h-2 w-full rounded bg-white/5" />
                        <div className="h-2 w-4/5 rounded bg-white/5" />
                        <div className="h-2 w-3/5 rounded bg-white/5" />
                      </div>
                    </div>
                  ))}
              </div>
              <SavingsBar tone={tone} />
              <div className={`rounded-2xl p-4 ${s.panel} ${s.panelRing}`}>
                <p className="text-sm font-semibold text-white">Make it yours</p>
                <p className={`mt-1 text-xs ${s.body}`}>Replace Lisbon with anywhere. It re-plans from scratch in front of you.</p>
                <div className="mt-3">
                  <Composer tone={tone} placeholder="Kyoto in April with a 6-year-old…" action="Take over" />
                </div>
                <PromptChips tone={tone} prompts={examplePrompts.slice(0, 3)} />
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* The stage is the hero, not the whole site. Everything a first-time visitor needs to
          trust the thing lives below it, in daylight. */}
      <div className="bg-white">
        <section className="border-b border-slate-200 px-6 py-8">
          <SectionHead tone="light" eyebrow="What you just watched" title="Every number carries its source" body="The stage is a live run of the same engine. Here is the receipt." />
          <div className="mt-4 grid gap-3 lg:grid-cols-[1.4fr_1fr]">
            <PriceTable tone="light" />
            <div className="space-y-3">
              <ProofMap tone="light" />
              <div className="rounded-xl border border-slate-200 p-3">
                <p className="text-xs font-semibold text-ink">Where the €353 came from</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-600">
                  A second flight pairing at €412 instead of €478, and a re-priced stay after the
                  dates locked. It kept comparing until the whole-trip total stopped falling.
                </p>
              </div>
            </div>
          </div>
        </section>
        <section className="border-b border-slate-200 px-6 py-8">
          <SectionHead tone="light" eyebrow="Start from a plan" title="Or take one that already exists" />
          <div className="mt-4">
            <DestinationGrid tone="light" />
          </div>
        </section>
        <TrustAndFaq tone="light" />
        <SiteFooter tone="light" />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ shared sections */

function TrustAndFaq({ tone }: { tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <section className={`border-b px-6 py-8 ${s.divider}`}>
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <SectionHead tone={tone} eyebrow="What we do and don't do" title="The boundaries, on the front page" />
          <div className="mt-4">
            <TrustList tone={tone} columns={1} />
          </div>
        </div>
        <div>
          <SectionHead tone={tone} eyebrow="Asked first" title="Four questions before you type" />
          <dl className="mt-4 space-y-3">
            {faq.map((entry) => (
              <div key={entry.q}>
                <dt className={`text-sm font-semibold ${s.heading}`}>{entry.q}</dt>
                <dd className={`mt-0.5 text-xs leading-relaxed ${s.body}`}>{entry.a}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------- first plan and sign-in */

function BrowserFrame({ url, tone, children }: { url: string; tone: Tone; children: ReactNode }) {
  const dark = tone === "dark";
  return (
    <div className={`overflow-hidden rounded-xl ${dark ? "bg-[#0d1218] ring-1 ring-white/10" : "bg-white ring-1 ring-slate-200"} shadow-card`}>
      <div className={`flex items-center gap-2 border-b px-3 py-1.5 ${dark ? "border-white/10" : "border-slate-200"}`}>
        <span className="flex gap-1" aria-hidden>
          {["#f87171", "#fbbf24", "#34d399"].map((color) => (
            <span key={color} className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
          ))}
        </span>
        <span className={`flex min-w-0 flex-1 items-center gap-1 truncate rounded px-2 py-0.5 text-[10px] ${dark ? "bg-white/5 text-slate-400" : "bg-slate-100 text-slate-500"}`}>
          <Globe size={9} aria-hidden /> {url}
        </span>
      </div>
      {children}
    </div>
  );
}

function FirstPlan({ option, tone, stress }: { option: Exclude<FirstVisitOption, "today">; tone: Tone; stress: boolean }) {
  const s = toneStyles[tone];
  const moment = signInMoments[option];
  return (
    <div className={`min-h-full px-6 py-6 ${tone === "dark" ? "bg-[#080b11]" : "bg-slate-50"}`}>
      <SectionHead
        tone={tone}
        eyebrow="From prompt to a trip you own"
        title="The forty seconds that decide everything"
        body="A first-time visitor has no trip, no account and no patience. These three moments are the whole conversion, and each option places the account ask differently."
      />

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <Panel tone={tone} caption="0:00 · you pressed Plan">
          <BrowserFrame url="tripplanner.app/trip/guest-8f2c" tone={tone}>
            <div className="grid grid-cols-[1.1fr_1fr] gap-2 p-2.5">
              <div className="space-y-1.5">
                <div className={`h-2.5 w-28 rounded ${tone === "dark" ? "bg-white/10" : "bg-slate-200"}`} />
                {[0, 1, 2, 3].map((row) => (
                  <div key={row} className={`h-8 rounded-lg ${tone === "dark" ? "bg-white/5" : "bg-white ring-1 ring-slate-200"}`} />
                ))}
              </div>
              <div className="space-y-1.5">
                <ProofMap tone={tone} height="h-20" />
                <div className={`rounded-lg p-2 ${s.panel} ${s.panelRing}`}>
                  <p className={`flex items-center gap-1 text-[10px] ${s.body}`}>
                    <Loader2 size={9} className="animate-spin" aria-hidden /> Checking 41 stays in Alfama…
                  </p>
                  <p className={`mt-1 text-[10px] ${s.muted}`}>Flights priced · day 1 placed</p>
                </div>
              </div>
            </div>
          </BrowserFrame>
          <ul className="mt-2 space-y-1">
            <CheckLine tone={tone}>The URL is already a trip. Nothing was asked for.</CheckLine>
            <CheckLine tone={tone}>Work is visible as it lands, so the wait is legible.</CheckLine>
          </ul>
        </Panel>

        <Panel tone={tone} caption={stress ? "0:52 · still working, and honest about it" : "0:40 · a real plan, still a guest"}>
          <BrowserFrame url="tripplanner.app/trip/guest-8f2c" tone={tone}>
            <div className="space-y-2 p-2.5">
              <div className={`flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-semibold ${tone === "dark" ? "bg-amber-400/10 text-amber-200" : "bg-amber-50 text-amber-800"}`}>
                <UserRound size={10} aria-hidden /> Guest trip · kept in this browser for 30 days
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <DayCard dayIndex={0} tone={tone} stops={2} />
                {stress ? (
                  <div className={`rounded-xl p-3 ${s.panel} ${s.panelRing}`}>
                    <p className={`text-[11px] font-semibold ${s.heading}`}>Day 2 · still resolving</p>
                    <p className={`mt-1 text-[10px] ${s.body}`}>Two hotel rates timed out. Showing the plan without them rather than a spinner.</p>
                  </div>
                ) : (
                  <DayCard dayIndex={1} tone={tone} stops={2} />
                )}
              </div>
              <SavingsBar tone={tone} />
            </div>
          </BrowserFrame>
          <ul className="mt-2 space-y-1">
            <CheckLine tone={tone}>A complete, editable trip exists before any account.</CheckLine>
            <CheckLine tone={tone}>The guest banner states the expiry instead of implying permanence.</CheckLine>
          </ul>
        </Panel>

        <Panel tone={tone} caption="The sign-in moment">
          <div className={`rounded-xl p-4 ${s.panel} ${s.panelRing}`}>
            <p className={`text-[10px] font-bold uppercase ${s.accent}`}>When this option asks</p>
            <p className={`mt-1 text-xs leading-relaxed ${s.body}`}>{moment.when}</p>
            <div className={`mt-3 rounded-xl p-3 ${tone === "dark" ? "bg-black/40 ring-1 ring-white/10" : "bg-white ring-1 ring-slate-200"}`}>
              <p className={`text-sm font-semibold ${s.heading}`}>Keep this trip</p>
              <p className={`mt-1 text-xs leading-relaxed ${s.body}`}>{moment.copy}</p>
              <div className={`mt-3 flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold ${tone === "dark" ? "bg-white text-ink" : "bg-ink text-white"}`}>
                Continue with Google
              </div>
              <p className={`mt-2 text-center text-[11px] ${s.muted}`}>or keep planning as a guest</p>
            </div>
            <p className={`mt-3 flex gap-1.5 text-[11px] ${s.muted}`}>
              <TriangleAlert size={12} className="mt-0.5 shrink-0" aria-hidden /> {moment.risk}
            </p>
          </div>
          <ul className="mt-2 space-y-1">
            <CheckLine tone={tone}>Nothing is re-planned on sign-in; the guest trip is adopted as-is.</CheckLine>
            <CheckLine tone={tone}>Declining leaves the trip working, not degraded.</CheckLine>
          </ul>
        </Panel>
      </div>
    </div>
  );
}

function Panel({ tone, caption, children }: { tone: Tone; caption: string; children: ReactNode }) {
  const s = toneStyles[tone];
  return (
    <section>
      <p className={`mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase ${s.muted}`}>
        <Clock3 size={12} aria-hidden /> {caption}
      </p>
      {children}
    </section>
  );
}

/* --------------------------------------------------------------- shared trip page */

function SharePage({ option, tone, stress }: { option: Exclude<FirstVisitOption, "today">; tone: Tone; stress: boolean }) {
  const s = toneStyles[tone];
  return (
    <div className={`min-h-full px-6 py-6 ${tone === "dark" ? "bg-[#080b11]" : "bg-slate-50"}`}>
      <SectionHead
        tone={tone}
        eyebrow="The other front door"
        title="Most first visits will arrive through someone else's trip"
        body="A shared link is a landing page with a plan already in it. It has to render before JavaScript, read well in a message app, and offer the same one action."
      />

      <div className="mt-5 grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="space-y-3">
          <p className={`text-[11px] font-bold uppercase ${s.muted}`}>How the link looks in a message</p>
          <div className={`rounded-2xl p-3 ${tone === "dark" ? "bg-white/[0.04] ring-1 ring-white/10" : "bg-white ring-1 ring-slate-200"} shadow-card`}>
            <div className="overflow-hidden rounded-xl ring-1 ring-black/5">
              <div className="h-28" style={{ background: "linear-gradient(115deg,#0f766e,#0369a1 55%,#f43f5e)" }} aria-hidden />
              <div className={`${tone === "dark" ? "bg-white/5" : "bg-slate-50"} p-2.5`}>
                <p className={`text-[10px] uppercase ${s.muted}`}>tripplanner.app</p>
                <p className={`text-xs font-semibold ${s.heading}`}>Lisbon, 4 days for two · {trip.totalCost}</p>
                <p className={`mt-0.5 text-[11px] leading-relaxed ${s.body}`}>
                  Land 11:20 Thursday, Alfama on foot, Belém on Saturday. 14 places, every price stamped.
                </p>
              </div>
            </div>
            <p className={`mt-2 flex items-center gap-1.5 text-[11px] ${s.muted}`}>
              <Link2 size={12} aria-hidden /> Served as HTML, so the preview exists without running the app.
            </p>
          </div>
          <ul className="space-y-1">
            <CheckLine tone={tone}>The recipient sees the plan, not a sign-in wall.</CheckLine>
            <CheckLine tone={tone}>Prices show the owner's fetch time, never a live quote in someone else's name.</CheckLine>
            <CheckLine tone={tone}>One action: plan your own from this one.</CheckLine>
          </ul>
        </div>

        <div>
          <p className={`mb-2 text-[11px] font-bold uppercase ${s.muted}`}>The page itself</p>
          <BrowserFrame url="tripplanner.app/t/lisbon-oct-4d-8f2c" tone={tone}>
            <div className="p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <h3 className={`display text-lg font-semibold ${s.heading}`}>{proof.headline}</h3>
                  <p className={`text-[11px] ${s.body}`}>{proof.subline} · shared by Mahesh</p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${s.chip}`}>Read-only</span>
              </div>
              {stress && <div className="mt-2"><StaleNotice tone={tone} /></div>}
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {sampleDays.slice(0, 4).map((_, index) => (
                  <DayCard key={index} dayIndex={index} tone={tone} stops={3} />
                ))}
              </div>
              <div className="mt-3 grid gap-2 lg:grid-cols-[1.3fr_1fr]">
                <PriceTable tone={tone} compact />
                <ProofMap tone={tone} height="h-full" />
              </div>
              <div className={`mt-3 rounded-xl p-3 ${s.panel} ${s.panelRing}`}>
                <p className={`text-xs font-semibold ${s.heading}`}>
                  {option === "stage" ? "Watch one get built for your dates" : "Plan the same trip for your dates"}
                </p>
                <div className="mt-2">
                  <Composer tone={tone} size="sm" placeholder="Same trip, but 6 days in March for 2…" action={option === "stage" ? "Take over" : "Plan it"} />
                </div>
                <p className={`mt-1.5 flex items-center gap-1 text-[11px] ${s.muted}`}>
                  <ArrowRight size={11} aria-hidden /> Starts a new guest trip. Mahesh's plan is untouched.
                </p>
              </div>
            </div>
          </BrowserFrame>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------- today */

function TodayLanding() {
  return (
    <div className="min-h-full bg-slate-50 p-6">
      <div className="mx-auto max-w-3xl">
        <BrowserFrame url="tripplanner.app" tone="light">
          <div className="grid grid-cols-[1fr_1fr] gap-2 p-3">
            <div className="space-y-2">
              <div className="h-2.5 w-24 rounded bg-slate-200" />
              <div className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
                <p className="text-xs font-semibold text-ink">No trips yet</p>
                <p className="mt-1 text-[11px] text-slate-500">Start a conversation to build your first itinerary.</p>
              </div>
              <div className="h-24 rounded-lg bg-white ring-1 ring-slate-200" />
            </div>
            <div className="space-y-2">
              <ProofMap tone="light" height="h-28" />
              <div className="rounded-lg bg-white p-2 ring-1 ring-slate-200">
                <p className="text-[10px] text-slate-500">Assistant</p>
                <p className="mt-1 text-[11px] text-ink">Where would you like to go?</p>
              </div>
            </div>
          </div>
        </BrowserFrame>
        <div className="mt-4 rounded-xl bg-white p-4 shadow-card ring-1 ring-slate-200">
          <p className="text-sm font-semibold text-ink">Today there is no public page at all</p>
          <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-slate-600">
            <li>· The root URL boots the full React app and shows an empty workspace.</li>
            <li>· First paint waits for the bundle; a crawler sees an empty shell.</li>
            <li>· Nothing states what the product does, what it costs, or whether an account is required.</li>
            <li>· A shared trip link resolves to the same shell, so a recipient must load the app to read a plan.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function TodayFirstPlan() {
  return (
    <div className="min-h-full bg-slate-50 p-6">
      <div className="mx-auto max-w-2xl rounded-xl bg-white p-5 shadow-card ring-1 ring-slate-200">
        <p className="text-sm font-semibold text-ink">Today's first plan</p>
        <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
          A visitor types into the Assistant sheet inside the workspace. A guest capability
          credential is issued and the trip persists for that browser, but nothing on screen
          explains that, states an expiry, or offers to keep the trip. Sign-in exists in the
          toolbar and is never contextual.
        </p>
      </div>
    </div>
  );
}

function TodayShare() {
  return (
    <div className="min-h-full bg-slate-50 p-6">
      <div className="mx-auto max-w-2xl rounded-xl bg-white p-5 shadow-card ring-1 ring-slate-200">
        <p className="text-sm font-semibold text-ink">Today's shared trip</p>
        <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
          Export produces email and calendar artifacts. There is no public trip URL, so there is
          no link preview, no indexable page, and no way for a recipient to arrive at a plan
          without an account and the full app.
        </p>
      </div>
    </div>
  );
}
