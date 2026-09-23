/** The committed corpus trip `goa-relaxed` (corpus/trips/goa-relaxed.json), with
 * its placeholders left exactly as the planner saved them. Only the gap
 * suggestions are Lab-authored; they illustrate what a fill would offer and are
 * not verified availability. */

export type GapKind = "stay" | "meal" | "journey" | "fare";

export interface Gap {
  id: string;
  kind: GapKind;
  /** What the traveller is missing, in plain words. */
  need: string;
  /** Why it matters, shown under the need. */
  why: string;
  suggestions: string[];
}

export interface Stop {
  time?: string;
  name: string;
  kind: "flight" | "hotel" | "attraction" | "meal";
  note?: string;
  gap?: string;
}

export interface Day {
  day: number;
  date: string;
  title: string;
  summary: string;
  stops: Stop[];
}

export const trip = {
  title: "Relaxed Goa",
  dates: "Wed 10 – Sun 14 Mar 2027",
  party: "2 adults · from Bangalore",
  request: "Plan a relaxed 4 day trip to Goa from Bangalore for 2 adults, 10 to 14 March 2027. We want a slow pace, beaches and good food.",
};

export const gaps: Gap[] = [
  { id: "stay", kind: "stay", need: "Choose a hotel for 4 nights", why: "Every day starts and ends at \"Hotel (TBD)\", so no drive time, map route or price can be real.", suggestions: ["Taj Holiday Village, Candolim", "The Park Calangute", "W Goa, Vagator"] },
  { id: "d1-dinner", kind: "meal", need: "Day 1 dinner", why: "\"Beachside dining (TBD)\" on a trip that asked for good food.", suggestions: ["Britto's, Baga", "Souza Lobo, Calangute", "Infantaria, Calangute"] },
  { id: "d2-lunch", kind: "meal", need: "Day 2 lunch", why: "\"Lunch (TBD)\" between Candolim Beach and Fort Aguada.", suggestions: ["Gunpowder, Assagao", "Vinayak Family Restaurant", "Mum's Kitchen, Panjim"] },
  { id: "d2-dinner", kind: "meal", need: "Day 2 dinner", why: "\"Dinner (TBD)\" after the Fort Aguada sunset.", suggestions: ["Pousada by the Beach", "Thalassa, Siolim", "Fisherman's Wharf, Panjim"] },
  { id: "d3-lunch", kind: "meal", need: "Day 3 lunch at Palolem", why: "\"Beachside lunch (TBD)\" two and a half hours south of a North Goa base.", suggestions: ["Dropadi, Palolem", "Magic Italy, Palolem", "Ourem 88, Palolem"] },
  { id: "d4-brunch", kind: "meal", need: "Day 4 brunch", why: "\"Brunch (TBD)\" before the flight home.", suggestions: ["Artjuna, Anjuna", "Café Lilliput, Anjuna", "Baba Au Rhum, Anjuna"] },
  { id: "outbound", kind: "journey", need: "Pick an outbound flight time", why: "The flight to Goa has no time, so Day 1 cannot know when the beach walk is possible.", suggestions: ["Morning · lands by 10:00", "Midday · lands by 14:00", "Evening · lands by 19:00"] },
  { id: "fare", kind: "fare", need: "Replace a sample fare", why: "The selected fare is from \"Nuitée Air\", a provider test-mode offer. It looks priced (₹29,582) but cannot be booked.", suggestions: ["Find a bookable fare", "Keep as an estimate only"] },
];

