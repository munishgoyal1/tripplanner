// Mirrors the Python view-model contract in src/multiagent/web/trip_view.py.
// Keep these types in sync with build_view()'s output shape.

export interface Review {
  rating: number | null;
  text: string;
  author: string;
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
  family_pills?: string[];
}

export interface TripView {
  has_trip: boolean;
  title: string;
  destination: string;
  focus: { kind: string; name: string } | null;
  is_fallback: boolean;
  empty_message: string;
  overview: TripOverview;
  items: TripItem[];
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

export interface KeyAttraction {
  name: string;
  rating: number | null;
  review_count: number | null;
  summary: string;
  photo: string | null;
}

export interface DestinationReview {
  place: string;
  rating: number | null;
  text: string;
  author: string;
}

export interface NewsItem {
  title: string;
  url: string;
  content: string;
}

export interface DestinationOverview {
  destination: string;
  summary: string;
  rating: number | null;
  review_count: number | null;
  photos: string[];
  key_attractions: KeyAttraction[];
  reviews: DestinationReview[];
  news: NewsItem[];
  map_url?: string;
}

// ---- Interactive map view-model (mirrors build_map_view) ------------------

export interface MapPin {
  id: string;
  name: string;
  kind: string; // hotel | attraction | airport
  selected: boolean;
  day: number | null;
  lat: number;
  lng: number;
  rating: number | null;
  address: string;
  photo: string | null;
}

export interface MapDay {
  day: number;
  label: string;
  color: string;
  pin_ids: string[];
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
  unscheduled_pin_ids: string[];
  airport: MapAirport | null;
  empty_message: string | null;
}

export interface MapsConfig {
  enabled: boolean;
  key: string;
}

// ---- Structured itinerary (mirrors build_itinerary) -----------------------

export interface ItineraryStop {
  name: string;
  kind: string; // hotel | attraction | meal | transport | flight | other
  time: string;
  duration_min: number | null;
  note: string;
  booked: boolean;
  selected: boolean;
  color: string;
}

export interface ItineraryDay {
  day: number;
  date: string;
  title: string;
  summary: string;
  color: string;
  stops: ItineraryStop[];
}

export interface Itinerary {
  has_itinerary: boolean;
  destination: string;
  currency: string;
  days: ItineraryDay[];
  stats: { days: number; stops: number; booked: number };
}

// ---- Saved trips (mirrors trip_planner.list_saved_trips) ------------------

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
