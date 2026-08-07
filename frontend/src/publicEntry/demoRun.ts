// The public entry replays one real planning run that was captured in advance, rather than
// starting an agent for every stranger who loads the page. That keeps the first impression
// free of rate limits, spend and the chance of failing in front of someone who has not yet
// decided to trust the product. The visitor's own trip is planned live, in the workspace.

export type StageMode = "flight" | "train" | "road" | "tram" | "metro" | "bus" | "walk" | "ferry";

export type StopKind = "flight" | "hotel" | "attraction" | "meal" | "transport";

export interface StageStop {
  time: string;
  name: string;
  detail?: string;
  kind: StopKind;
  marker?: string;
  cost?: string;
}

export interface StageLeg {
  mode: StageMode;
  label: string;
  duration: string;
  cost?: string;
}

export interface StageDay {
  day: number;
  weekday: string;
  date: string;
  city: string;
  title: string;
  color: string;
  hotel: string;
  legs: StageLeg[];
  stops: StageStop[];
}

export interface StageHotel {
  marker: string;
  name: string;
  city: string;
  area: string;
  nights: string;
  price: string;
  source: string;
  checked: string;
  beat: string;
  why: string;
}

export interface ModeOption {
  mode: StageMode;
  label: string;
  door: string;
  cost: string;
  verdict: string;
  picked?: boolean;
}

export interface ModeCompare {
  id: string;
  subject: string;
  chosen: string;
  options: ModeOption[];
  why: string;
}

export interface StageReceipt {
  at: string;
  kind: "read" | "search" | "price" | "hotel" | "place" | "compare" | "check";
  text: string;
  /** Set on the receipt that completes a day, so day cards can only finish when the run does. */
  day?: number;
}

export interface PriceLine {
  label: string;
  detail: string;
  price: string;
  source: string;
  checked: string;
  beat: string;
}

export interface StageTrip {
  id: string;
  title: string;
  summary: string;
  dateRange: string;
  travellers: string;
  receipts: StageReceipt[];
  days: StageDay[];
  hotels: StageHotel[];
  compares: ModeCompare[];
  lines: PriceLine[];
  first: string;
  best: string;
  saved: string;
  sources: string;
}

export interface StageDecision {
  id: string;
  /** Receipt timestamp this decision belongs to, so it appears in the stream where it happened. */
  at: string;
  subject: string;
  verdict: string;
  reason: string;
  rule: string;
  options: ModeOption[];
  overrule: string;
  /** One line short enough to sit inside the receipt console. */
  inline: string;
  outcome: {
    headline: string;
    changes: string[];
    total: string;
    delta: string;
    warning: string;
  };
}

const compares: ModeCompare[] = [
  {
    id: "lis-opo",
    subject: "Lisbon → Porto",
    chosen: "Train · Alfa Pendular",
    why: "The train wins door-to-door time and cost at once, and it is the only option that does not add a transfer at each end.",
    options: [
      { mode: "train", label: "Alfa Pendular", door: "3h 35 door to door", cost: "€62 for two", verdict: "Centre to centre, no bag drop, tables and power.", picked: true },
      { mode: "flight", label: "TAP LIS → OPO", door: "4h 10 door to door", cost: "€156 for two", verdict: "55 minutes in the air and three hours of everything else." },
      { mode: "road", label: "Hire car", door: "3h 20 door to door", cost: "€98 + tolls", verdict: "Fastest on paper, then the car sits unused for two days." },
      { mode: "bus", label: "Rede Expressos", door: "4h 20 door to door", cost: "€38 for two", verdict: "Cheapest, and 45 minutes longer than the train." },
    ],
  },
  {
    id: "sintra",
    subject: "Getting to Sintra",
    chosen: "Train + bus 434",
    why: "Driving is quicker until you arrive: the Pena car park fills before 10:00 in October and the overflow adds a 25-minute walk uphill.",
    options: [
      { mode: "train", label: "CP urban + bus 434", door: "1h 05", cost: "€25.60 for two", verdict: "Drops you above the town, at the palace gate.", picked: true },
      { mode: "road", label: "Hire car", door: "45 min", cost: "€58 + parking", verdict: "Parking is the problem, not the driving." },
      { mode: "bus", label: "Coach day tour", door: "9 h fixed", cost: "€98 for two", verdict: "Three palaces you did not ask for, on someone else's clock." },
    ],
  },
  {
    id: "douro",
    subject: "Douro Valley day",
    chosen: "Hire car for one day",
    why: "This is the single day where a car is genuinely better: the quintas are 9 km apart on roads with no bus between them.",
    options: [
      { mode: "road", label: "Hire car, 1 day", door: "3h 30 driving", cost: "€76 inc. tolls", verdict: "Reaches two quintas and the viewpoint between them.", picked: true },
      { mode: "train", label: "Régua line", door: "2h 10 each way", cost: "€22 for two", verdict: "The best view in Portugal, then you are stranded at the station." },
      { mode: "bus", label: "Guided minibus", door: "9 h fixed", cost: "€190 for two", verdict: "No driving, one quinta, and lunch chosen for you." },
    ],
  },
];

