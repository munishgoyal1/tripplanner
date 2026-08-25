export interface Review {
  rating: number | null;
  text: string;
  author: string;
}

export interface PlaceOccurrence {
  day: number;
  stop: number;
  time: string;
}

export interface TripItem {
  kind: string;
  name: string;
  city?: string;
  selected: boolean;
  rating: number | null;
  review_count: number | null;
  address: string;
  summary: string;
  website: string;
  photos: string[];
  reviews: Review[];
  occurrences: PlaceOccurrence[];
}

// Lab 13 — lightweight browse row for the paged destination guide. Rich fields
// (multiple photos, reviews) are only fetched when a place is focused.
export interface PlaceRow {
  kind: string;
  name: string;
  city: string;
  selected: boolean;
  rating: number | null;
  review_count: number | null;
  address: string;
  summary: string;
  photo: string | null;
  website: string;
}

export interface PlaceGuidePage {
  items: PlaceRow[];
  cursor: string | null;
  total_count: number;
  remaining_count: number;
  available_cities: string[];
  available_kinds: string[];
}

export interface Budget {
  currency: string;
  spent: number;
  spent_display: string;
  travelers: number;
  per_traveler: number;
  per_traveler_display: string;
  breakdown: { flights?: number; hotels?: number; activities?: number };
  target: number | null;
  target_currency?: string;
  target_owner?: "user" | "legacy" | string;
  target_updated_at?: string;
  target_fx?: CostEvidenceLine["fx"] | null;
  target_display: string;
  remaining: number | null;
  remaining_display: string;
  pct_used: number | null;
  over_budget: boolean;
  estimated: boolean;
  evidence_coverage_pct: number;
  verified_spent: number | null;
  all_in_spent?: number | null;
  all_in_coverage_pct?: number;
  required_unknown?: string[];
}

export interface BudgetWhatIfProposal {
  id: string;
  decision_id: string;
  option_id: string;
  kind: "flight" | "lodging";
  subject: string;
  label: string;
  savings: number;
  currency: string;
  tradeoff: string;
  personalized: boolean;
}

export interface BudgetWhatIf {
  generated_on_demand: true;
  estimated: boolean;
  evidence_coverage_pct: number;
  currency: string;
  proposals: BudgetWhatIfProposal[];
}

export interface DecisionBatchChange {
  decision_id: string;
  option_id?: string | null;
}

export interface DecisionBatchApplyResult {
  ok: boolean;
  stale?: boolean;
  message: string;
  results: DecisionApplyResult[];
  failed_change?: DecisionBatchChange;
  total_cost?: number | null;
  delta?: number;
  currency?: string;
  view?: TripView;
  itinerary?: Itinerary;
}

export type WeatherCondition = "clear" | "partly_cloudy" | "cloudy" | "fog" | "rain" | "storm" | "snow" | "unknown";

export interface WeatherDay {
  date: string;
  summary: string;
  condition: WeatherCondition;
  high_c: number | null;
  low_c: number | null;
  precip_mm: number | null;
  precip_probability_pct: number | null;
}

export interface TripWeather {
  source: "forecast" | "seasonal_estimate" | "agent_climate_estimate";
  source_label: string;
  note: string;
  days: WeatherDay[];
  packing_advice: string[];
}

export interface CostEvidenceLine {
  kind: string;
  label: string;
  status: "live" | "stale" | "unverified" | "unpriced";
  amount?: number;
  currency?: string;
  provider?: string;
  checked_at?: string;
  expires_at?: string;
  reason?: string;
  components?: Array<{
    kind: string;
    label: string;
    amount: number;
    currency: string;
    inclusion: "reported" | "excluded" | "included" | "unknown" | string;
  }>;
  required_unknown?: string[];
  all_in_complete?: boolean;
  all_in_amount?: number;
  fx?: {
    from_currency: string;
    to_currency: string;
    rate: number;
    source: string;
    rate_date: string;
    fetched_at: string;
  };
}

/** What the trip costs according to recorded provider checks, not the model. */
export interface CostEvidence {
  currency: string;
  lines: CostEvidenceLine[];
  priced_total: number | null;
  all_in_total?: number | null;
  priced_count: number;
  stale_count: number;
  unverified_count: number;
  unpriced_count: number;
  complete: boolean;
  coverage_pct: number;
  all_in_count?: number;
  all_in_coverage_pct?: number;
  required_unknown?: string[];
  summary: string;
}

