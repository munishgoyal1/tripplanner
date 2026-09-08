// The shape of what scripts/capture_public_run.py writes. It is the engine's own
// output — trip view, decisions, receipts and a real re-settle for every option the
// planner turned down — so the page below can show the run without retelling it.

export interface CapturedReceipt {
  seq: number;
  at: string;
  kind: string;
  text: string;
  detail?: string;
  source?: string;
  decision_id?: string;
  priced?: string;
}

export interface CapturedStop {
  name: string;
  kind: string;
  time: string;
  note?: string;
  cost_display?: string;
  duration_min?: number | null;
  distance_km?: number | null;
  rating?: number | null;
  review_count?: number | null;
}

export interface CapturedDay {
  day: number;
  date: string;
  title: string;
  summary?: string;
  color: string;
  stops: CapturedStop[];
}

export interface CapturedOption {
  id: string;
  mode: string;
  label: string;
  detail: string;
  price: number | null;
  priced: boolean;
  unpriced_reason?: string | null;
  duration_min: number;
  door_to_door_min: number;
  rejected_because: string | null;
}

export interface CapturedDecision {
  id: string;
  subject: string;
  scope: { day?: number; date?: string };
  rule_text: string;
  chosen_option_id: string;
  priced: string;
  options: CapturedOption[];
}

export interface CapturedOverrule {
  decision_id: string;
  option_id: string;
  label: string;
  message: string;
  total_cost: number;
  delta: number;
  currency: string;
  warnings: string[];
  changes: string[];
}

export interface CapturedHotel {
  name: string;
  city: string;
  address?: string;
  checkin?: string;
  checkout?: string;
  rating?: number | null;
  review_count?: number | null;
  price_per_night?: number | null;
  price_total?: number | null;
  total_price?: number | null;
  currency?: string;
  /** What the agent wrote when no provider would quote the room. */
  note?: string;
}

// A record per booking rather than per leg: a return trip is one row with the way back on it.
export interface CapturedFlight {
  airline?: string;
  flight_number?: string;
  from?: string;
  to?: string;
  departure?: string;
  arrival?: string;
  return_departure?: string;
  return_arrival?: string;
  price_per_person?: number | null;
  total_price?: number | null;
  cabin_class?: string;
}

export interface CapturedProvenance {
  kind: string;
  provider: string;
  checked_at: string;
  current: boolean;
  text: string;
}

export interface CapturedRun {
  captured_at: string;
  trip: {
    id: string;
    destination: string;
    departure_date: string;
    return_date: string;
    travellers: string;
    total_cost: number;
    currency: string;
  };
  overview: { total_cost_display?: string; cost_baseline?: unknown };
  plan: {
    selected_hotels?: CapturedHotel[];
    selected_flights?: CapturedFlight[];
    day_wise_itinerary?: Array<{ cost_estimate?: number | null }>;
  };
  receipts: CapturedReceipt[];
  days: CapturedDay[];
  stats: { days: number; stops: number; booked: number };
  decisions: CapturedDecision[];
  overrules: CapturedOverrule[];
  provenance: CapturedProvenance[];
}
