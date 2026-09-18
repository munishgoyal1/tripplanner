import { BASE, apiFetch, getUserId } from "./auth/authSession";

export type Category = "flights" | "hotels" | "tickets" | "transport";
export interface Cap { amount: number; currency: string }
export interface Actual {
  product: string; provider: string; amount: number | null; currency: string;
  start_date: string; end_date: string; time: string; reference: string; notes: string;
  url?: string;
}
export interface Choice {
  id: string; name: string; amount: number | null; currency: string;
  start_date: string; end_date: string; time: string; provider: string;
  checked_at: string; expires_at: string; complete_cost: boolean;
  url: string; handoff: string; details: Record<string, unknown>;
  reason?: string; recommended?: boolean;
  context_warning?: string;
}
export interface BookingRow extends Choice {
  category: Category; decision_id: string; option_id: string;
  alternatives: Choice[]; booked: boolean; actual: Actual | null;
  intended: Choice | null; intent_state: string; evidence: string; disposition: string;
  selected: boolean;
  warnings?: string[];
}
export interface BookingView {
  research_defaults?: Record<"flights" | "hotels", { id: string; label: string; search: Search; assumptions: string[] }[]>;
  trip_id: string; updated_at: string; destination: string; travelers: string | number;
  rows: BookingRow[]; coverage: string; locked_count: number; booked_count: number;
  schedule?: { date: string; stops: { name: string; time: string; booked: boolean }[] }[];
  category_caps: Partial<Record<Category, Cap>>;
  budgets: Partial<Record<Category, Cap & {
    known_total: number; unknown_items: number; incomplete_items: number; status: string;
  }>>;
}
export interface Search {
  category: "flights" | "hotels"; origin: string; destination: string;
  start_date: string; end_date: string; adults: number; rooms: number;
  children: number; infants: number; children_ages: number[];
  currency: string; nationality: string; cabin: string; refundable_only: boolean;
}
export interface Command {
  action: "choose" | "lock" | "unlock" | "report" | "manual" | "caps" | "disposition" | "research";
  item_id?: string; option_id?: string; actual?: Actual;
  caps?: Partial<Record<Category, Cap>>; disposition?: string; search?: Search;
}
export interface BookingResult {
  ok: boolean; message: string; bookings: BookingView;
  before?: BookingView; preview_token?: string; warnings?: string[];
  research_result?: string;
}
async function json<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    const detail = typeof payload.detail === "string" ? payload.detail : payload.message;
    throw new Error(detail || "The request could not be completed. Check the fields and reload if the trip changed.");
  }
  return payload as T;
}
export async function fetchBookings(tripId = "", signal?: AbortSignal): Promise<BookingView> {
  const query = new URLSearchParams({ user_id: getUserId(), trip_id: tripId });
  return json(await apiFetch(`${BASE}/trip/bookings?${query}`, { signal }));
}
export async function bookingCommand(view: BookingView, command: Command, previewToken?: string): Promise<BookingResult> {
  return json(await apiFetch(`${BASE}/trip/bookings`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...command, user_id: getUserId(), trip_id: view.trip_id,
      updated_at: view.updated_at, preview: !previewToken, preview_token: previewToken || "" }),
  }));
}
export async function shareBookings(view: BookingView): Promise<string> {
  const result = await json<{ url: string }>(await apiFetch(`${BASE}/trip/bookings/share`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getUserId(), trip_id: view.trip_id, updated_at: view.updated_at }),
  }));
  return result.url;
}
export function bookingJsonUrl(view: BookingView): string {
  return `${BASE}/trip/bookings/export.json?${new URLSearchParams({
    user_id: getUserId(), trip_id: view.trip_id, updated_at: view.updated_at,
  })}`;
}
