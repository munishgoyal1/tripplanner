// The shape `trip_audit.py --report` writes. A hand-written mirror rather than
// something generated: it is small, and a mismatch shows up immediately as an
// empty column instead of a build step nobody remembers to run.

export type Rule = {
  code: string;
  title: string;
  statement: string;
  severity: "gate" | "report" | "observe";
  evaluated_in: string;
  hits: number;
};

export type Finding = {
  record_id: string;
  day: number | null;
  provenance: string;
  message: string;
};

export type Group = {
  key: string;
  rule: string;
  symptom: string;
  count: number;
  new: boolean;
  accepted_on: string;
  provenances: Record<string, number>;
  example: string;
  findings: Finding[];
};

export type TripRecord = {
  id: string;
  provenance: string;
  source: string;
  destination: string;
  days: number;
  departure_date: string;
  return_date: string;
  user_id: string;
  trip_id: string;
  openable: boolean;
  findings: number;
};

export type Observation = { label: string; value: string; detail: string };

export type Report = {
  version: number;
  generated_at: string;
  corpus: {
    size: number;
    provenance: Record<string, number>;
    sources: string[];
    skipped: string[];
  };
  rules: Rule[];
  groups: Group[];
  retired: string[];
  observations: Observation[];
  records: TripRecord[];
};

export const AUDIT_COMMAND = "./scripts/mac/user/validation/Audit-Trips.command --report";

export async function loadReport(): Promise<Report | null> {
  const response = await fetch("/audit-report.json", { cache: "no-store" });
  if (!response.ok) return null;
  const body = (await response.json()) as Report | { error: string };
  return "error" in body ? null : body;
}

const APP_URL = (import.meta.env.VITE_APP_URL as string | undefined) || "http://127.0.0.1:5173";

/** The product UI, showing this trip under the identity that owns it. */
export function openUrl(record: TripRecord): string {
  const params = new URLSearchParams({ inspect: record.user_id });
  if (record.trip_id) params.set("trip", record.trip_id);
  return `${APP_URL}/?${params.toString()}`;
}

export function howLongAgo(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}