export interface TripOverview {
  destination: string;
  origin: string;
  departure_date: string;
  return_date: string;
  travelers: number | string;
  status: string;
  notes: string;
  counts: { flights: number; hotels: number; activities: number; days: number };
  total_cost: number | null;
  total_cost_display: string;
  cost_evidence?: CostEvidence | null;
  offer_comparisons?: Array<{
    subject_key: string;
    recommended_provider: string;
    recommended_label: string;
    recommended_all_in_total: number;
    currency: string;
    savings: number | null;
    compared_providers: string[];
    excluded_providers: Record<string, string>;
    applied_benefit?: {
      program: string;
      card_label: string;
      discount: number;
      currency: string;
      terms_url: string;
    } | null;
  }>;
  price_rechecks?: Array<{ kind: string; provider: string; reason: string }>;
  cost_baseline?: CostBaseline | null;
  provenance?: ProvenanceRow[];
  budget?: Budget | null;
  weather?: TripWeather | null;
  effort_notes?: string[];
  pacing_statement?: {
    day: number;
    remedy_day: number;
    statement: string;
    remedy: string;
  } | null;
  family_pills?: string[];
  constraints?: string[];
}

export type TransportMode =
  | "flight"
  | "train"
  | "road"
  | "coach"
  | "ferry"
  | "metro"
  | "walk";

/** A price is real or absent. There is no estimated tier. */
export type UnpricedReason = "no_source" | "source_failed" | "out_of_coverage";

export type PricedState = "full" | "partial" | "none";

export interface DecisionPrice {
  amount: number;
  currency: string;
  basis?: "per_traveller" | "per_party";
  amount_max?: number | null;
}

export interface DecisionSource {
  provider: string;
  url?: string;
  checked_at?: string;
  expires_at?: string | null;
  confidence?: "live" | "cached";
}

export interface DecisionOption {
  id: string;
  mode?: TransportMode | null;
  label: string;
  detail?: string;
  price: DecisionPrice | null;
  priced: boolean;
  unpriced_reason: UnpricedReason | null;
  duration_min?: number | null;
  door_to_door_min?: number | null;
  duration_estimated?: boolean;
  rejected_because?: string | null;
  source?: DecisionSource;
  lodging?: {
    checkin?: string;
    checkout?: string;
    room_name?: string;
    board_name?: string | null;
    refundable?: boolean | null;
    cancellation_summary?: string | null;
    address?: string | null;
    rating?: number | null;
    review_count?: number | null;
  } | null;
  flight?: {
    origin?: string;
    destination?: string;
    departure_date?: string;
    return_date?: string;
    cabin_class?: string;
    segments?: Array<Record<string, unknown>>;
    stops?: number;
    seats_remaining?: number | null;
    baggage?: Record<string, unknown> | null;
    terms?: Record<string, unknown> | null;
  } | null;
}

export interface Decision {
  id: string;
  kind: "transport_mode" | "lodging" | "flight" | "day_shape";
  subject: string;
  scope: {
    day?: number | null;
    from_place?: string;
    to_place?: string;
    date?: string;
  };
  rule: { code: string; text: string };
  state: "agent" | "overruled";
  priced: PricedState;
  /** The option currently in the plan — the override when there is one. */
  chosen_option_id: string;
  /** What the agent picked, so "undo" has something to point at. */
  agent_option_id?: string;
  override?: DecisionOverride | null;
  effect: { total_cost: number; delta?: number; currency: string };
  options: DecisionOption[];
}

export interface DecisionOverride {
  option_id: string;
  at: string;
  previous_option_id: string;
  effect: { total_cost?: number | null; delta?: number | null; currency: string };
  warnings: string[];
}

/** When we last looked at a live source, and whether that look still holds. */
export interface ProvenanceRow {
  kind: string;
  provider: string;
  checked_at: string;
  expires_at: string;
  /** False once the quote has aged out. Never present it as today's price. */
  current: boolean;
  text: string;
}

/** What the plan cost before the traveller started overruling it. */
export interface CostBaseline {
  first: number;
  current: number;
  saved: number;
  currency: string;
  first_display: string;
  current_display: string;
  saved_display: string;
}

export interface DecisionApplyResult {
  ok: boolean;
  stale?: boolean;
  message: string;
  decision_id: string;
  option_id: string | null;
  previous_option_id: string | null;
  total_cost: number | null;
  delta: number;
  currency: string;
  warnings: string[];
  view?: TripView;
  itinerary?: Itinerary;
}

export interface TripView {
  trip_id: string | null;
  /** The revision an override must quote back to avoid clobbering newer work. */
  updated_at?: string | null;
  has_trip: boolean;
  title: string;
  destination: string;
  focus: { kind: string; name: string; day?: number; stop?: number } | null;
  is_fallback: boolean;
  empty_message: string;
  overview: TripOverview | null;
  available_days: number[];
  items: TripItem[];
  decisions?: Decision[];
  alerts?: string[];
  feedback?: {
    count: number;
    last_at?: string | null;
    last_rating?: number | null;
    last_sentiment?: "up" | "down" | null;
  };
}

export type ChatRole = "user" | "assistant";

export interface ToolTraceEntry {
  name: string;
  args?: string;
  duration_ms?: number;
}

