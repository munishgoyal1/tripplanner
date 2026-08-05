export type VariantId = "conversation-dock" | "focus-composer" | "turn-thread";

export interface Variant {
  id: VariantId;
  label: string;
  summary: string;
  delta: string;
}

export const variants: Variant[] = [
  {
    id: "conversation-dock",
    label: "A · Conversation dock",
    summary:
      "The Assistant becomes a permanent full-height left column beside Itinerary, Map, and Details. It never overlaps the plan and never has to be reopened.",
    delta:
      "The Assistant is a fourth resident column that permanently costs about 22rem of workspace width. Unlike B it is never dismissed, and unlike C it does not displace Details.",
  },
  {
    id: "focus-composer",
    label: "B · Focus composer",
    summary:
      "One full-width command line sits under the workspace with the last reply inline. The transcript rises into a centred reading sheet only when asked for.",
    delta:
      "The resting Assistant is a 4rem input strip with zero column cost, and the transcript is a temporary reading sheet over the workspace. Unlike A nothing is permanently reserved, and unlike C the conversation is never side by side with the map.",
  },
  {
    id: "turn-thread",
    label: "C · Turn thread",
    summary:
      "The Assistant takes the right rail as a thread of turn cards. Each card carries its own timing, tools, and the exact stops it changed. Details opens over the Map on demand.",
    delta:
      "Every turn is a card that links to the stops it changed, and Details loses its permanent rail to an on-demand overlay. Unlike A the conversation replaces a panel rather than adding one, and unlike B it stays visible while you work the map.",
  },
];

export interface TurnEffect {
  label: string;
  day: number;
  stopId?: string;
}

export interface Turn {
  id: string;
  group: "Two days ago" | "Yesterday" | "Earlier today" | "Just now";
  at: string;
  user: string;
  assistant: string;
  seconds: number;
  tools?: { name: string; seconds: number }[];
  effects?: TurnEffect[];
}

export interface Stop {
  id: string;
  time: string;
  timingLabel?: string;
  name: string;
  kind: "hotel" | "attraction" | "restaurant" | "station";
  meta: string;
  travel?: string;
  booked?: boolean;
  x: number;
  y: number;
  blurb: string;
  rating?: string;
  hours?: string;
}

export const trip = {
  title: "Madhya Pradesh heritage loop",
  dates: "12 - 17 Nov 2026",
  travellers: "2 travellers · unhurried pace",
  days: [
    { day: 1, label: "D1", title: "Delhi to Bhopal by rail" },
    { day: 2, label: "D2", title: "Old Bhopal and the lakes" },
    { day: 3, label: "D3", title: "Sanchi and Udayagiri" },
    { day: 4, label: "D4", title: "Bhimbetka and Bhojpur" },
    { day: 5, label: "D5", title: "Pachmarhi" },
    { day: 6, label: "D6", title: "Bhopal to Delhi" },
  ],
};

export const dayBrief = {
  headline: "08:15 - 17:10 · 4 planned stops · 96 km driving",
  rhythm: "One long morning at Sanchi, a slow lunch, then Udayagiri before the light goes.",
  readiness: "Car and driver confirmed · museum tickets still open",
};

