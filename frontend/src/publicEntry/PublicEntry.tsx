// Option E from Lab 22: the run argues with you while it happens. The two decisions the
// planner made for the visitor are offered inside the receipt stream, at the moment they were
// taken, and overruling one re-settles the totals in place.

import { ArrowRight, Info, Loader2, MapPin, Undo2 } from "lucide-react";
import { Fragment, useEffect, useState } from "react";

import {
  demoArtifactForLocale,
  faq,
  fetchDemoArtifact,
  withDisplayCurrency,
  type PublicDemoArtifact,
  type StageDecision,
  type StageTrip,
} from "./demoRun";
import { fetchPreferences } from "../api";
import { getDisplayName, isAnonymousUser } from "../auth/authSession";
import { openAccountSettings } from "../components/accountSettings";
import {
  displayLanguageLabel,
  displayRegionLabel,
  ensureInitialDisplayPreferences,
  normalizeDisplayLanguage,
  normalizeDisplayRegion,
  useDisplayPreferences,
  writeDisplayPreferences,
} from "../lib/displayPreferences";
import {
  HotelStrip,
  ModeCompareCard,
  ModeLegend,
  Masthead,
  PendingDayCard,
  PriceTableLive,
  ReceiptLine,
  SavingsRow,
  SectionHead,
  SiteFooter,
  StageControls,
  StageDayCard,
  TrustList,
  daysBuilt,
  toneStyles,
  useStageRun,
} from "./stagePieces";

const dark = toneStyles.dark;

function useOverrule(decisions: StageDecision[]) {
  const [overruled, setOverruled] = useState<string | null>(null);
  const active = decisions.find((decision) => decision.id === overruled) ?? null;
  return { overruled, setOverruled, active };
}

