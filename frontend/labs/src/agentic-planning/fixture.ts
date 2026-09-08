/**
 * The owner's real failure case: a Bengaluru -> Indore round trip. Both reported
 * defects reproduce on this fixture with the production placement algorithm.
 */

export type StopKind = "flight" | "stay" | "transfer" | "attraction" | "meal";

export interface Stop {
  id: string;
  kind: StopKind;
  title: string;
  city: string;
  day: number;
  /** HH:MM */
  start: string;
  durationMin: number;
  lat: number;
  lng: number;
  /** Anchors define the trip's shape and may only change through their own operation. */
  locked?: boolean;
  role?: "arrival" | "departure" | "check-in" | "check-out";
  fromCity?: string;
  toCity?: string;
  openFrom?: string;
  openTo?: string;
  booked?: boolean;
  ref?: string;
  note?: string;
}

export interface DayMeta {
  day: number;
  date: string;
  weekday: string;
  color: string;
}

export interface Candidate {
  id: string;
  title: string;
  city: string;
  lat: number;
  lng: number;
  durationMin: number;
  openFrom: string;
  openTo: string;
  rating: number;
  note: string;
}

export const HOME = "Bengaluru";
export const DESTINATION = "Indore";

export const dayMeta: DayMeta[] = [
  { day: 1, date: "5 Nov", weekday: "Thu", color: "#e11d48" },
  { day: 2, date: "6 Nov", weekday: "Fri", color: "#0f766e" },
  { day: 3, date: "7 Nov", weekday: "Sat", color: "#b45309" },
  { day: 4, date: "8 Nov", weekday: "Sun", color: "#6d28d9" },
  { day: 5, date: "9 Nov", weekday: "Mon", color: "#0369a1" },
];

