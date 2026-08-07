/**
 * The effort model, running on the same fixture as the plan engine.
 *
 * The panels are arranged to answer one question in order: what does a day cost,
 * what does yesterday cost today, what does the owner actually get told, and
 * what does the model catch that has nothing to do with tiredness.
 */

import { Activity, Gauge, MessageSquareQuote, Route, Scale } from "lucide-react";
import { startingTrip } from "./planEngine";
import {
  CURRENCIES,
  CURRENCY_LABEL,
  MODE_FACTOR,
  RECOVERY,
  SOLO_STEADY,
  capacityFor,
  coherenceFlags,
  compareEffort,
  dayEffort,
  describeChoice,
  describeDay,
  pacingVerdict,
  rankTravelOptions,
  reserveCurve,
  totalEffort,
} from "./effortModel";
import type { Party } from "./effortModel";
import { indoreFacts, legOptions, novemberMalwa, surfaceExample } from "./effortFacts";

const FAMILY: Party = { adults: 2, childAges: [7], seniors: 0, pace: "steady" };

const currencyDefinition: Array<{ currency: (typeof CURRENCIES)[number]; text: string }> = [
  {
    currency: "physical",
    text: "Active minutes weighted by what they demand: distance on foot, climbing, steps, standing, crowds. The slowest of the five to repay.",
  },
  {
    currency: "transit",
    text: "Time in motion weighted by mode and surface. This is where a jeep track and a highway stop being the same kilometre.",
  },
  {
    currency: "logistical",
    text: "Transitions rather than time: check-ins, bag moves, mode switches, navigation. Four short hops exhaust more than one long block, and only this currency notices.",
  },
  {
    currency: "circadian",
    text: "Starts before 07:00, ends after 22:00, red-eyes, timezone shifts. Repayable by a late start and by almost nothing else.",
  },
  {
    currency: "exposure",
    text: "Heat, rain, altitude and sun during the hours actually spent outdoors. Free to compute and routinely the difference between a good day and a punishing one.",
  },
];