function InlineChoice({
  decision,
  overruled,
  onOverrule,
  onUndo,
}: {
  decision: StageDecision;
  overruled: boolean;
  onOverrule: () => void;
  onUndo: () => void;
}) {
  if (overruled) {
    return (
      <li className="rounded-xl bg-amber-400/10 px-3 py-2.5 ring-1 ring-amber-400/30">
        <p className={`text-[11px] font-semibold ${dark.heading}`}>{decision.outcome.headline}</p>
        <p className="mt-0.5 flex items-start gap-1.5 text-[11px] leading-relaxed text-amber-200">
          <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
          {decision.outcome.warning}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <span className={`text-xs font-bold tabular-nums ${dark.heading}`}>{decision.outcome.total}</span>
          <span className="text-[11px] font-semibold text-amber-300">{decision.outcome.delta}</span>
          <button
            type="button"
            onClick={onUndo}
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${dark.chip}`}
          >
            <Undo2 size={11} aria-hidden /> Put it back
          </button>
        </div>
      </li>
    );
  }

  return (
    <li className="rounded-xl bg-white/[0.06] px-3 py-2.5 ring-1 ring-white/15">
      <p className={`text-[11px] font-semibold ${dark.heading}`}>
        {decision.subject} — <span className={dark.accent}>{decision.verdict}</span>
      </p>
      <p className={`mt-0.5 text-[11px] leading-relaxed ${dark.muted}`}>{decision.rule}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onOverrule}
          className="inline-flex items-center gap-1.5 rounded-full bg-ink px-2.5 py-1 text-[11px] font-semibold text-white transition hover:opacity-90"
        >
          {decision.overrule}
        </button>
        <span className={`text-[11px] ${dark.muted}`}>{decision.inline}</span>
      </div>
    </li>
  );
}

function Composer({ onPlan }: { onPlan: (request: string) => void }) {
  const [value, setValue] = useState("");
  const request = value.trim();
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (request) onPlan(request);
      }}
    >
      <div className="flex items-center gap-2 rounded-2xl bg-white/[0.06] px-3 py-2.5 shadow-card ring-1 ring-white/20 focus-within:ring-2 focus-within:ring-brand">
        <MapPin size={18} className={dark.muted} aria-hidden />
        <input
          type="text"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Kyoto in April with a 6-year-old…"
          aria-label="Where do you want to go?"
          className="min-w-0 flex-1 bg-transparent text-[15px] text-white outline-none placeholder:text-slate-500"
        />
        <button
          type="submit"
          disabled={!request}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-brand px-3.5 py-2 text-[13px] font-semibold text-white transition hover:bg-brand-600 disabled:opacity-50"
        >
          Plan mine <ArrowRight size={14} aria-hidden />
        </button>
      </div>
    </form>
  );
}

function BelowTheFold({ trip }: { trip: StageTrip }) {
  return (
    <div className="bg-white">
      <section className="border-b border-slate-200 px-6 py-8">
        <SectionHead
          tone="light"
          eyebrow="What you just watched"
          title="Every number carries its source"
          body="One real run, captured and replayed. Here is the receipt it produced."
        />
        <div className="mt-4 grid gap-3 lg:grid-cols-[1.5fr_1fr]">
          <PriceTableLive trip={trip} tone="light" />
          <HotelStrip hotels={trip.hotels} tone="light" detail />
        </div>
      </section>

      <section className="border-b border-slate-200 px-6 py-8">
        <SectionHead
          tone="light"
          eyebrow="How it decided to move you"
          title="Flight, rail, road and coach — measured door to door"
          body="A trip is decided by how you get between places. Each hop is compared end to end, including the transfers a fare page never shows you, and the options it rejected stay visible with the reason."
        />
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {trip.compares.map((compare) => (
            <ModeCompareCard key={compare.id} compare={compare} tone="light" />
          ))}
        </div>
      </section>

      <section className="border-b border-slate-200 px-6 py-8">
        <SectionHead tone="light" eyebrow="What it will and will not do" title="The honest edges" />
        <div className="mt-4 grid gap-5 lg:grid-cols-2">
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

export default function PublicEntry({
  onPlan,
  onSkip,
}: {
  onPlan: (request: string) => void;
  onSkip: () => void;
}) {
  const signedIn = !isAnonymousUser();
  const accountLabel = signedIn ? getDisplayName() || "Account" : "Guest";
  const displayPreferences = useDisplayPreferences();
  const fallbackArtifact = demoArtifactForLocale(
    displayPreferences.region,
    displayPreferences.currency,
  );
  const [artifact, setArtifact] = useState<PublicDemoArtifact>(fallbackArtifact);
  useEffect(() => {
    ensureInitialDisplayPreferences();
    fetchPreferences().then((preferences) => {
      if (!isAnonymousUser() || preferences.display_currency_configured) {
        writeDisplayPreferences({
          region: normalizeDisplayRegion(preferences.display_region || preferences.home_country || ""),
          language: normalizeDisplayLanguage(preferences.display_language || "en"),
          currency: preferences.display_currency || "USD",
        });
      }
    }).catch(() => undefined);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const selected = demoArtifactForLocale(displayPreferences.region, displayPreferences.currency);
    setArtifact(selected);
    fetchDemoArtifact(
      selected.region,
      selected.currency,
      controller.signal,
    ).then((remote) => {
      if (remote.region === selected.region && remote.currency === selected.currency) {
        setArtifact(remote);
      }
    }).catch(() => undefined);
    return () => controller.abort();
  }, [displayPreferences.currency, displayPreferences.region]);
  const localized = withDisplayCurrency(artifact, displayPreferences.currency);
  const trip = localized.trip;
  const decisions = localized.decisions;
  const { step, running, replay, finish } = useStageRun(trip.receipts.length);
  const built = running ? daysBuilt(trip.receipts, step) : trip.days.length;
  const { overruled, setOverruled, active } = useOverrule(decisions);
  const shown = Math.max(1, built);

  return (
    <div className="min-h-full overflow-y-auto bg-[#080b11]">
      <div className="relative overflow-hidden bg-[#080b11]">
        <div className="pointer-events-none absolute -left-24 -top-40 h-96 w-96 rounded-full bg-brand/25 blur-3xl" aria-hidden />
        <div className="pointer-events-none absolute -right-24 top-10 h-96 w-96 rounded-full bg-teal-400/20 blur-3xl" aria-hidden />

        <Masthead tone="dark" onSkip={onSkip} onOpenAccount={() => openAccountSettings()} accountLabel={accountLabel} signedIn={signedIn} />

        <section className="relative px-6 pb-8 pt-10">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/15 px-2.5 py-1 text-[11px] font-bold uppercase text-emerald-300 ring-1 ring-emerald-400/30">
              <span className={`h-1.5 w-1.5 rounded-full bg-emerald-500 ${running ? "animate-pulse" : ""}`} aria-hidden />
              {running ? "Replaying a real run" : "Plan complete"}
            </span>
            <span className={`text-[11px] ${dark.muted}`}>
              No account, no signup. This run was captured so it cannot fail in front of you — yours is planned live.
            </span>
            <span className={`text-[11px] ${dark.muted}`}>
              Display: {displayPreferences.currency}{displayPreferences.region ? ` · ${displayRegionLabel(displayPreferences.region)}` : " · detected from browser"} · {displayLanguageLabel(displayPreferences.language)}
            </span>
          </div>

          <h1 className={`display mt-3 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl ${dark.heading}`}>
            Watch it plan a trip.<br />Then ask it to plan yours.
          </h1>

          <div className="mt-6 grid gap-3 lg:grid-cols-[0.95fr_1.05fr]">
            <div className={`rounded-2xl p-4 ${dark.panel} ${dark.panelRing}`}>
              <div className="flex items-center justify-between gap-2">
                <p className={`font-mono text-[11px] uppercase tracking-wide ${dark.muted}`}>
                  agent · {trip.title} · {trip.travellers}
                </p>
                <StageControls tone="dark" running={running} onReplay={replay} onFinish={finish} />
              </div>
              <ol className="mt-3 space-y-1.5" aria-live="polite">
                {trip.receipts.slice(0, step).map((receipt, index) => (
                  <Fragment key={`${index}-${receipt.at}`}>
                    <ReceiptLine receipt={receipt} tone="dark" />
                    {decisions
                      .filter((decision) => decision.after === index)
                      .map((decision) => (
                        <InlineChoice
                          key={decision.id}
                          decision={decision}
                          overruled={overruled === decision.id}
                          onOverrule={() => setOverruled(decision.id)}
                          onUndo={() => setOverruled(null)}
                        />
                      ))}
                  </Fragment>
                ))}
                {running && (
                  <li className={`flex items-center gap-2 font-mono text-[11px] ${dark.muted}`}>
                    <Loader2 size={11} className="animate-spin" aria-hidden /> working…
                  </li>
                )}
              </ol>
            </div>

            <div className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-2">
                {trip.days.slice(0, shown).map((day) => (
                  <StageDayCard key={day.day} day={day} tone="dark" />
                ))}
                {Array.from({ length: Math.max(0, trip.days.length - shown) }).map((_, index) => (
                  <PendingDayCard
                    key={`pending-${index}`}
                    tone="dark"
                    label={index === 0 ? `Placing day ${shown + 1} of ${trip.days.length}…` : undefined}
                  />
                ))}
              </div>

              {active ? (
                <div className="rounded-xl bg-amber-400/10 px-3.5 py-2.5 ring-1 ring-amber-400/30">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="text-[11px] font-bold uppercase text-amber-200">Re-settled around your change</span>
                    <span className={`text-lg font-bold tabular-nums ${dark.heading}`}>{active.outcome.total}</span>
                    <span className="text-xs font-semibold text-amber-300">{active.outcome.delta}</span>
                  </div>
                  <p className={`mt-0.5 text-[11px] leading-relaxed ${dark.body}`}>
                    The plan above is the one you asked for, not the one it recommended. Put it back
                    and its own version returns intact.
                  </p>
                </div>
              ) : (
                <SavingsRow trip={trip} tone="dark" />
              )}

              <div className={`rounded-2xl p-4 ${dark.panel} ${dark.panelRing}`}>
                <p className={`text-sm font-semibold ${dark.heading}`}>Make it yours</p>
                <p className={`mt-1 text-xs ${dark.body}`}>
                  Replace this trip with anywhere. It re-plans from scratch in front of you, and you can
                  argue with that one too.
                </p>
                <div className="mt-3">
                  <Composer onPlan={onPlan} />
                </div>
                <button
                  type="button"
                  onClick={onSkip}
                  className={`mt-2 text-[11px] underline underline-offset-2 ${dark.muted} hover:text-slate-300`}
                >
                  Or skip this and open the planner
                </button>
              </div>

              <ModeLegend tone="dark" />
            </div>
          </div>
        </section>
      </div>
      <BelowTheFold trip={trip} />
    </div>
  );
}
