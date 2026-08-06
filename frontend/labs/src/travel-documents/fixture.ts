// One realistic Lisbon trip for an Indian-passport family, used to argue about where
// travel documents live. The facts are chosen so the deterministic checks have real
// answers: one passport fails the Schengen validity rule, one traveller has nothing
// on file, and the insurance actually satisfies the €30,000 medical minimum.

export type DocumentKind =
  | "passport"
  | "visa"
  | "insurance"
  | "vaccination"
  | "licence"
  | "loyalty";

export type CheckSeverity = "blocker" | "warning" | "ok";

export interface Traveller {
  id: string;
  name: string;
  relationship: string;
  initials: string;
}

export interface ExtractedField {
  label: string;
  value: string;
  /** Masked values are stored masked; the original document is never kept. */
  masked?: boolean;
  confidence: number;
}

export interface TravellerDocument {
  id: string;
  travellerId: string;
  kind: DocumentKind;
  title: string;
  issuer: string;
  expiry?: string;
  expiryLabel?: string;
  fields: ExtractedField[];
  capturedOn: string;
  reusedFrom?: string;
  supersedes?: string;
}

export interface BookingDocument {
  id: string;
  stopId: string;
  provider: string;
  reference: string;
  title: string;
  when: string;
  amount: string;
  capturedOn: string;
  fields: ExtractedField[];
}

export interface ReadinessCheck {
  id: string;
  severity: CheckSeverity;
  travellerId?: string;
  title: string;
  detail: string;
  rule: string;
  /** Deterministic checks are computed; grounded ones cite a live source. */
  origin: "computed" | "grounded";
  source?: string;
  action?: string;
}

export interface ItineraryStop {
  id: string;
  day: number;
  time: string;
  name: string;
  kind: "flight" | "hotel" | "attraction" | "meal";
  booked: boolean;
}

export const tripLabel = "Lisbon · 8–13 Oct 2026";
export const tripExitDate = "13 Oct 2026";

export const travellers: Traveller[] = [
  { id: "self", name: "Munish Goyal", relationship: "You", initials: "MG" },
  { id: "spouse", name: "Priya Goyal", relationship: "Spouse", initials: "PG" },
  { id: "child", name: "Aarav Goyal", relationship: "Son · 9", initials: "AG" },
];

export const travellerDocuments: TravellerDocument[] = [
  {
    id: "doc-passport-self",
    travellerId: "self",
    kind: "passport",
    title: "Passport",
    issuer: "India",
    expiry: "2031-04-18",
    expiryLabel: "18 Apr 2031",
    capturedOn: "12 Mar 2026",
    reusedFrom: "Kyoto, Mar 2026",
    fields: [
      { label: "Issuing country", value: "India", confidence: 0.99 },
      { label: "Document number", value: "Z••••••4", masked: true, confidence: 0.98 },
      { label: "Date of birth", value: "11 Feb 1984", confidence: 0.99 },
      { label: "Expiry", value: "18 Apr 2031", confidence: 0.99 },
    ],
  },
  {
    id: "doc-visa-self",
    travellerId: "self",
    kind: "visa",
    title: "Schengen visa · Type C",
    issuer: "Portugal · multi-entry",
    expiry: "2026-12-15",
    expiryLabel: "15 Dec 2026",
    capturedOn: "02 Aug 2026",
    fields: [
      { label: "Destination", value: "Schengen area", confidence: 0.97 },
      { label: "Entry type", value: "Multiple", confidence: 0.96 },
      { label: "Valid from", value: "01 Jun 2026", confidence: 0.98 },
      { label: "Valid until", value: "15 Dec 2026", confidence: 0.98 },
      { label: "Days permitted", value: "90 in 180", confidence: 0.93 },
    ],
  },
  {
    id: "doc-passport-spouse",
    travellerId: "spouse",
    kind: "passport",
    title: "Passport",
    issuer: "India",
    expiry: "2026-11-20",
    expiryLabel: "20 Nov 2026",
    capturedOn: "12 Mar 2026",
    reusedFrom: "Kyoto, Mar 2026",
    fields: [
      { label: "Issuing country", value: "India", confidence: 0.99 },
      { label: "Document number", value: "Z••••••1", masked: true, confidence: 0.97 },
      { label: "Date of birth", value: "30 Sep 1986", confidence: 0.99 },
      { label: "Expiry", value: "20 Nov 2026", confidence: 0.99 },
    ],
  },
  {
    id: "doc-insurance",
    travellerId: "self",
    kind: "insurance",
    title: "Travel insurance · family",
    issuer: "ICICI Lombard · policy TR••••882",
    expiry: "2026-10-20",
    expiryLabel: "20 Oct 2026",
    capturedOn: "28 Jul 2026",
    fields: [
      { label: "Medical cover", value: "€50,000", confidence: 0.95 },
      { label: "Covers", value: "8–20 Oct 2026", confidence: 0.97 },
      { label: "Assistance line", value: "+91 22 6787 2000", confidence: 0.99 },
      { label: "Insured", value: "3 travellers", confidence: 0.94 },
    ],
  },
];

