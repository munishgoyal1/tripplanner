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
}