export function EffortPanels() {
  const days = [...new Set(startingTrip.map((stop) => stop.day))].sort((a, b) => a - b);
  const efforts = days.map((day) => dayEffort(startingTrip, day, indoreFacts, novemberMalwa));
  const soloCurve = reserveCurve(startingTrip, SOLO_STEADY, indoreFacts, novemberMalwa);
  const familyCurve = reserveCurve(startingTrip, FAMILY, indoreFacts, novemberMalwa);
  const soloVerdict = pacingVerdict(startingTrip, SOLO_STEADY, indoreFacts, novemberMalwa);
  const familyVerdict = pacingVerdict(startingTrip, FAMILY, indoreFacts, novemberMalwa);
  const flags = coherenceFlags(startingTrip, indoreFacts);
  const ranked = rankTravelOptions(legOptions, { prefersRail: true, dislikesEarlyStarts: true });
  const choice = describeChoice(ranked);
  const peak = Math.max(...familyCurve.map((row) => row.load));
  const heaviest = efforts.reduce((a, b) => (b.total > a.total ? b : a));
  const deltas = compareEffort(ranked[0].effort, ranked[1].effort);

  const surface = surfaceExample.map((entry) => {
    const minutes = (entry.km / entry.speedKmh) * 60;
    return { ...entry, minutes, cost: minutes * MODE_FACTOR[entry.mode] };
  });

  return (
    <>
      <section className="mt-10 border-t border-slate-200 pt-8">
        <p className="text-[10px] font-bold uppercase text-brand">The second layer</p>
        <h2 className="mt-1 text-2xl font-semibold text-ink">
          A guard that stops nonsense, and a critic that stops a bad week
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
          The eight invariants above answer one question: is this plan possible. They cannot answer the second
          question, which is whether it is any good. A day can satisfy every invariant and still be eleven kilometres
          on foot in November sun after a 05:00 alarm. That needs a different kind of arithmetic, and — this is the
          part worth getting right first — it needs a different kind of authority.
        </p>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
            <p className="text-sm font-semibold text-ink">The invariant may block, but never speaks in numbers</p>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
              Boolean, provable, and about physics. "You land at 08:05, so nothing can start at 07:30." A refusal
              names the rule it enforced.
            </p>
          </div>
          <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
            <p className="text-sm font-semibold text-ink">The score may speak, but never blocks</p>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
              Continuous, arguable, and about taste. It ranks the options the invariants already permitted, and at
              most it says what a change cost. It never refuses.
            </p>
          </div>
        </div>
        <p className="mt-3 max-w-3xl rounded-2xl bg-amber-50 p-3.5 text-xs leading-relaxed text-amber-900 ring-1 ring-amber-200">
          <span className="font-semibold">Why they must not merge. </span>
          Fold taste into the guard and it starts refusing legal plans the owner wanted. Fold the guard into a total
          score and one genuinely broken day gets averaged away by four good ones. The two live in separate modules —
          <span className="font-mono"> planEngine.ts</span> and <span className="font-mono">effortModel.ts</span> —
          precisely so that no future change can quietly blend them.
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {[
            {
              mode: "Refuse",
              when: "An invariant is broken.",
              text: "Names the invariant in words, and offers the nearest legal slot. This is the only outcome that stops anything.",
              tone: "bg-rose-50 text-rose-900 ring-rose-200",
            },
            {
              mode: "Apply, and say what it cost",
              when: "Legal, but notably worse.",
              text: "The change is made. The receipt states the regression as a measured quantity. It never asks permission, because it was always allowed.",
              tone: "bg-amber-50 text-amber-900 ring-amber-200",
            },
            {
              mode: "Apply silently",
              when: "Legal, and neutral or better.",
              text: "By far the common case, and the reason this layer is not friction. Most edits are fine and get no commentary at all.",
              tone: "bg-emerald-50 text-emerald-900 ring-emerald-200",
            },
          ].map((entry) => (
            <div key={entry.mode} className={`rounded-2xl p-3.5 text-[11px] leading-relaxed ring-1 ${entry.tone}`}>
              <p className="text-xs font-semibold">{entry.mode}</p>
              <p className="mt-0.5 font-medium opacity-80">{entry.when}</p>
              <p className="mt-1">{entry.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-8">
        <div className="flex items-center gap-2 text-brand">
          <Activity size={16} aria-hidden />
          <p className="text-[10px] font-bold uppercase">What a day costs</p>
        </div>
        <h2 className="mt-1 text-lg font-semibold text-ink">Fatigue is a vector, not a number</h2>
        <p className="mt-1.5 max-w-3xl text-xs leading-relaxed text-slate-600">
          Collapsing tiredness to one figure loses the information that makes it actionable, because the five kinds
          recover at completely different rates overnight. A day that was heavy on transitions is gone by morning; a
          04:30 alarm is not.
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {currencyDefinition.map((entry) => (
            <div key={entry.currency} className="rounded-2xl bg-white p-3.5 shadow-card ring-1 ring-slate-200">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-xs font-semibold capitalize text-ink">{entry.currency}</p>
                <p className="text-[10px] text-slate-400">
                  {Math.round(RECOVERY[entry.currency] * 100)}% clears overnight
                </p>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{entry.text}</p>
            </div>
          ))}
          <div className="rounded-2xl bg-ink p-3.5 text-white shadow-card">
            <p className="text-xs font-semibold">Five kilometres against thirty</p>
            <div className="mt-2 space-y-1.5">
              {surface.map((entry) => (
                <div key={entry.label} className="text-[11px] leading-relaxed">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-slate-200">{entry.label}</span>
                    <span className="font-mono text-white">{Math.round(entry.cost)}</span>
                  </div>
                  <div className="mt-0.5 h-1 rounded-full bg-white/15">
                    <div
                      className="h-1 rounded-full bg-accent"
                      style={{ width: `${(entry.cost / Math.max(...surface.map((row) => row.cost))) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-300">
              The track costs more despite being a sixth of the distance, and no model was consulted: the surface tag
              is on the road in OpenStreetMap, and the rest is multiplication.
            </p>
          </div>
        </div>
      </section>

      <section className="mt-8">
        <div className="flex items-center gap-2 text-brand">
          <Gauge size={16} aria-hidden />
          <p className="text-[10px] font-bold uppercase">Fatigue is a stock, not a flow</p>
        </div>
        <h2 className="mt-1 text-lg font-semibold text-ink">The day it catches up is not the heaviest day</h2>
        <p className="mt-1.5 max-w-3xl text-xs leading-relaxed text-slate-600">
          Per-day scoring rates three consecutive heavy days better than one brutal day with a light one either side,
          which is exactly backwards. Carrying a reserve forward buys three things a per-day score structurally
          cannot: it fires on the ordinary day <em>after</em> the hard ones, it puts the remedy on the day that caused
          the problem, and it gives the trip a shape — hard walk early while fresh, long transfer on the flat day.
        </p>

        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {[
            { label: "Travelling alone, at your usual pace", curve: soloCurve, party: SOLO_STEADY, verdict: soloVerdict },
            { label: "Same itinerary, with a seven-year-old", curve: familyCurve, party: FAMILY, verdict: familyVerdict },
          ].map((scenario) => {
            const capacity = capacityFor(scenario.party);
            return (
              <div key={scenario.label} className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
                <p className="text-sm font-semibold text-ink">{scenario.label}</p>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  The party moves at the pace of its most limited member, so capacity is set by {capacity.limitedBy}.
                </p>
                <div className="mt-3 flex h-28 items-end gap-2">
                  {scenario.curve.map((row) => {
                    const carried = totalEffort(row.carriedIn);
                    return (
                      <div key={row.day} className="flex flex-1 flex-col items-center gap-1">
                        <div className="relative flex w-full flex-1 items-end">
                          <div
                            className="absolute inset-x-0 border-t border-dashed border-rose-400"
                            style={{ bottom: `${(row.capacity / peak) * 100}%` }}
                            aria-hidden
                          />
                          <div className="w-full">
                            <div
                              className={`w-full rounded-t ${row.overCapacity ? "bg-rose-400" : "bg-slate-300"}`}
                              style={{ height: `${(carried / peak) * 100}px` }}
                            />
                            <div
                              className={`w-full ${row.overCapacity ? "bg-rose-300" : "bg-slate-200"}`}
                              style={{ height: `${(row.spend / peak) * 100}px` }}
                            />
                          </div>
                        </div>
                        <span className="text-[10px] text-slate-500">D{row.day}</span>
                      </div>
                    );
                  })}
                </div>
                <p className="mt-1 text-[10px] text-slate-400">
                  Pale block is the day's own cost, solid block is what it inherited from the day before, dashed line
                  is capacity. Internal only — none of these shapes reaches the owner.
                </p>
                {scenario.verdict ? (
                  <div className="mt-2.5 rounded-xl bg-amber-50 p-3 text-[11px] leading-relaxed text-amber-900 ring-1 ring-amber-200">
                    <p className="font-semibold">The one thing it says, all trip:</p>
                    <p className="mt-1">{scenario.verdict.statement}</p>
                    <p className="mt-1.5">{scenario.verdict.remedy}</p>
                  </div>
                ) : (
                  <p className="mt-2.5 rounded-xl bg-emerald-50 p-3 text-[11px] leading-relaxed text-emerald-900 ring-1 ring-emerald-200">
                    <span className="font-semibold">It says nothing. </span>
                    The debt never runs high across two consecutive days, so there is nothing worth interrupting for.
                    Silence is the default and the common case.
                  </p>
                )}
              </div>
            );
          })}
        </div>

        <p className="mt-3 max-w-3xl rounded-2xl bg-white p-3.5 text-xs leading-relaxed text-slate-600 shadow-card ring-1 ring-slate-200">
          <span className="font-semibold text-ink">The risk, stated plainly. </span>
          The recovery rates are invented. There is no ground truth for them, and a compounding model gets a trip
          progressively wronger: ten per cent a day is a wrong verdict by day five. The failure mode is confident
          nagging, which is worse than saying nothing. So the model and its voice are separated: the reserve informs
          every ranking, always and invisibly, where being roughly right is already useful and being wrong is
          harmless. Speaking is rationed to one statement per trip, at the worst point, only on two or more
          consecutive days over capacity. Building it later is a rewrite — <span className="font-mono">score(day)</span>{" "}
          and <span className="font-mono">score(sequence)</span> are different shapes. Making it quieter later is a
          single coefficient.
        </p>
      </section>

      <section className="mt-8">
        <div className="flex items-center gap-2 text-brand">
          <MessageSquareQuote size={16} aria-hidden />
          <p className="text-[10px] font-bold uppercase">The presentation contract</p>
        </div>
        <h2 className="mt-1 text-lg font-semibold text-ink">No composite ever reaches the owner</h2>
        <p className="mt-1.5 max-w-3xl text-xs leading-relaxed text-slate-600">
          Not "Day 3: 78", not "fatigue 62%", and not a gauge, a progress bar or a five-star rating — those are
          numbers wearing a costume, and they invite an argument nobody can win. But a measured quantity is not a
          score. "Eleven kilometres on foot" is checkable, and it is exactly what a human planner says. The rule is
          the same one the document-readiness checks already follow: surface the quantity and the comparison, never
          the composite.
        </p>
        <div className="mt-3 overflow-hidden rounded-2xl bg-white shadow-card ring-1 ring-slate-200">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-[10px] font-bold uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">Day</th>
                <th className="px-3 py-2">Engine internals — never shown</th>
                <th className="px-3 py-2">What the owner would actually read</th>
              </tr>
            </thead>
            <tbody className="align-top">
              {efforts.map((entry) => (
                <tr key={entry.day} className={entry.day === heaviest.day ? "bg-rose-50" : ""}>
                  <td className="px-3 py-2 font-semibold text-ink">Day {entry.day}</td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-500">
                    {CURRENCIES.filter((currency) => entry.effort[currency] >= 1)
                      .map((currency) => `${currency.slice(0, 4)} ${Math.round(entry.effort[currency])}`)
                      .join(" · ")}
                    {" · Σ "}
                    {Math.round(entry.total)}
                  </td>
                  <td className="px-3 py-2 text-slate-700">{describeDay(soloCurve, entry.day, entry)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div className="rounded-2xl bg-emerald-50 p-3.5 text-[11px] leading-relaxed text-emerald-900 ring-1 ring-emerald-200">
            <p className="font-semibold">Allowed</p>
            <p className="mt-1">"Day 3 is your longest on foot — about 4 km, roughly double any other day."</p>
            <p className="mt-1">"The train costs four hours more but saves an 04:30 start and a hotel night."</p>
            <p className="mt-1">"That moved the museum to the day you fly home."</p>
          </div>
          <div className="rounded-2xl bg-rose-50 p-3.5 text-[11px] leading-relaxed text-rose-900 ring-1 ring-rose-200">
            <p className="font-semibold">Never</p>
            <p className="mt-1">"Day 3 fatigue score: 78 / 100."</p>
            <p className="mt-1">A bar, a gauge, a colour-coded rating or a trend line of tiredness.</p>
            <p className="mt-1">Any sentence the owner cannot check against the itinerary in front of them.</p>
          </div>
        </div>
        <p className="mt-2 text-[11px] text-slate-500">
          The composite stays inspectable for debugging in option C's plan console, behind a toggle and labelled as
          engineering detail. It never appears in the normal flow.
        </p>
      </section>

      <section className="mt-8">
        <div className="flex items-center gap-2 text-brand">
          <Scale size={16} aria-hidden />
          <p className="text-[10px] font-bold uppercase">Comparative, never absolute</p>
        </div>
        <h2 className="mt-1 text-lg font-semibold text-ink">Ranking options, with the awkward part said first</h2>
        <p className="mt-1.5 max-w-3xl text-xs leading-relaxed text-slate-600">
          The public interface is <span className="font-mono">rank(options)</span>, not{" "}
          <span className="font-mono">score(day)</span>. A lone absolute number means nothing and invites exactly the
          argument we are trying to avoid; a difference between two real choices is defensible and is what the owner
          actually wanted to know.
        </p>
        <div className="mt-3 grid gap-3 lg:grid-cols-[1.4fr_1fr]">
          <div className="overflow-hidden rounded-2xl bg-white shadow-card ring-1 ring-slate-200">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-[10px] font-bold uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">Option</th>
                  <th className="px-3 py-2">Leaves</th>
                  <th className="px-3 py-2">Wall clock</th>
                  <th className="px-3 py-2">Fare</th>
                  <th className="px-3 py-2">Why</th>
                </tr>
              </thead>
              <tbody className="align-top">
                {ranked.map((option, index) => (
                  <tr key={option.id} className={index === 0 ? "bg-emerald-50 text-emerald-900" : "text-slate-600"}>
                    <td className="px-3 py-2 font-semibold">
                      {option.label}
                      {index === 0 ? " · preferred" : ""}
                    </td>
                    <td className="px-3 py-2">{option.departs}</td>
                    <td className="px-3 py-2">
                      {Math.floor(option.minutes / 60)}h {option.minutes % 60}m
                    </td>
                    <td className="px-3 py-2">₹{option.price.toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-[11px] leading-relaxed">{option.reasons.join("; ")}.</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
            <p className="text-[10px] font-bold uppercase text-slate-400">Per-dimension difference</p>
            <ul className="mt-2 space-y-1">
              {deltas.map((entry) => (
                <li key={entry.currency} className="flex items-baseline justify-between gap-2 text-[11px]">
                  <span className="capitalize text-slate-500">{CURRENCY_LABEL[entry.currency]}</span>
                  <span className={entry.delta > 0 ? "text-emerald-700" : "text-slate-400"}>{entry.sentence}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 rounded-xl bg-ink p-3 text-[11px] leading-relaxed text-white">{choice}</p>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
              Stated preference — "rail over road", "no early starts" — tilts the comfort factor. Party composition
              shifts capacity. Neither invents a constraint, and a preference can lower a ranking but can never
              refuse a choice the owner asked for.
            </p>
          </div>
        </div>
      </section>

      <section className="mt-8">
        <div className="flex items-center gap-2 text-brand">
          <Route size={16} aria-hidden />
          <p className="text-[10px] font-bold uppercase">Weird is broader than tiring</p>
        </div>
        <h2 className="mt-1 text-lg font-semibold text-ink">
          {flags.length} coherence notes on this itinerary, all of them arithmetic
        </h2>
        <p className="mt-1.5 max-w-3xl text-xs leading-relaxed text-slate-600">
          A sunset viewpoint at 11:00 is the highest-signal weirdness detector per line of code in the whole model. So
          are a day that runs through lunch with nowhere to stop, a route that crosses the city and comes back, a late
          night against an early start, and the thing worth the trip sharing a day with a departure flight. None of
          these block; each is one sentence the owner can accept or ignore.
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {flags.map((flag) => (
            <div key={`${flag.code}-${flag.day}-${flag.title}`} className="flex gap-2.5 rounded-2xl bg-white p-3 shadow-card ring-1 ring-slate-200">
              <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-amber-500 text-[10px] font-bold text-white">
                {flag.code}
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-ink">{flag.title}</p>
                <p className="mt-0.5 text-[11px] leading-relaxed text-slate-600">{flag.detail}</p>
                <p className="mt-1 text-[10px] uppercase text-slate-400">{flag.source}</p>
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 max-w-3xl rounded-2xl bg-white p-3.5 text-xs leading-relaxed text-slate-600 shadow-card ring-1 ring-slate-200">
          <span className="font-semibold text-ink">Reviews, kept in their place. </span>
          Asking a model how tiring a place is returns "moderate walking" for everything, and reviewer fitness and
          recency make review text a poor numeric input. One review signal is genuinely checkable and genuinely
          valuable: how long people say the visit takes. That one feeds a flag. Everything else read from reviews
          stays annotation text, never a term in the arithmetic.
        </p>
      </section>
    </>
  );
}