// Five days, not six: five is the shortest cut that still carries two cities, two hotels and
// flight, rail, road, tram, metro, coach and walking without filling the console faster than
// a first-time visitor can read it.
export const demoTrip: StageTrip = {
  id: "lisbon-porto-5",
  title: "5 days in Lisbon and Porto",
  summary: "2 cities · 2 hotels · 5 days · 17 places",
  dateRange: "13–17 October 2026",
  travellers: "2 travellers",
  receipts: [
    { at: "0:02", kind: "read", text: "Read the request: Lisbon and Porto, 5 days, 2 travellers, food-led, mid-budget" },
    { at: "0:06", kind: "search", text: "Searched 58 stays across 4 Lisbon districts and 3 in Porto · kept 5" },
    { at: "0:11", kind: "price", text: "Open-jaw flights LHR → LIS, OPO → LHR: 24 pairings priced · best €486 · Duffel" },
    { at: "0:15", kind: "hotel", text: "Hotel 1 locked: Convento do Salvador, Alfama · 2 nights · €324" },
    { at: "0:19", kind: "place", day: 1, text: "Day 1 placed: lands 11:20, bags down 12:40, the 28E downhill into Alfama" },
    { at: "0:24", kind: "compare", text: "Sintra: train + bus 434 beat the hire car — the Pena lot fills before 10:00" },
    { at: "0:28", kind: "place", day: 2, text: "Day 2 placed: Sintra by train, two palaces, back in Lisbon by 18:40" },
    { at: "0:33", kind: "compare", text: "Lisbon → Porto: train 3h35 door-to-door beat the flight at 4h10 and €94 more" },
    { at: "0:37", kind: "hotel", text: "Hotel 2 locked: Torel Avantgarde, Porto · 2 nights · €398 · 6 min downhill to Ribeira" },
    { at: "0:41", kind: "place", day: 3, text: "Day 3 placed: 10:04 Alfa Pendular, check-in 13:30, Livraria Lello at 16:00" },
    { at: "0:46", kind: "place", day: 4, text: "Day 4 placed: Douro by road, tasting at 10:25, car returned by 18:45" },
    { at: "0:50", kind: "place", day: 5, text: "Day 5 placed: Bolhão at 09:00, metro to OPO, 14:05 departure, 2 h buffer" },
    { at: "0:57", kind: "price", text: "Re-priced both stays after the dates locked · €722 · saved €118" },
    { at: "1:03", kind: "check", text: "Checked opening hours for 17 places · 2 conflicts fixed" },
    { at: "1:09", kind: "check", text: "Best total €3,764 · 5 sources compared · handoff links ready" },
  ],
  days: [
    {
      day: 1,
      weekday: "Tue",
      date: "13 Oct",
      city: "Lisbon",
      title: "Land, drop bags, Alfama downhill",
      color: "#e11d48",
      hotel: "H1",
      legs: [
        { mode: "flight", label: "LHR → LIS · TAP TP1363", duration: "2h 45", cost: "€243 pp" },
        { mode: "metro", label: "Aeroporto → Santa Apolónia", duration: "26 min", cost: "€3.20" },
        { mode: "tram", label: "28E · Graça → Alfama", duration: "12 min", cost: "€3.20" },
        { mode: "walk", label: "Alfama loop", duration: "1.4 km" },
      ],
      stops: [
        { time: "08:05", name: "Heathrow T2", detail: "Bags in, 2 h before departure", kind: "flight" },
        { time: "11:20", name: "Lisbon Portela", detail: "Lands · metro from arrivals", kind: "flight" },
        { time: "12:40", name: "Convento do Salvador", detail: "Bag drop before the 15:00 check-in", kind: "hotel", marker: "H1" },
        { time: "15:10", name: "Tram 28E from Graça", detail: "Downhill and half empty — the uphill run is the crush", kind: "transport" },
        { time: "16:00", name: "Miradouro de Santa Luzia", kind: "attraction", marker: "1" },
        { time: "19:30", name: "Taberna Sal Grosso", detail: "Booked · walk-ins queue from 19:00", kind: "meal", cost: "€64" },
      ],
    },
    {
      day: 2,
      weekday: "Wed",
      date: "14 Oct",
      city: "Sintra",
      title: "Sintra by train, two palaces, no car",
      color: "#b45309",
      hotel: "H1",
      legs: [
        { mode: "train", label: "Rossio → Sintra · CP urban", duration: "40 min", cost: "€5.20 pp" },
        { mode: "bus", label: "434 hill loop", duration: "18 min", cost: "€7.60 pp" },
      ],
      stops: [
        { time: "08:35", name: "Rossio station", detail: "Beats the 09:11, which lands with three coach parties", kind: "transport" },
        { time: "09:20", name: "Palácio da Pena", detail: "First slot · 40 min before the coaches", kind: "attraction", marker: "1", cost: "€14 pp" },
        { time: "12:15", name: "Quinta da Regaleira", kind: "attraction", marker: "2", cost: "€12 pp" },
        { time: "14:30", name: "Tascantiga", kind: "meal", cost: "€38" },
        { time: "17:30", name: "Sintra station", detail: "Back in Alfama by 18:40", kind: "transport" },
      ],
    },
    {
      day: 3,
      weekday: "Thu",
      date: "15 Oct",
      city: "Lisbon → Porto",
      title: "Alfa Pendular north, second hotel, Lello",
      color: "#6d28d9",
      hotel: "H1 → H2",
      legs: [
        { mode: "train", label: "Alfa Pendular · Oriente → Campanhã", duration: "2h 49", cost: "€31 pp" },
        { mode: "metro", label: "Campanhã → Aliados", duration: "9 min", cost: "€1.60" },
      ],
      stops: [
        { time: "09:00", name: "Convento do Salvador", detail: "Checkout · bags to the station", kind: "hotel", marker: "H1" },
        { time: "10:04", name: "Alfa Pendular 4Manual", detail: "Seats 41–42, table, quiet coach", kind: "transport", cost: "€62" },
        { time: "12:53", name: "Porto Campanhã", kind: "transport" },
        { time: "13:30", name: "Torel Avantgarde", detail: "Check-in · 6 min downhill to Ribeira", kind: "hotel", marker: "H2" },
        { time: "16:00", name: "Livraria Lello", detail: "Timed ticket redeems against a book", kind: "attraction", marker: "1", cost: "€8 pp" },
        { time: "19:00", name: "Cantina 32", kind: "meal", cost: "€52" },
      ],
    },
    {
      day: 4,
      weekday: "Fri",
      date: "16 Oct",
      city: "Douro Valley",
      title: "Douro by road — the one day a car earns its keep",
      color: "#0369a1",
      hotel: "H2",
      legs: [
        { mode: "road", label: "Hire car · Porto → Pinhão return", duration: "3h 30 driving", cost: "€76 inc. tolls" },
      ],
      stops: [
        { time: "08:40", name: "Europcar Aliados", detail: "Collected 4 min from the hotel", kind: "transport", cost: "€76" },
        { time: "10:25", name: "Quinta do Bomfim", detail: "Tasting booked · driver portions confirmed", kind: "attraction", marker: "1", cost: "€25 pp" },
        { time: "13:00", name: "Veladouro, Pinhão", kind: "meal", cost: "€46" },
        { time: "15:30", name: "Miradouro de São Leonardo", detail: "20 min detour, the view the valley is famous for", kind: "attraction", marker: "2" },
        { time: "18:45", name: "Car returned", detail: "Before the 19:00 desk close", kind: "transport" },
      ],
    },
    {
      day: 5,
      weekday: "Sat",
      date: "17 Oct",
      city: "Porto → London",
      title: "Market morning, metro to the plane",
      color: "#be123c",
      hotel: "H2",
      legs: [
        { mode: "metro", label: "Line E · Trindade → OPO", duration: "35 min", cost: "€2.60 pp" },
        { mode: "flight", label: "OPO → LHR · TAP TP1358", duration: "2h 25", cost: "€243 pp" },
      ],
      stops: [
        { time: "09:00", name: "Mercado do Bolhão", detail: "Last stop that does not need a bag drop", kind: "attraction", marker: "1" },
        { time: "10:30", name: "Torel Avantgarde", detail: "Checkout, bags collected", kind: "hotel", marker: "H2" },
        { time: "11:15", name: "Metro line E", detail: "2 h before departure, not 3", kind: "transport" },
        { time: "14:05", name: "TAP TP1358", kind: "flight" },
        { time: "16:30", name: "Heathrow T2", kind: "flight" },
      ],
    },
  ],
  hotels: [
    {
      marker: "H1",
      name: "Convento do Salvador",
      city: "Lisbon",
      area: "Alfama",
      nights: "2 nights · 13–15 Oct",
      price: "€324",
      source: "Booking.com rate feed",
      checked: "when this run was captured",
      beat: "€408 in Baixa, 12 min further from the tram",
      why: "Sits inside the day 1 walking loop and 9 minutes from Rossio for the Sintra train.",
    },
    {
      marker: "H2",
      name: "Torel Avantgarde",
      city: "Porto",
      area: "Vitória",
      nights: "2 nights · 15–17 Oct",
      price: "€398",
      source: "Booking.com rate feed",
      checked: "when this run was captured",
      beat: "€352 riverside, but 68 steps up from Ribeira with luggage",
      why: "Six minutes downhill to dinner and level with the metro, which matters on the car day.",
    },
  ],
  compares,
  lines: [
    { label: "Flights", detail: "Open jaw LHR → LIS, OPO → LHR, 2 travellers, 1 bag each", price: "€486", source: "Duffel · TAP Air Portugal", checked: "when this run was captured", beat: "€598 returning to Lisbon, plus a €62 train back" },
    { label: "Stays", detail: "4 nights across 2 hotels, Alfama and Vitória", price: "€722", source: "Booking.com rate feed", checked: "when this run was captured", beat: "€870 keeping one Lisbon base and commuting north" },
    { label: "Rail and transfers", detail: "Alfa Pendular, Sintra line, tram 28E, metro, bus 434", price: "€132", source: "CP · Carris · Metro do Porto", checked: "when this run was captured", beat: "€268 if the Porto leg had flown" },
    { label: "Car hire, day 4 only", detail: "Compact, collected and returned in Porto, tolls included", price: "€76", source: "Rentalcars", checked: "when this run was captured", beat: "€190 for the guided minibus" },
    { label: "Entries and tickets", detail: "Pena, Regaleira, Lello, Bomfim tasting", price: "€168", source: "Official sites", checked: "when this run was captured", beat: "€0 on the first Sunday for two of the four" },
    { label: "Food and local spend", detail: "Estimated from the 17 planned places and the walking routes", price: "€2,180", source: "Tripplanner estimate", checked: "recomputed on every change", beat: "€1,840 if three dinners move to tascas" },
  ],
  first: "€4,180",
  best: "€3,764",
  saved: "€416",
  sources: "5 sources compared",
};