export const stops: Stop[] = [
  {
    id: "hotel-out",
    time: "08:15",
    timingLabel: "Depart",
    name: "Jehan Numa Palace Hotel",
    kind: "hotel",
    meta: "Breakfast from 07:00 · car waits at the porch",
    booked: true,
    x: 78,
    y: 226,
    blurb: "Colonial-era palace stay in Shamla Hills, five minutes from Upper Lake.",
    rating: "4.6 · 3,914 reviews",
    hours: "Reception open 24 hours",
  },
  {
    id: "sanchi-stupa",
    time: "09:40",
    timingLabel: "Arrive",
    name: "Sanchi Stupa No. 1",
    kind: "attraction",
    meta: "2 h · UNESCO site · steep last approach",
    travel: "Drive 46 km · 1 h 10 m",
    x: 268,
    y: 74,
    blurb: "The Great Stupa, commissioned by Ashoka, with the four carved toranas intact.",
    rating: "4.7 · 12,180 reviews",
    hours: "Open 06:30 - 18:30 · ticket counter closes 18:00",
  },
  {
    id: "sanchi-museum",
    time: "11:50",
    timingLabel: "Arrive",
    name: "Sanchi Archaeological Museum",
    kind: "attraction",
    meta: "45 m · shaded · combined ticket accepted",
    travel: "Walk 700 m · 9 m",
    x: 244,
    y: 106,
    blurb: "Lion capital and recovered torana fragments, useful before or after the stupa climb.",
    rating: "4.3 · 1,207 reviews",
    hours: "Open 09:00 - 17:00 · closed Fridays",
  },
  {
    id: "gateway-lunch",
    time: "13:00",
    timingLabel: "Table",
    name: "Gateway Retreat Sanchi",
    kind: "restaurant",
    meta: "1 h · thali and continental · garden seating",
    travel: "Drive 2.1 km · 6 m",
    booked: true,
    x: 214,
    y: 132,
    blurb: "The only reliable sit-down lunch near the hill; call ahead on weekends.",
    rating: "4.1 · 862 reviews",
    hours: "Lunch 12:00 - 15:30",
  },
  {
    id: "udayagiri",
    time: "14:30",
    timingLabel: "Arrive",
    name: "Udayagiri Caves",
    kind: "attraction",
    meta: "1 h 30 m · rock-cut · little shade",
    travel: "Drive 13 km · 25 m",
    x: 158,
    y: 150,
    blurb: "Gupta-period cave shrines including the Varaha panel, best in late-afternoon light.",
    rating: "4.5 · 2,431 reviews",
    hours: "Open sunrise to sunset · no ticket counter after 17:30",
  },
  {
    id: "hotel-in",
    time: "17:10",
    timingLabel: "Return",
    name: "Jehan Numa Palace Hotel",
    kind: "hotel",
    meta: "Dinner held at 20:00 · same room",
    booked: true,
    x: 78,
    y: 226,
    blurb: "Colonial-era palace stay in Shamla Hills, five minutes from Upper Lake.",
    rating: "4.6 · 3,914 reviews",
    hours: "Reception open 24 hours",
  },
];