export const days: Day[] = [
  {
    day: 1, date: "Wed 10 Mar", title: "Arrival & North Goa beach walk",
    summary: "Arrive in Goa, check in to your hotel, unwind with a gentle walk along Baga Beach, and enjoy a beachside dinner.",
    stops: [
      { name: "Flight: Bangalore to Goa", kind: "flight", gap: "outbound" },
      { name: "Hotel (TBD)", kind: "hotel", note: "Check-in and freshen up", gap: "stay" },
      { time: "16:00", name: "Baga Beach", kind: "attraction", note: "Relax and stroll · 2 h" },
      { time: "19:00", name: "Beachside dining (TBD)", kind: "meal", note: "Local Goan cuisine", gap: "d1-dinner" },
    ],
  },
  {
    day: 2, date: "Thu 11 Mar", title: "Candolim & Fort Aguada sunset",
    summary: "Spend the morning at Candolim Beach, enjoy a leisurely lunch, and visit Fort Aguada for sunset views.",
    stops: [
      { name: "Hotel (TBD)", kind: "hotel", note: "Start from hotel", gap: "stay" },
      { time: "10:00", name: "Candolim Beach", kind: "attraction", note: "Swim & sunbathe · 2 h" },
      { time: "13:00", name: "Lunch (TBD)", kind: "meal", note: "Try Goan seafood", gap: "d2-lunch" },
      { time: "17:00", name: "Fort Aguada", kind: "attraction", note: "Sunset views · 1 h 30" },
      { time: "19:30", name: "Dinner (TBD)", kind: "meal", note: "Relaxed evening meal", gap: "d2-dinner" },
    ],
  },
  {
    day: 3, date: "Fri 12 Mar", title: "South Goa & Palolem Beach",
    summary: "Head to South Goa for a relaxed day at Palolem Beach, with beachside lunch and evening free time.",
    stops: [
      { name: "Hotel (TBD)", kind: "hotel", note: "Start from hotel", gap: "stay" },
      { time: "11:00", name: "Palolem Beach", kind: "attraction", note: "Relax, swim · 3 h" },
      { time: "14:30", name: "Beachside lunch (TBD)", kind: "meal", note: "Local specialties", gap: "d3-lunch" },
      { time: "18:00", name: "Hotel (TBD)", kind: "hotel", note: "Return and unwind", gap: "stay" },
    ],
  },
  {
    day: 4, date: "Sat 13 Mar", title: "Anjuna Beach & departure",
    summary: "Enjoy a slow morning at Anjuna Beach, sample brunch, and depart for Bangalore in the afternoon.",
    stops: [
      { name: "Hotel (TBD)", kind: "hotel", note: "Check out", gap: "stay" },
      { time: "10:00", name: "Anjuna Beach", kind: "attraction", note: "Final beach stroll · 2 h" },
      { time: "12:30", name: "Brunch (TBD)", kind: "meal", note: "Cafe by the beach", gap: "d4-brunch" },
      { time: "15:00", name: "Flight: Goa to Bangalore", kind: "flight", note: "Nuitée Air · ₹29,582", gap: "fare" },
    ],
  },
];

/** Further improvements from the same review, ranked by expected value.
 * Each names the evidence that motivated it so the owner can pick one for a
 * later Lab or a direct handoff. */
export const improvements = [
  { rank: 1, title: "Never pin a guess on the map", evidence: "11.5% of cached place lookups share no word with the stop name: \"India Gate\" pinned to a tour agency, \"Meetings (User's location)\" to an AA office.", idea: "Pins whose resolved name does not match the stop show a hollow \"approximate\" marker with Confirm place, instead of a confident pin." },
  { rank: 2, title: "Show the day in the order it happens", evidence: "Hotel checkouts after the departing drive or train in Gujarat, Tokyo, Char Dham and Kerala; lunch listed after a 20:00 check-in in Rajasthan.", idea: "Render stops strictly by time with travel legs between them, and flag any stop whose time runs backwards as \"Out of order\" with Fix order." },
  { rank: 3, title: "Day summaries that cannot disagree with the day", evidence: "Lonavala's Day 2 summary promises Bhushi Dam and Tiger Point; its stops are the bazaar and Rajmachi.", idea: "Generate the summary line from the stops, or grey out any place the summary names that the day does not contain." },
  { rank: 4, title: "An unpriced trip should say so", evidence: "88 of 178 corpus trips carry no priced item at all, and only 13 carry a selected flight.", idea: "Show \"Not priced yet · 0 of 6 items priced\" with a Price this trip action instead of an empty or partial total." },
  { rank: 5, title: "Keep the promises the request made", evidence: "\"Include the flights\" (Paris), \"verify entry requirements\" (Bali) and \"Char Dham\" (2 of 4 dhams) were silently dropped.", idea: "A Request checklist in Details echoes each explicit ask with Met / Not yet / Dropped because…" },
  { rank: 6, title: "Wasted nights are visible", evidence: "Paris, Tokyo and Mysore keep the hotel one night past the flight or drive home.", idea: "Stay rows show nights used against nights booked and offer Shorten stay." },
];