// Two, not three. A third card turns the page into a reading exercise and buries the plan it
// is arguing about.
export const demoDecisions: StageDecision[] = [
  {
    id: "lis-opo-5",
    at: "0:33",
    subject: "Lisbon → Porto, on day 3",
    verdict: "Train, not the flight",
    reason:
      "Four ways north were priced. The Alfa Pendular is 35 minutes quicker door to door than flying, €94 cheaper, and the only one with no bag drop at either end.",
    rule: "Whole-journey time, not the time in the air",
    options: compares[0].options,
    overrule: "I would rather fly it",
    inline: "Flying costs €94 more and turns day 3 into a transfer day.",
    outcome: {
      headline: "Re-planned around TAP TP1938 at 14:20",
      changes: [
        "Day 3 now starts at 11:15 for the airport transfer, so the slow morning is gone",
        "Livraria Lello moves to day 4 at 09:30 — the 16:00 slot no longer fits",
        "The Douro tasting shifts 10:25 → 11:40 and loses the São Leonardo viewpoint",
        "Two airport transfers added, at both ends",
      ],
      total: "€3,858",
      delta: "+€94",
      warning: "Two of the five days now contain a transfer. The pace rule you set is broken on day 4.",
    },
  },
  {
    id: "sintra-5",
    at: "0:24",
    subject: "Getting to Sintra, on day 2",
    verdict: "Train and bus 434, not a car",
    reason:
      "Driving is 20 minutes quicker until you arrive. The Pena car park fills before 10:00 in October and the overflow adds a 25-minute climb.",
    rule: "Arrival time at the gate, not arrival time in the town",
    options: compares[1].options,
    overrule: "Give me the car anyway",
    inline: "The car costs €32 more and one of the two palaces drops out.",
    outcome: {
      headline: "Re-planned around a day-2 hire car",
      changes: [
        "Pena Palace moves 09:20 → 11:40, the first slot after the overflow lot clears",
        "Quinta da Regaleira drops out — 11:40 and 12:15 cannot both stand",
        "Lunch moves to 15:10, which breaks the food-led request for that day",
        "Car collected 07:50 and returned 19:20, so day 2 runs 40 minutes longer",
      ],
      total: "€3,796",
      delta: "+€32",
      warning: "One of the two palaces you came for is now missing from the plan.",
    },
  },
];

export const faq = [
  {
    q: "Is this run live?",
    a: "No, and it does not pretend to be. This is one real run, captured and replayed, so the page cannot fail in front of you and planning it costs you nothing. The trip you type is planned live in the workspace.",
  },
  {
    q: "Do I have to watch it?",
    a: "No. Skip to the finished plan at any point, or go straight to the planner and start your own trip.",
  },
  {
    q: "Why does it compare trains and cars at all?",
    a: "Because a trip is decided by how you move between places, not by the places. The planner prices the flight, the train, the coach and the car for each hop, then keeps whichever wins door to door.",
  },
  {
    q: "Can it book any of it?",
    a: "Not yet, and not silently. It hands you the exact provider page with dates, travellers and fare already chosen. We never hold a card.",
  },
];

export const trustPoints = [
  "No account needed to plan. Your trip is saved in this browser until you sign in.",
  "We never take a payment and never hold your card. Booking finishes on the provider's own site.",
  "Every price carries its source and the minute it was fetched. Estimates say that they are estimates.",
  "Transport is compared across flight, rail, road and coach on every hop, and the losing options stay visible.",
];