/** A stop a reply changed, so the conversation can navigate the workspace. */
export interface TurnEffect {
  kind: string;
  name: string;
  day?: number;
  stop?: number;
  change: "added" | "removed" | "moved";
}

export interface ChatMessage {
  role: ChatRole;
  text: string;
  tools?: string[];
  tool_trace?: ToolTraceEntry[];
  /** Epoch ms the turn was recorded at; groups the transcript by day. */
  ts?: number;
  /** Wall-clock seconds the reply took, retained after the turn settles. */
  seconds?: number;
  effects?: TurnEffect[];
}

export interface MapPin {
  id: string;
  name: string;
  source_name?: string;
  kind: string;
  selected: boolean;
  day: number | null;
  lat: number;
  lng: number;
  rating: number | null;
  address: string;
  photo: string | null;
  occurrences: PlaceOccurrence[];
}

export interface RouteMetrics {
  distance_km: number;
  duration_min: number;
  mode: string;
  distance_display: string;
  duration_display: string;
  detail?: string;
}

export interface DaySchedule {
  start: string;
  end: string;
  duration_min: number;
  duration_display: string;
  travel_duration_min: number;
  travel_duration_display: string;
  estimated: boolean;
}

export interface MapLeg extends RouteMetrics {
  from_pin_id: string;
  to_pin_id: string;
  intercity?: boolean;
  route_circuit_id?: string;
}

export interface MapRoadWaypoint {
  pin_id: string;
  role: "origin" | "scenic" | "meal" | "destination";
}

export interface MapRoadCircuit {
  id: string;
  day: number;
  mode: "Drive" | "Bus";
  label: string;
  pin_ids: string[];
  waypoints?: MapRoadWaypoint[];
  legs: MapLeg[];
  route: RouteMetrics;
}

export type MapDriveCircuit = Omit<MapRoadCircuit, "mode"> & { mode: "Drive" };

export interface MapDay {
  day: number;
  label: string;
  context_name?: string;
  color: string;
  pin_ids: string[];
  circuit_pin_ids?: string[];
  route: RouteMetrics;
  schedule?: DaySchedule;
  legs?: MapLeg[];
}

export interface MapAirport {
  id: string;
  name: string;
  kind: string;
  lat: number;
  lng: number;
}

/** What is lost when the map cannot place a stop, worst first. */
export type UnmappedStopTier = "anchor" | "place" | "label";

export type UnmappedStopReason = "no_match" | "no_location" | "not_a_place";

export interface UnmappedStopCandidate {
  name: string;
  place_id: string | null;
  lat: number | null;
  lng: number | null;
}

/** An itinerary stop the map could not pin, and why. */
export interface UnmappedStop {
  name: string;
  kind: string;
  day: number | null;
  tier: UnmappedStopTier;
  reason: UnmappedStopReason;
  candidate: UnmappedStopCandidate | null;
}

export interface MapView {
  enabled: boolean;
  destination: string;
  center: { lat: number; lng: number } | null;
  pins: MapPin[];
  days: MapDay[];
  road_circuits?: MapRoadCircuit[];
  drive_circuits?: MapDriveCircuit[];
  available_days: number[];
  unscheduled_pin_ids: string[];
  unmapped_stops?: UnmappedStop[];
  airport: MapAirport | null;
  empty_message: string | null;
}

export interface ItineraryStop {
  name: string;
  kind: string;
  time: string;
  /** Set on an intercity leg that came out of a recorded comparison. */
  decision_id?: string | null;
  arrival_time?: string;
  arrival_time_estimated?: boolean;
  terminal_role?: "departure" | "connection" | "arrival";
  duration_min: number | null;
  distance_km?: number | null;
  route_circuit_id?: string;
  duration_estimated?: boolean;
  operational_time_display?: string;
  note: string;
  booked: boolean;
  selected: boolean;
  color: string;
  opening_hours?: string;
  cost_display?: string;
  insight?: string;
  concern?: string;
  departure_time?: string;
  expected_arrival_time?: string;
  time_estimated?: boolean;
  buffer_before_min?: number;
  buffer_before_display?: string;
  timing_conflict_min?: number;
  timing_conflict_display?: string;
  rating?: number | null;
  review_count?: number | null;
  popularity_score?: number | null;
  travel_from_previous?: RouteMetrics;
}

export interface ItineraryDay {
  day: number;
  date: string;
  title: string;
  summary: string;
  color: string;
  stops: ItineraryStop[];
  reachability?: string;
  google_maps_url?: string;
  route?: MapDay["route"];
  schedule?: DaySchedule;
  weather?: WeatherDay | null;
}

export interface Itinerary {
  has_itinerary: boolean;
  destination: string;
  currency: string;
  days: ItineraryDay[];
  stats: { days: number; stops: number; booked: number };
}

