// One realistic Lisbon trip shared by the Itinerary and Map canvas Labs, so both
// experiments argue over presentation of identical facts rather than nicer data.

export type StopKind =
  | "hotel"
  | "attraction"
  | "meal"
  | "transport"
  | "flight"
  | "airport";

export interface TravelLeg {
  mode: string;
  distance: string;
  duration: string;
  detail?: string;
  arrival?: string;
  buffer?: string;
  conflict?: string;
}

export interface Stop {
  id: string;
  marker?: string;
  kind: StopKind;
  name: string;
  timing: string;
  time?: string;
  estimated?: boolean;
  durationLabel?: string;
  leaveLabel?: string;
  operational?: string;
  travel?: TravelLeg;
  planned?: boolean;
  bookable?: boolean;
  booked?: boolean;
  cost?: string;
  rating?: number;
  reviews?: number;
  score?: number;
  note?: string;
  insight?: string;
  concern?: string;
  x: number;
  y: number;
}

export interface Weather {
  condition: "sun" | "cloud" | "rain";
  summary: string;
  high: number;
  low: number;
  precip: number;
}

export interface Day {
  day: number;
  date: string;
  weekday: string;
  title: string;
  color: string;
  summary: string;
  weather: Weather;
  schedule: { duration: string; start: string; end: string; estimated: boolean };
  route: { duration: string; distance: string; mode: string };
  rhythm: string;
  routeUrl: string;
  stops: Stop[];
}

export const dayColors = ["#e11d48", "#0f766e", "#b45309", "#6d28d9", "#0369a1"];