export const bookingDocuments: BookingDocument[] = [
  {
    id: "bk-flight-out",
    stopId: "stop-flight-out",
    provider: "TAP Air Portugal",
    reference: "4XQ2P9",
    title: "BLR → LIS · TP 1234",
    when: "8 Oct · 02:40 → 11:25",
    amount: "₹1,42,300",
    capturedOn: "29 Jul 2026",
    fields: [
      { label: "Confirmation", value: "4XQ2P9", confidence: 0.99 },
      { label: "Passengers", value: "3", confidence: 0.98 },
      { label: "Baggage", value: "2 × 23kg each", confidence: 0.91 },
      { label: "Free change until", value: "01 Oct 2026", confidence: 0.88 },
    ],
  },
  {
    id: "bk-hotel",
    stopId: "stop-hotel",
    provider: "Bairro Alto Hotel",
    reference: "BA-88421",
    title: "Deluxe room · 5 nights",
    when: "8 Oct → 13 Oct",
    amount: "€1,240",
    capturedOn: "29 Jul 2026",
    fields: [
      { label: "Confirmation", value: "BA-88421", confidence: 0.99 },
      { label: "Check-in", value: "8 Oct, from 15:00", confidence: 0.97 },
      { label: "Free cancellation until", value: "05 Oct 2026", confidence: 0.94 },
      { label: "Breakfast", value: "Included", confidence: 0.9 },
    ],
  },
];

export const itinerary: ItineraryStop[] = [
  { id: "stop-flight-out", day: 1, time: "02:40", name: "BLR → LIS · TP 1234", kind: "flight", booked: true },
  { id: "stop-hotel", day: 1, time: "15:00", name: "Bairro Alto Hotel", kind: "hotel", booked: true },
  { id: "stop-timeout", day: 1, time: "19:30", name: "Time Out Market", kind: "meal", booked: false },
  { id: "stop-jeronimos", day: 2, time: "09:30", name: "Jerónimos Monastery", kind: "attraction", booked: false },
  { id: "stop-belem", day: 2, time: "12:15", name: "Pastéis de Belém", kind: "meal", booked: false },
  { id: "stop-tram", day: 2, time: "15:00", name: "Tram 28 · Graça loop", kind: "attraction", booked: false },
  { id: "stop-sintra", day: 3, time: "08:45", name: "Sintra day trip", kind: "attraction", booked: false },
];

export const readinessChecks: ReadinessCheck[] = [
  {
    id: "chk-spouse-passport",
    severity: "blocker",
    travellerId: "spouse",
    title: "Priya's passport is too close to expiry for Portugal",
    detail:
      "Expires 20 Nov 2026, which is 38 days after you leave the Schengen area on 13 Oct. Portugal requires at least 3 months of validity beyond your exit date.",
    rule: "expiry − exit_date ≥ 3 months",
    origin: "computed",
    action: "Renewal takes 4–6 weeks. Start it now or move the trip.",
  },
  {
    id: "chk-child-passport",
    severity: "blocker",
    travellerId: "child",
    title: "Aarav has no passport on file",
    detail: "He is on the flight booking and the hotel reservation, but nothing on this account records his passport.",
    rule: "every traveller on the trip has a passport record",
    origin: "computed",
    action: "Add his passport details.",
  },
  {
    id: "chk-child-visa",
    severity: "blocker",
    travellerId: "child",
    title: "Aarav has no Schengen visa recorded",
    detail:
      "Indian passport holders need a Schengen short-stay visa for Portugal. Minors apply with both parents' consent and the applications are usually lodged together.",
    rule: "Indian passport → Schengen requires a Type C visa",
    origin: "grounded",
    source: "VFS Global Portugal · India, checked 6 Aug 2026",
    action: "Add his visa once issued.",
  },
  {
    id: "chk-self-visa",
    severity: "ok",
    travellerId: "self",
    title: "Your Schengen visa covers the whole trip",
    detail: "Multi-entry Type C valid 1 Jun – 15 Dec 2026, so 8–13 Oct sits inside the window with 63 days to spare.",
    rule: "valid_from ≤ trip_start and trip_end ≤ valid_until",
    origin: "computed",
  },
  {
    id: "chk-insurance",
    severity: "ok",
    title: "Insurance meets the Schengen medical minimum",
    detail: "€50,000 of medical cover against a €30,000 requirement, covering 8–20 Oct for all three travellers.",
    rule: "medical_cover ≥ €30,000 and policy window covers the trip",
    origin: "grounded",
    source: "EU Visa Code Art. 15, checked 6 Aug 2026",
  },
];

export const pendingExtraction: ExtractedField[] = [
  { label: "Issuing country", value: "India", confidence: 0.99 },
  { label: "Document number", value: "Z••••••7", masked: true, confidence: 0.96 },
  { label: "Surname", value: "Goyal", confidence: 0.99 },
  { label: "Given name", value: "Aarav", confidence: 0.98 },
  { label: "Date of birth", value: "14 Jun 2017", confidence: 0.97 },
  { label: "Expiry", value: "09 Jan 2030", confidence: 0.99 },
];

export const blockerCount = readinessChecks.filter((check) => check.severity === "blocker").length;