/** A check the planner ran, or could not run, over the trip. */
export type VerificationStatus = "passed" | "failed" | "unverified";

export interface VerificationGap {
  name: string;
  day: number | null;
  missing: string[];
}

export interface VerificationCheck {
  code: string;
  rule: string;
  statement: string;
  status: VerificationStatus;
  /** A contradiction rests on a fetched fact; an advisory on estimated travel. */
  severity: "contradiction" | "advisory";
  findings: string[];
  gaps: VerificationGap[];
}

export interface VerificationDay {
  day: number;
  status: VerificationStatus;
  findings: string[];
  advisories: string[];
  unverified: string[];
  holiday: string;
}

export interface PlaceFactRefreshItem {
  name: string;
  days: number[];
  changed?: string[];
}

export interface ClosureAdvisory extends PlaceFactRefreshItem {
  title: string;
  url: string;
  snippet: string;
}

export interface ClosureWatch {
  status: "checked" | "failed" | "unavailable";
  advisories: ClosureAdvisory[];
}

export interface PlaceFactFreshness {
  checked_at: string;
  checked: number;
  total: number;
  comparison_available?: boolean;
  changes: PlaceFactRefreshItem[];
  failed: PlaceFactRefreshItem[];
  closure_watch?: ClosureWatch;
}

/** "unverified" at trip level means there was nothing to check yet. */
export interface TripVerification {
  verdict: "clear" | "partial" | "advisories" | "issues" | "unverified";
  counts: { total: number; passed: number; failed: number; unverified: number };
  checks: VerificationCheck[];
  days: VerificationDay[];
  unverified_stops: VerificationGap[];
  freshness?: PlaceFactFreshness | null;
}

export interface TripFreshnessResult extends PlaceFactFreshness {
  ok: boolean;
  stale: boolean;
  message: string;
  verification: TripVerification;
}

export interface RepairMove {
  name: string;
  from_day: number;
  to_day: number;
  time: string;
}

/** A finding the planner may not fix alone, because the stop is the user's. */
export interface BlockedFinding {
  code: string;
  day: number | null;
  stop: string;
  message: string;
  reason: string;
}

export interface TripRepairResult {
  ok: boolean;
  stale: boolean;
  changed: boolean;
  message: string;
  moves: RepairMove[];
  blocked: BlockedFinding[];
  before: { contradictions: number; travel_min: number };
  after: { contradictions: number; travel_min: number };
  view?: TripView;
  itinerary?: Itinerary;
  verification?: TripVerification;
}

/** Every panel's view-model for one trip, returned together on a trip switch. */
export interface TripWorkspaceView {
  view: TripView;
  map: MapView | null;
  itinerary: Itinerary | null;
}

export interface SavedTrip {
  trip_id: string;
  trip_number?: number;
  destination: string;
  departure_date: string;
  return_date: string;
  status: string;
  total_cost: number;
  currency: string;
  counts: { flights: number; hotels: number; activities: number };
  updated_at: string;
  is_active: boolean;
}

export interface SelectItemOptions {
  start_day?: number;
  end_day?: number;
  day?: number;
  source_day?: number;
  source_stop?: number;
  replace_stay?: boolean;
}

export interface SelectionPlacement {
  day: number;
  stop: number;
  name: string;
}

export interface PlannerReview {
  severity: "warning";
  day: number;
  summary: string;
  prompt: string;
}

export interface DeselectItemOptions {
  day?: number;
  stop?: number;
  all_occurrences?: boolean;
}

export interface ToolEventExtras {
  args?: string;
  duration_ms?: number;
}

export interface TripInputOption {
  value: string;
  label: string;
  detail?: string;
}

export interface TripInputField {
  id: string;
  label: string;
  kind: "single" | "multi" | "boolean" | "number" | "text" | "date";
  value: string | string[] | boolean | number;
  options?: TripInputOption[];
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
}

export interface TripInputRequest {
  version: 1;
  request_id: string;
  question: string;
  known_context: string[];
  fields: TripInputField[];
  submit_label: string;
  allow_skip: boolean;
}

/** One line of what the planner actually did, derived from a tool's own output. */
export interface Receipt {
  seq: number;
  at: string;
  kind: string;
  text: string;
  detail?: string;
  decision_id?: string;
  source?: string;
}

export interface StreamHandlers {
  onToken: (text: string) => void;
  onTool: (name: string, phase: "start" | "end", extras?: ToolEventExtras) => void;
  onReceipt?: (receipt: Receipt) => void;
  onProgress?: (stage: "thinking" | "reviewing" | "saving") => void;
  onInputRequest?: (request: TripInputRequest) => void;
  onDone: (reply: string, tripId?: string) => void;
  onError: (message: string) => void;
}

export interface StreamOptions {
  proposalOnly?: boolean;
  requestId?: string;
  signal?: AbortSignal;
}