export const days: Day[] = [
  {
    day: 1,
    date: "8 Oct 2026",
    weekday: "Thursday",
    title: "Land, drop bags, walk Alfama",
    color: dayColors[0],
    summary:
      "A deliberately short first day. Everything is within ten minutes of the hotel so a delayed flight costs nothing.",
    weather: { condition: "sun", summary: "Clear", high: 24, low: 17, precip: 5 },
    schedule: { duration: "7 hr 40 min", start: "13:05", end: "20:45", estimated: true },
    route: { duration: "38 min", distance: "9.4 km", mode: "mixed" },
    rhythm: "One transfer from the airport, then everything on foot.",
    routeUrl: "https://maps.google.com/",
    stops: [
      {
        id: "d1-airport",
        kind: "airport",
        name: "Humberto Delgado Airport",
        timing: "Land",
        time: "13:05",
        durationLabel: "2 hr 45 min flight",
        x: 74,
        y: 22,
      },
      {
        id: "d1-hotel",
        marker: "H",
        kind: "hotel",
        name: "Memmo Alfama",
        timing: "Check in",
        time: "14:20",
        travel: { mode: "taxi", distance: "8.1 km", duration: "26 min", arrival: "14:14", buffer: "6 min" },
        bookable: true,
        booked: true,
        cost: "€980 · 5 nights",
        rating: 4.6,
        reviews: 2100,
        x: 52,
        y: 47,
      },
      {
        id: "d1-miradouro",
        marker: "1",
        kind: "attraction",
        name: "Miradouro das Portas do Sol",
        timing: "Arrive",
        time: "16:30",
        durationLabel: "50 min visit",
        travel: { mode: "walk", distance: "0.4 km", duration: "6 min", arrival: "16:24", buffer: "6 min" },
        planned: true,
        bookable: true,
        booked: false,
        cost: "Free",
        operational: "Open all day",
        rating: 4.7,
        reviews: 18400,
        score: 86,
        insight: "Best light is the hour before sunset, which is 18:52 on this date.",
        x: 48,
        y: 43,
      },
      {
        id: "d1-dinner",
        marker: "2",
        kind: "meal",
        name: "Taberna Sal Grosso",
        timing: "Arrive",
        time: "19:30",
        durationLabel: "1 hr 15 min",
        travel: { mode: "walk", distance: "0.9 km", duration: "12 min", arrival: "19:22", buffer: "8 min" },
        planned: true,
        bookable: true,
        booked: true,
        cost: "€54",
        operational: "18:30 – 23:00",
        rating: 4.6,
        reviews: 3900,
        note: "Confirmed for 19:30 under Marta. They hold the table 15 minutes.",
        x: 55,
        y: 52,
      },
      {
        id: "d1-return",
        marker: "H",
        kind: "hotel",
        name: "Memmo Alfama",
        timing: "Return",
        time: "20:45",
        estimated: true,
        travel: { mode: "walk", distance: "0.9 km", duration: "11 min" },
        x: 52,
        y: 47,
      },
    ],
  },
  {
    day: 2,
    date: "9 Oct 2026",
    weekday: "Friday",
    title: "Tram 28 and the Baixa grid",
    color: dayColors[1],
    summary:
      "One museum, one long tram ride, and a late-afternoon gap held open on purpose for Ana's nap.",
    weather: { condition: "cloud", summary: "Partly cloudy", high: 22, low: 16, precip: 20 },
    schedule: { duration: "10 hr 20 min", start: "09:30", end: "19:50", estimated: false },
    route: { duration: "1 hr 4 min", distance: "12.8 km", mode: "tram and walking" },
    rhythm: "Two tram legs, both under 25 minutes, with a two-hour rest built in.",
    routeUrl: "https://maps.google.com/",
    stops: [
      {
        id: "d2-hotel",
        marker: "H",
        kind: "hotel",
        name: "Memmo Alfama",
        timing: "Depart",
        time: "09:30",
        x: 52,
        y: 47,
      },
      {
        id: "d2-tram",
        marker: "1",
        kind: "attraction",
        name: "Tram 28 from Graça",
        timing: "Arrive",
        time: "09:50",
        durationLabel: "45 min ride",
        travel: { mode: "walk", distance: "0.7 km", duration: "9 min", arrival: "09:41", buffer: "9 min" },
        planned: true,
        bookable: true,
        booked: true,
        cost: "€6",
        operational: "05:40 – 22:15",
        rating: 4.4,
        reviews: 24100,
        score: 90,
        insight: "Boarding at Graça instead of Martim Moniz usually means a seat.",
        x: 45,
        y: 38,
      },
      {
        id: "d2-museum",
        marker: "2",
        kind: "attraction",
        name: "MAAT",
        timing: "Arrive",
        time: "11:30",
        durationLabel: "1 hr 40 min visit",
        travel: { mode: "tram", distance: "6.1 km", duration: "24 min", arrival: "11:19", buffer: "11 min" },
        planned: true,
        bookable: true,
        booked: false,
        cost: "€11",
        operational: "11:00 – 19:00",
        rating: 4.5,
        reviews: 12600,
        score: 84,
        concern: "Closed on Tuesdays — this is the only day it fits.",
        x: 22,
        y: 62,
      },
      {
        id: "d2-lunch",
        marker: "3",
        kind: "meal",
        name: "Time Out Market",
        timing: "Arrive",
        time: "13:40",
        durationLabel: "1 hr 10 min",
        travel: { mode: "tram", distance: "4.2 km", duration: "18 min", arrival: "13:33", buffer: "7 min" },
        planned: true,
        bookable: true,
        booked: false,
        cost: "€38",
        operational: "10:00 – 24:00",
        rating: 4.4,
        reviews: 55200,
        note: "Busiest 13:00–14:00; the Cais do Sodré end has the shorter queues.",
        x: 38,
        y: 58,
      },
      {
        id: "d2-return",
        marker: "H",
        kind: "hotel",
        name: "Memmo Alfama",
        timing: "Return",
        time: "19:50",
        estimated: true,
        travel: { mode: "walk", distance: "1.8 km", duration: "22 min" },
        x: 52,
        y: 47,
      },
    ],
  },
  {
    day: 3,
    date: "10 Oct 2026",
    weekday: "Saturday",
    title: "Belém, then the river back",
    color: dayColors[2],
    summary:
      "The heaviest day of the trip: two monuments, a ferry crossing, and the one dinner that is already confirmed.",
    weather: { condition: "sun", summary: "Sunny", high: 26, low: 18, precip: 10 },
    schedule: { duration: "12 hr 5 min", start: "09:15", end: "21:20", estimated: true },
    route: { duration: "1 hr 22 min", distance: "18.4 km", mode: "tram, ferry and walking" },
    rhythm: "Two tram legs and one ferry; no single transfer is over 35 minutes.",
    routeUrl: "https://maps.google.com/",
    stops: [
      {
        id: "d3-hotel",
        marker: "H",
        kind: "hotel",
        name: "Memmo Alfama",
        timing: "Depart",
        time: "09:15",
        x: 52,
        y: 47,
      },
      {
        id: "d3-monastery",
        marker: "1",
        kind: "attraction",
        name: "Jerónimos Monastery",
        timing: "Arrive",
        time: "10:00",
        durationLabel: "1 hr 30 min visit",
        travel: {
          mode: "tram",
          distance: "6.2 km",
          duration: "25 min",
          detail: "Tram 15E from Praça da Figueira",
          arrival: "09:52",
          buffer: "8 min",
        },
        planned: true,
        bookable: true,
        booked: true,
        cost: "€12",
        operational: "10:00 – 17:30",
        rating: 4.7,
        reviews: 61300,
        score: 92,
        insight: "The cloister queue is shortest before 10:30 and worst after 12:00.",
        x: 16,
        y: 66,
      },
      {
        id: "d3-pasteis",
        marker: "2",
        kind: "meal",
        name: "Pastéis de Belém",
        timing: "Arrive",
        time: "11:45",
        durationLabel: "45 min",
        travel: { mode: "walk", distance: "0.6 km", duration: "8 min", arrival: "11:38", buffer: "7 min" },
        planned: true,
        bookable: true,
        booked: false,
        cost: "€9",
        operational: "08:00 – 23:00",
        rating: 4.5,
        reviews: 42800,
        note: "Ana's nap window starts at 13:00, so this has to stay before it.",
        x: 18,
        y: 68,
      },
      {
        id: "d3-tower",
        marker: "3",
        kind: "attraction",
        name: "Belém Tower",
        timing: "Arrive",
        time: "13:00",
        estimated: true,
        durationLabel: "1 hr visit",
        travel: {
          mode: "walk",
          distance: "1.1 km",
          duration: "14 min",
          arrival: "12:44",
          conflict: "16 min",
        },
        planned: true,
        bookable: true,
        booked: false,
        cost: "€8",
        operational: "09:30 – 18:00",
        rating: 4.5,
        reviews: 38200,
        score: 88,
        concern: "Only 16 minutes spare before the 14:10 ferry. Consider the exterior only.",
        x: 12,
        y: 72,
      },
      {
        id: "d3-ferry",
        kind: "transport",
        name: "Ferry: Belém to Cais do Sodré",
        timing: "Depart from Belém",
        time: "14:10",
        durationLabel: "35 min transfer",
        leaveLabel: "Ends 14:45",
        travel: { mode: "walk", distance: "0.5 km", duration: "7 min" },
        x: 30,
        y: 74,
      },
      {
        id: "d3-market",
        marker: "4",
        kind: "attraction",
        name: "LX Factory",
        timing: "Arrive",
        time: "15:30",
        durationLabel: "1 hr 15 min visit",
        travel: { mode: "walk", distance: "1.3 km", duration: "17 min", arrival: "15:12", buffer: "18 min" },
        planned: true,
        bookable: true,
        booked: false,
        cost: "€25",
        operational: "10:00 – 20:00",
        rating: 4.4,
        reviews: 29700,
        score: 79,
        x: 33,
        y: 63,
      },
      {
        id: "d3-dinner",
        marker: "5",
        kind: "meal",
        name: "Cervejaria Ramiro",
        timing: "Arrive",
        time: "19:30",
        durationLabel: "1 hr 30 min",
        travel: { mode: "tram", distance: "5.4 km", duration: "21 min", arrival: "19:18", buffer: "12 min" },
        planned: true,
        bookable: true,
        booked: true,
        cost: "€72",
        operational: "12:00 – 24:00",
        rating: 4.6,
        reviews: 29400,
        note: "Confirmed 19:30. Walk-ins were quoted a 50 minute wait last Saturday.",
        x: 58,
        y: 34,
      },
      {
        id: "d3-return",
        marker: "H",
        kind: "hotel",
        name: "Memmo Alfama",
        timing: "Return",
        time: "21:20",
        estimated: true,
        travel: { mode: "walk", distance: "1.4 km", duration: "18 min" },
        x: 52,
        y: 47,
      },
    ],
  },
  {
    day: 4,
    date: "11 Oct 2026",
    weekday: "Sunday",
    title: "Sintra, one castle only",
    color: dayColors[3],
    summary:
      "A deliberate single-target day. One palace, an early train, and nothing scheduled after 17:00.",
    weather: { condition: "rain", summary: "Showers", high: 19, low: 14, precip: 65 },
    schedule: { duration: "9 hr 15 min", start: "08:40", end: "17:55", estimated: true },
    route: { duration: "2 hr 6 min", distance: "62.0 km", mode: "rail and bus" },
    rhythm: "One 40 minute train each way; the rest is a short shuttle bus.",
    routeUrl: "https://maps.google.com/",
    stops: [
      {
        id: "d4-hotel",
        marker: "H",
        kind: "hotel",
        name: "Memmo Alfama",
        timing: "Depart",
        time: "08:40",
        x: 52,
        y: 47,
      },
      {
        id: "d4-train",
        kind: "transport",
        name: "Train: Rossio to Sintra",
        timing: "Depart from Rossio",
        time: "09:11",
        durationLabel: "40 min transfer",
        leaveLabel: "Ends 09:51",
        travel: { mode: "walk", distance: "1.2 km", duration: "16 min", arrival: "08:56", buffer: "15 min" },
        x: 44,
        y: 30,
      },
      {
        id: "d4-pena",
        marker: "1",
        kind: "attraction",
        name: "Pena Palace",
        timing: "Arrive",
        time: "10:30",
        durationLabel: "2 hr 30 min visit",
        travel: { mode: "bus", distance: "4.6 km", duration: "22 min", arrival: "10:18", buffer: "12 min" },
        planned: true,
        bookable: true,
        booked: true,
        cost: "€28",
        operational: "09:30 – 18:30",
        rating: 4.6,
        reviews: 78900,
        score: 94,
        insight: "Timed entry is booked for 10:30; late arrivals are refused, not rescheduled.",
        concern: "65% chance of showers — the terraces are exposed.",
        x: 8,
        y: 18,
      },
      {
        id: "d4-lunch",
        marker: "2",
        kind: "meal",
        name: "Tascantiga",
        timing: "Arrive",
        time: "13:40",
        durationLabel: "1 hr",
        travel: { mode: "bus", distance: "3.9 km", duration: "19 min", arrival: "13:31", buffer: "9 min" },
        planned: true,
        bookable: true,
        booked: false,
        cost: "€44",
        operational: "12:00 – 22:00",
        rating: 4.5,
        reviews: 5600,
        x: 12,
        y: 24,
      },
      {
        id: "d4-return",
        marker: "H",
        kind: "hotel",
        name: "Memmo Alfama",
        timing: "Return",
        time: "17:55",
        estimated: true,
        travel: { mode: "rail", distance: "28.4 km", duration: "52 min" },
        x: 52,
        y: 47,
      },
    ],
  },
];

