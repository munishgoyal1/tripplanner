// The public edge of the product: what an anonymous visitor sees before they own a trip.
// Every option argues over the same facts, so the content lives here once. The trip proof
// reuses the shared Lisbon fixture so the landing page promises exactly the trip the
// workspace Labs already show.

import { days, trip } from "../shared/tripFixture";

export const sampleDays = days.slice(0, 4);

export const product = {
  name: "Tripplanner",
  promise: "Say where you're going. Get a real trip back.",
  subPromise:
    "One planner that builds the whole itinerary around how you actually travel, then keeps working on the price until the booking links are worth opening.",
  beta: "Free while in beta",
};

export const examplePrompts = [
  "8 days in Lisbon and Porto in October, food-led, mid-budget",
  "Kyoto in April with a 6-year-old, slow mornings, no queues",
  "Long weekend in Rome under £900 for two",
  "Two weeks in Japan, first time, trains not flights",
];

// The demo plan the public page shows. Times, sources and ages are deliberately concrete:
// a landing page that shows a real price with a fetch time is making a different promise
// than one that shows a stock photo.
export const proof = {
  headline: `${sampleDays.length} days in ${trip.destination}, planned in 6 minutes`,
  subline: `${trip.travelers} travellers · ${trip.dateRange} · ${trip.counts.places} places · ${trip.totalCost} total`,
  builtAt: "generated 6 minutes ago, unedited",
  pricesCheckedAt: "prices checked 4 minutes ago",
};

export interface PriceLine {
  label: string;
  detail: string;
  price: string;
  source: string;
  checked: string;
  alternative: string;
}

export const priceLines: PriceLine[] = [
  {
    label: "Flights",
    detail: "LHR → LIS return, 2 travellers, 1 bag each",
    price: "€412",
    source: "Duffel · TAP Air Portugal",
    checked: "4 min ago",
    alternative: "€478 for the direct evening pair",
  },
  {
    label: "Stay",
    detail: "Hotel Convento do Salvador, 4 nights, Alfama",
    price: "€1,144",
    source: "Booking.com rate feed",
    checked: "4 min ago",
    alternative: "€1,240 for the Baixa alternative, 12 min further out",
  },
  {
    label: "Entries and tickets",
    detail: "Jerónimos, Belém Tower, tram 28 day passes",
    price: "€168",
    source: "Google Places · official sites",
    checked: "22 min ago",
    alternative: "€0 on the first Sunday of the month",
  },
  {
    label: "Food and local transport",
    detail: "Estimated from the 14 planned places and the walking routes",
    price: "€1,756",
    source: "Tripplanner estimate",
    checked: "recomputed on every change",
    alternative: "€1,410 if two dinners move to tascas",
  },
];

export const savings = {
  first: "€3,833",
  best: trip.totalCost,
  saved: "€353",
  sources: "3 sources compared",
  cardNote: "Amex Platinum hotel credit would take another €96 off — connect it later, we never see the card number.",
};

export const agentReceipts = [
  { at: "0:02", text: "Read the request: Lisbon, 4 days, 2 travellers, food-led, mid-budget" },
  { at: "0:06", text: "Checked 41 stays in Alfama, Baixa and Príncipe Real · kept 3" },
  { at: "0:14", text: "Flights LHR → LIS: 18 pairings priced · best €412 · Duffel" },
  { at: "0:21", text: "Day 1 placed: land 11:20, bags down 13:00, Alfama on foot" },
  { at: "0:33", text: "Rejected Sintra on day 2 — 78 min transfer breaks the pace rule" },
  { at: "0:41", text: "Day 3 placed: Belém morning, LX Factory afternoon, 2.1 km walk" },
  { at: "0:52", text: "Re-priced the stay after the date lock · €1,144 · saved €96" },
  { at: "1:04", text: "Checked opening hours for all 14 places · 1 conflict fixed" },
  { at: "1:12", text: "Best total €3,480 · 3 sources compared · handoff links ready" },
];

export const capabilities = [
  {
    title: "A plan, not a list of links",
    body: "Every day is placed with real times, real transfers and the constraints you gave — naps, no queues over 20 minutes, dinner before 20:00.",
  },
  {
    title: "Prices you can check",
    body: "Each number carries its source and when it was fetched. If it is our estimate, it says so.",
  },
  {
    title: "The best total, then a clean handoff",
    body: "It keeps comparing until the total stops falling, then hands you the exact links to book. We never take a payment.",
  },
];