export const baseTrip: Stop[] = [
  {
    id: "flight-out",
    kind: "flight",
    title: "6E-6357 Bengaluru → Indore",
    city: DESTINATION,
    fromCity: HOME,
    toCity: DESTINATION,
    day: 1,
    start: "06:15",
    durationMin: 110,
    lat: 22.7218,
    lng: 75.8011,
    locked: true,
    role: "arrival",
    booked: true,
    ref: "PNR RTQ4XZ",
    note: "Lands Indore 08:05",
  },
  {
    id: "stay-in",
    kind: "stay",
    title: "Check in · Sayaji Indore (5★)",
    city: DESTINATION,
    day: 1,
    start: "09:30",
    durationMin: 45,
    lat: 22.7533,
    lng: 75.8937,
    locked: true,
    role: "check-in",
    booked: true,
    ref: "Booking 4471-9922",
    note: "₹9,400 per night · 4 nights",
  },
  {
    id: "rajwada",
    kind: "attraction",
    title: "Rajwada Palace",
    city: DESTINATION,
    day: 1,
    start: "11:15",
    durationMin: 90,
    lat: 22.7177,
    lng: 75.8545,
    openFrom: "10:00",
    openTo: "18:00",
  },
  {
    id: "sarafa",
    kind: "meal",
    title: "Sarafa Bazaar night market",
    city: DESTINATION,
    day: 1,
    start: "19:30",
    durationMin: 120,
    lat: 22.7172,
    lng: 75.8571,
    openFrom: "19:00",
    openTo: "01:00",
  },
  {
    id: "lalbagh",
    kind: "attraction",
    title: "Lal Bagh Palace",
    city: DESTINATION,
    day: 2,
    start: "09:30",
    durationMin: 105,
    lat: 22.701,
    lng: 75.842,
    openFrom: "09:00",
    openTo: "17:00",
  },
  {
    id: "chhappan",
    kind: "meal",
    title: "56 Dukan",
    city: DESTINATION,
    day: 2,
    start: "12:30",
    durationMin: 75,
    lat: 22.7247,
    lng: 75.8895,
    openFrom: "08:00",
    openTo: "23:00",
  },
  {
    id: "kanch",
    kind: "attraction",
    title: "Kanch Mandir",
    city: DESTINATION,
    day: 2,
    start: "15:30",
    durationMin: 60,
    lat: 22.7185,
    lng: 75.8598,
    openFrom: "10:00",
    openTo: "17:00",
  },
  {
    id: "annapurna",
    kind: "attraction",
    title: "Annapurna Temple",
    city: DESTINATION,
    day: 2,
    start: "17:00",
    durationMin: 60,
    lat: 22.6944,
    lng: 75.8452,
    openFrom: "06:00",
    openTo: "20:00",
  },
  {
    id: "mandu-out",
    kind: "transfer",
    title: "Drive to Mandu",
    city: DESTINATION,
    day: 3,
    start: "07:30",
    durationMin: 120,
    lat: 22.37,
    lng: 75.4,
  },
  {
    id: "jahaz",
    kind: "attraction",
    title: "Jahaz Mahal, Mandu",
    city: DESTINATION,
    day: 3,
    start: "09:45",
    durationMin: 150,
    lat: 22.3555,
    lng: 75.3939,
    openFrom: "08:00",
    openTo: "18:00",
  },
  {
    id: "roopmati",
    kind: "attraction",
    title: "Rani Roopmati Pavilion",
    city: DESTINATION,
    day: 3,
    start: "13:15",
    durationMin: 105,
    lat: 22.3269,
    lng: 75.3944,
    openFrom: "08:00",
    openTo: "18:00",
  },
  {
    id: "mandu-back",
    kind: "transfer",
    title: "Drive back to Indore",
    city: DESTINATION,
    day: 3,
    start: "17:00",
    durationMin: 120,
    lat: 22.7196,
    lng: 75.8577,
  },
  {
    id: "khajrana",
    kind: "attraction",
    title: "Khajrana Ganesh Temple",
    city: DESTINATION,
    day: 4,
    start: "09:00",
    durationMin: 75,
    lat: 22.742,
    lng: 75.9,
    openFrom: "05:00",
    openTo: "22:00",
  },
  {
    id: "museum",
    kind: "attraction",
    title: "Central Museum",
    city: DESTINATION,
    day: 4,
    start: "15:00",
    durationMin: 90,
    lat: 22.7226,
    lng: 75.8746,
    openFrom: "10:00",
    openTo: "17:00",
  },
  {
    id: "stay-out",
    kind: "stay",
    title: "Check out · Sayaji Indore",
    city: DESTINATION,
    day: 5,
    start: "11:00",
    durationMin: 30,
    lat: 22.7533,
    lng: 75.8937,
    locked: true,
    role: "check-out",
    booked: true,
    ref: "Booking 4471-9922",
  },
  {
    id: "flight-back",
    kind: "flight",
    title: "6E-6358 Indore → Bengaluru",
    city: HOME,
    fromCity: DESTINATION,
    toCity: HOME,
    day: 5,
    start: "15:40",
    durationMin: 115,
    lat: 13.1986,
    lng: 77.7066,
    locked: true,
    role: "departure",
    booked: true,
    ref: "PNR RTQ4XZ",
    note: "Lands Bengaluru 17:35",
  },
];

export const patalpani: Candidate = {
  id: "patalpani",
  title: "Patalpani Waterfall",
  city: DESTINATION,
  lat: 22.5301,
  lng: 75.7203,
  durationMin: 120,
  openFrom: "08:00",
  openTo: "18:00",
  rating: 4.4,
  note: "35 km south-west of Indore, closes at dusk, no lighting on the trail.",
};

/** The 3★ stay the owner asked to switch to. */
export const shreemaya = {
  title: "Shreemaya Celebration (3★)",
  lat: 22.7196,
  lng: 75.8712,
  ref: "Booking 5518-2043",
  note: "₹3,900 per night · 4 nights",
  checkIn: "13:00",
};

/** Owner-declared rules, shown live in Option C. */
export const declaredRules = [
  { id: "pace", label: "At most 4 stops in a day", detail: "Pace preference, soft" },
  { id: "start", label: "Nothing starts before 08:30", detail: "Except a booked flight, soft" },
  { id: "buffer", label: "At least 120 minutes free before a flight", detail: "Hard" },
  { id: "stay", label: "Every night away has a stay", detail: "Hard" },
  { id: "budget", label: "Stay under ₹95,000 for the trip", detail: "Currently ₹78,600" },
];