export const trip = {
  destination: "Lisbon",
  origin: "London",
  dateRange: "8 Oct 2026 - 13 Oct 2026",
  travelers: 2,
  status: "planning",
  totalCost: "€3,480",
  summary:
    "A five-day Lisbon trip for 2 travelers with 14 planned places, built around slow mornings and one anchor sight a day.",
  counts: { days: 5, stays: 1, places: 14, flights: 2 },
  budget: {
    spent: "€3,480",
    target: "€4,200",
    perTraveler: "€1,740",
    remaining: "€720 left",
    pct: 83,
  },
  familyPills: ["Slow mornings", "Ana naps 13:00", "No queues over 20 min"],
  constraints: ["Transfers under 45 minutes", "One anchor sight a day", "Dinner before 20:00"],
  packing: "Light layers, one rainshell for Sunday, and shoes that survive the Alfama cobbles",
  weatherSource: "Open-Meteo · updated 2 hours ago",
};

export const bookingTotals = (() => {
  const all = days.flatMap((day) => day.stops);
  const bookable = all.filter((stop) => stop.bookable);
  return {
    stops: 14,
    booked: bookable.filter((stop) => stop.booked).length + 4,
  };
})();

export function dayTotals(day: Day) {
  const planned = day.stops.filter((stop) => stop.planned);
  const bookable = day.stops.filter((stop) => stop.bookable);
  return {
    planned: planned.length,
    confirmed: bookable.filter((stop) => stop.booked).length,
    toBook: bookable.filter((stop) => !stop.booked).length,
  };
}

export const dayThree = days[2];
