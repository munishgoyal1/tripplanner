import bundleJson from "./publicDemoRuns.json";
import { formatCostDisplay, type DisplayCurrency } from "../lib/displayPreferences";

export type StageMode = "flight" | "train" | "road" | "tram" | "metro" | "bus" | "walk" | "ferry";
export type StopKind = "flight" | "hotel" | "attraction" | "meal" | "transport";
export interface StageStop { time: string; name: string; detail?: string; kind: StopKind; marker?: string; cost?: string; }
export interface StageLeg { mode: StageMode; label: string; duration: string; cost?: string; }
export interface StageDay { day: number; weekday: string; date: string; city: string; title: string; color: string; hotel: string; legs: StageLeg[]; stops: StageStop[]; }
export interface StageHotel { marker: string; name: string; city: string; area: string; nights: string; price: string; source: string; checked: string; why: string; }
export interface ModeOption { mode: StageMode; label: string; door: string; cost: string; verdict: string; picked?: boolean; }
export interface ModeCompare { id: string; subject: string; chosen: string; options: ModeOption[]; why: string; }
export interface StageReceipt { at: string; kind: "read" | "search" | "price" | "hotel" | "place" | "compare" | "check"; text: string; day?: number; }
export interface PriceLine { label: string; detail: string; price: string; source: string; checked: string; }
export interface StageTrip { id: string; title: string; summary: string; dateRange: string; travellers: string; receipts: StageReceipt[]; days: StageDay[]; hotels: StageHotel[]; compares: ModeCompare[]; lines: PriceLine[]; total: string; totalLabel: string; totalNote: string; sources: string; }
export interface StageDecision { id: string; at: string; after: number; subject: string; verdict: string; reason: string; rule: string; options: ModeOption[]; overrule: string; inline: string; outcome: { headline: string; changes: string[]; total: string; delta: string; warning: string; }; }
export interface PublicDemoArtifact {
  schema_version: number;
  artifact_version: string;
  generated_at: string;
  region: string;
  currency: string;
  market: { aliases: string[]; country: string; origin: string; destination: string; cities: string[]; entities: string[]; };
  trip: StageTrip;
  decisions: StageDecision[];
}

const bundle = bundleJson as unknown as { schema_version: number; artifacts: PublicDemoArtifact[] };

export function demoArtifactForLocale(region: string, currency: string): PublicDemoArtifact {
  const normalizedRegion = region.trim().toUpperCase();
  const normalizedCurrency = currency.trim().toUpperCase();
  return bundle.artifacts.find((artifact) =>
    artifact.market.aliases.some((alias) => alias.toUpperCase() === normalizedRegion))
    ?? bundle.artifacts.find((artifact) => artifact.currency === normalizedCurrency)
    ?? bundle.artifacts.find((artifact) => artifact.currency === "EUR")!;
}

/** Present one market's captured money in the traveller's currency; the itinerary itself is untouched. */
export function withDisplayCurrency(
  artifact: PublicDemoArtifact,
  currency: DisplayCurrency,
): PublicDemoArtifact {
  if (!currency || artifact.currency === currency) return artifact;
  const money = (value: string) => formatCostDisplay(value, currency);
  const optional = (value?: string) => (value ? money(value) : value);
  const trip = artifact.trip;
  return {
    ...artifact,
    trip: {
      ...trip,
      total: money(trip.total),
      days: trip.days.map((day) => ({
        ...day,
        legs: day.legs.map((leg) => ({ ...leg, cost: optional(leg.cost) })),
        stops: day.stops.map((stop) => ({ ...stop, cost: optional(stop.cost) })),
      })),
      hotels: trip.hotels.map((hotel) => ({ ...hotel, price: money(hotel.price) })),
      compares: trip.compares.map((compare) => ({
        ...compare,
        options: compare.options.map((option) => ({ ...option, cost: money(option.cost) })),
      })),
      lines: trip.lines.map((line) => ({ ...line, price: money(line.price) })),
    },
    decisions: artifact.decisions.map((decision) => ({
      ...decision,
      options: decision.options.map((option) => ({ ...option, cost: money(option.cost) })),
      outcome: {
        ...decision.outcome,
        total: money(decision.outcome.total),
        delta: money(decision.outcome.delta),
      },
    })),
  };
}

export function isPublicDemoArtifact(value: unknown): value is PublicDemoArtifact {
  if (!value || typeof value !== "object") return false;
  const artifact = value as Partial<PublicDemoArtifact>;
  return artifact.schema_version === 1
    && typeof artifact.artifact_version === "string"
    && typeof artifact.region === "string"
    && typeof artifact.currency === "string"
    && Boolean(artifact.trip?.days.length)
    && Boolean(artifact.decisions?.length);
}

export async function fetchDemoArtifact(
  region: string,
  currency: string,
  signal?: AbortSignal,
): Promise<PublicDemoArtifact> {
  const params = new URLSearchParams({ region, currency });
  const response = await fetch(`/api/public/demo-run?${params}`, { cache: "force-cache", signal });
  if (!response.ok) throw new Error(`Public demo request failed: ${response.status}`);
  const artifact: unknown = await response.json();
  if (!isPublicDemoArtifact(artifact)) throw new Error("Public demo returned an invalid artifact");
  return artifact;
}

export function demoTripForLocale(region: string, currency: string): StageTrip {
  return demoArtifactForLocale(region, currency).trip;
}

export function demoDecisionsForLocale(region: string, currency: string): StageDecision[] {
  return demoArtifactForLocale(region, currency).decisions;
}

export const demoTrip = demoArtifactForLocale("EU", "EUR").trip;
export const demoDecisions = demoArtifactForLocale("EU", "EUR").decisions;

export const faq = [
  { q: "Is this run live?", a: "No. This is a curated regional run, captured and replayed so the page remains available without live provider dependencies." },
  { q: "Are these the prices I would pay?", a: "Treat these as representative beta figures. Prices are identified as estimates and checked again before booking." },
  { q: "Do I have to watch it?", a: "No. Skip to the finished plan at any point, or go straight to the planner and start your own trip." },
  { q: "Why compare transport?", a: "The planner measures practical door-to-door time and representative cost, then keeps the option that best fits the trip." },
  { q: "Can it book any of it?", a: "Not yet. It hands you into the provider flow and never holds a card." },
];

export const trustPoints = [
  "No account needed to plan. Your trip is saved in this browser until you sign in.",
  "We never take a payment and never hold your card. Booking finishes on the provider's own site.",
  "Every price is identified as a provider figure or a representative beta estimate, then rechecked before booking.",
  "Transport is compared across practical modes on every hop, and the losing options stay visible.",
];