export const steps = [
  { step: "1", title: "Say it in your own words", body: "One sentence is enough. It asks only for what it genuinely needs." },
  { step: "2", title: "Watch the trip get built", body: "Days, transfers, prices and the reasoning arrive as they resolve — nothing hidden behind a spinner." },
  { step: "3", title: "Take it over", body: "Move a stop, change a hotel class, tighten the budget. The plan re-checks itself, including the price." },
];

export const destinations = [
  { city: "Lisbon", country: "Portugal", days: "4 days", from: "from €1,740 pp", why: "October is the last warm month and the queues are gone" },
  { city: "Kyoto", country: "Japan", days: "6 days", from: "from €2,310 pp", why: "Cherry blossom windows are short — the plan books around the forecast" },
  { city: "Amalfi Coast", country: "Italy", days: "5 days", from: "from €1,980 pp", why: "Ferry timetables decide the itinerary more than the hotels do" },
  { city: "Reykjavík", country: "Iceland", days: "4 days", from: "from €1,520 pp", why: "Aurora odds and road closures change the day order nightly" },
  { city: "Porto", country: "Portugal", days: "3 days", from: "from €890 pp", why: "Pairs with Lisbon on a 3-hour train, not a second flight" },
  { city: "Marrakech", country: "Morocco", days: "4 days", from: "from €1,180 pp", why: "A riad location changes the whole walking plan" },
];

export const trustPoints = [
  "No account needed to plan. Your trip is saved in this browser until you sign in.",
  "We never take a payment and never hold your card. Booking happens on the provider's own site.",
  "Prices come from Duffel, Booking.com and official ticket sites, each stamped with a fetch time.",
  "Preferences you give once — pace, budget, who travels with you — are reused on the next trip and can be deleted in one action.",
];

export const faq = [
  {
    q: "Is this another chatbot?",
    a: "No. The model reads your intent, but a deterministic engine places stops, validates times and owns the plan. That is why it can refuse to put an attraction after your flight home.",
  },
  {
    q: "Do I have to sign in?",
    a: "Only to keep a trip past this browser, or to share it. The plan you already made moves with you unchanged.",
  },
  {
    q: "Can it book for me?",
    a: "Not yet, and not silently. It gets you to the exact provider page with the right dates, travellers and fare already chosen.",
  },
  {
    q: "How is the price the best one?",
    a: "It compares the sources it can reach, keeps the whole-trip total rather than the cheapest single line, and shows you what it rejected.",
  },
];

export const footerColumns = [
  { title: "Product", links: ["How it works", "Sample trip", "What it costs", "Changelog"] },
  { title: "Destinations", links: ["Lisbon", "Kyoto", "Amalfi Coast", "All destinations"] },
  { title: "Company", links: ["About", "Privacy", "Terms", "Contact"] },
];

// When each option asks for an account. This is a real product decision, not styling:
// asked too early it kills the first plan, asked too late the trip is stranded in a browser.
export const signInMoments: Record<string, { when: string; copy: string; risk: string }> = {
  prompt: {
    when: "After the plan exists, when the visitor saves, shares or edits a second time",
    copy: "Keep this Lisbon plan. Nothing is re-planned — it moves with you exactly as it is.",
    risk: "A visitor who closes the tab in the first 30 days still finds the trip; after that it is gone.",
  },
  magazine: {
    when: "After the plan exists, at the first save — same as A, but most visitors have already read a full plan before typing",
    copy: "Keep your Lisbon plan and the one you were reading. Both land in the same account.",
    risk: "Longer path to the first prompt, so a visitor who wanted to type immediately has to scroll or find the sticky bar.",
  },
  intake: {
    when: "After the plan exists, but the intake answers are already a profile, so the account is offered as 'save these preferences too'",
    copy: "Keep this trip and the preferences behind it — pace, budget and who travels with you carry to the next one.",
    risk: "Feels like a signup funnel if the intake is long; the fields must stay optional.",
  },
  stage: {
    when: "At take-over: the moment you replace the demo destination with your own, before the second plan is spent",
    copy: "You are about to make this yours. Sign in and it is saved from the first second — or carry on as a guest.",
    risk: "Asking at take-over is the earliest of the four; if it reads as a wall, the demo's momentum is wasted.",
  },
};
