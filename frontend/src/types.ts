// Cross-platform contracts live in packages/tripplanner-client.
export * from "@tripplanner/client/types";

// Web-only destination and browser map configuration contracts.

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

export interface MapsConfig {
  enabled: boolean;
  key: string;
}
export type BrowserMapsConfig = MapsConfig;
