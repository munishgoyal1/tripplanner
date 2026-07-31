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

export interface Budget {
  currency: string;
  spent: number;
  spent_display: string;
  travelers: number;
  per_traveler: number;
  per_traveler_display: string;
  breakdown: { flights?: number; hotels?: number; activities?: number };
  target: number | null;
  target_display: string;
  remaining: number | null;
  remaining_display: string;
  pct_used: number | null;
  over_budget: boolean;
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
  budget?: Budget | null;
  weather?: TripWeather | null;
  family_pills?: string[];
  constraints?: string[];
}

export interface TripView {
  has_trip: boolean;
  title: string;
  destination: string;
  focus: { kind: string; name: string } | null;
  is_fallback: boolean;
  empty_message: string;
  overview: TripOverview | null;
  available_days: number[];
  items: TripItem[];
  alerts?: string[];
}

export type ChatRole = "user" | "assistant";

export interface ToolTraceEntry {
  name: string;
  args?: string;
  duration_ms?: number;
}

export interface ChatMessage {
  role: ChatRole;
  text: string;
  tools?: string[];
  tool_trace?: ToolTraceEntry[];
}

export interface MapPin {
  id: string;
  name: string;
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
}

export interface MapDay {
  day: number;
  label: string;
  color: string;
  pin_ids: string[];
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

export interface MapView {
  enabled: boolean;
  destination: string;
  center: { lat: number; lng: number } | null;
  pins: MapPin[];
  days: MapDay[];
  available_days: number[];
  unscheduled_pin_ids: string[];
  airport: MapAirport | null;
  empty_message: string | null;
}

export interface ItineraryStop {
  name: string;
  kind: string;
  time: string;
  duration_min: number | null;
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

export interface SavedTrip {
  trip_id: string;
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
  kind: "single" | "multi" | "boolean" | "number";
  value: string | string[] | boolean | number;
  options?: TripInputOption[];
  min?: number;
  max?: number;
  step?: number;
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

export interface StreamHandlers {
  onToken: (text: string) => void;
  onTool: (name: string, phase: "start" | "end", extras?: ToolEventExtras) => void;
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