export const turns: Turn[] = [
  {
    id: "t1",
    group: "Two days ago",
    at: "Mon 21:04",
    user: "Six days in Madhya Pradesh in November, two of us, heritage over hill stations. Trains from Delhi, no early starts.",
    assistant:
      "Built a six-day loop out of Bhopal: rail in on the Vande Bharat, two heritage day trips, one hill day, rail back. Nothing starts before 08:00.",
    seconds: 41,
    tools: [
      { name: "search_trains", seconds: 9.2 },
      { name: "search_places", seconds: 12.8 },
      { name: "save_trip", seconds: 1.4 },
    ],
    effects: [
      { label: "Created 6 days", day: 1 },
      { label: "Bhopal base", day: 2 },
    ],
  },
  {
    id: "t2",
    group: "Two days ago",
    at: "Mon 21:19",
    user: "The Delhi train is fine but I do not want to arrive after dark on day one.",
    assistant:
      "Moved you to the 06:00 Vande Bharat, arriving Bhopal 14:00. Check-in now lands at 15:12 with the evening free for Upper Lake.",
    seconds: 17,
    tools: [{ name: "search_trains", seconds: 7.9 }],
    effects: [{ label: "Day 1 rail moved", day: 1 }],
  },
  {
    id: "t3",
    group: "Two days ago",
    at: "Mon 21:33",
    user: "Where are we sleeping?",
    assistant:
      "Jehan Numa Palace for all five nights, so no packing between day trips. It is the only heritage property with consistent service reports in the price band you use.",
    seconds: 12,
    effects: [{ label: "Hotel for 5 nights", day: 2, stopId: "hotel-out" }],
  },
  {
    id: "t4",
    group: "Yesterday",
    at: "Tue 09:41",
    user: "Day 3 feels thin. What else is near Sanchi?",
    assistant:
      "Added the Archaeological Museum next to the stupa and Udayagiri Caves 13 km west. That fills the afternoon without a second long drive.",
    seconds: 23,
    tools: [{ name: "search_places", seconds: 11.1 }],
    effects: [
      { label: "Added museum", day: 3, stopId: "sanchi-museum" },
      { label: "Added Udayagiri", day: 3, stopId: "udayagiri" },
    ],
  },
  {
    id: "t5",
    group: "Yesterday",
    at: "Tue 09:58",
    user: "Is there anywhere decent to eat out there?",
    assistant:
      "Gateway Retreat Sanchi is the only dependable sit-down option. Held a 13:00 table between the museum and Udayagiri.",
    seconds: 14,
    tools: [{ name: "search_restaurants", seconds: 6.3 }],
    effects: [{ label: "Lunch at 13:00", day: 3, stopId: "gateway-lunch" }],
  },
  {
    id: "t6",
    group: "Yesterday",
    at: "Tue 10:12",
    user: "How long is the drive back in the evening?",
    assistant: "Udayagiri to the hotel is 62 km, about 1 h 25 m. Leaving at 16:00 puts you back by 17:10, before the light goes.",
    seconds: 8,
    effects: [{ label: "Day 3 return time", day: 3, stopId: "hotel-in" }],
  },
  {
    id: "t7",
    group: "Yesterday",
    at: "Tue 18:26",
    user: "Book the car for day 3 and day 4.",
    assistant:
      "Both days are with the same driver, quoted 3,400 rupees per day including waiting. Confirmation and the driver's number are on the day cards.",
    seconds: 29,
    tools: [{ name: "search_transport", seconds: 13.7 }],
    effects: [
      { label: "Car confirmed", day: 3 },
      { label: "Car confirmed", day: 4 },
    ],
  },
  {
    id: "t8",
    group: "Yesterday",
    at: "Tue 18:44",
    user: "What did we decide about Pachmarhi again?",
    assistant:
      "Day 5 stays a single long day trip rather than an overnight, because you asked to keep one hotel for the whole trip. It is 3 h 15 m each way.",
    seconds: 11,
    effects: [{ label: "Day 5 unchanged", day: 5 }],
  },
  {
    id: "t9",
    group: "Earlier today",
    at: "08:22",
    user: "Bhimbetka before or after Bhojpur?",
    assistant:
      "Bhimbetka first. The shelters read badly in flat midday light, and Bhojpur temple is five minutes off the return road.",
    seconds: 9,
    effects: [{ label: "Day 4 order", day: 4 }],
  },
  {
    id: "t10",
    group: "Earlier today",
    at: "08:31",
    user: "Any museum closures I should know about?",
    assistant:
      "Sanchi Archaeological Museum is closed on Fridays. Day 3 is a Thursday, so you are clear, but do not swap days 3 and 4.",
    seconds: 13,
    tools: [{ name: "search_places", seconds: 5.8 }],
    effects: [{ label: "Day 3 constraint", day: 3, stopId: "sanchi-museum" }],
  },
  {
    id: "t11",
    group: "Earlier today",
    at: "09:05",
    user: "Show me the budget so far.",
    assistant:
      "Rail 8,400, hotel 62,500, cars 6,800, entries about 2,200. That is 79,900 of the 95,000 you set, leaving room for meals and the Pachmarhi day.",
    seconds: 16,
    effects: [{ label: "Budget summary", day: 1 }],
  },
  {
    id: "t12",
    group: "Earlier today",
    at: "09:18",
    user: "Move the day 3 start half an hour later.",
    assistant:
      "Day 3 now departs at 08:15 and still reaches Sanchi by 09:40. The museum shifts to 11:50 and lunch holds at 13:00.",
    seconds: 19,
    effects: [
      { label: "Depart 08:15", day: 3, stopId: "hotel-out" },
      { label: "Arrive 09:40", day: 3, stopId: "sanchi-stupa" },
    ],
  },
];

export const scriptedReply = {
  assistant:
    "Held a 15:30 tea stop at the Udayagiri car park kiosk and pushed the hotel return to 17:35. Nothing else on day 3 moved.",
  seconds: 12,
  tools: [{ name: "search_places", seconds: 5.1 }],
  effects: [{ label: "Return now 17:35", day: 3, stopId: "hotel-in" }],
};

export const improvementRows = [
  {
    label: "Session history",
    before: "Last 80 turns, no landmarks",
    after: "Whole session, grouped by day",
    gain: true,
  },
  { label: "Reading an old turn", before: "Snaps back to newest", after: "Position held", gain: true },
  { label: "Response time", before: "Lost when the turn ends", after: "Kept on every reply", gain: true },
  { label: "Trip data and tools", before: "Unchanged", after: "Unchanged", gain: false },
];
