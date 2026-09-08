// Lab 22 re-argues one screen from Lab 21: the live agent stage. Every option here plans
// the same trips from the same facts, so the only difference is what the visitor is asked
// to do while it runs. The trips are deliberately multi-city and multi-modal — flights,
// trains, a hire car, trams and two different hotels — because a planner that only ever
// walks around one city is not the planner this product claims to be.

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
  label: string;
  title: string;
  request: string;
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
  shareUrl: string;
}

const lisbon: StageTrip = {
  id: "lisbon",
  label: "Lisbon and Porto",
  title: "6 days in Lisbon and Porto",
  request: "Lisbon and Porto in October, 6 days, food-led, mid-budget, no early starts",
  summary: "2 cities · 2 hotels · 6 days · 21 places",
  dateRange: "13–18 October 2026",
  travellers: "2 travellers",
  receipts: [
    { at: "0:02", kind: "read", text: "Read the request: Lisbon and Porto, 6 days, 2 travellers, food-led, mid-budget" },
    { at: "0:07", kind: "search", text: "Searched 63 stays across 4 Lisbon districts and 3 in Porto · kept 5" },
    { at: "0:12", kind: "price", text: "Open-jaw flights LHR → LIS, OPO → LHR: 24 pairings priced · best €486 · Duffel" },
    { at: "0:16", kind: "hotel", text: "Hotel 1 locked: Convento do Salvador, Alfama · 3 nights · €486" },
    { at: "0:21", kind: "place", day: 1, text: "Day 1 placed: lands 11:20, bags down 12:40, Alfama on foot from the door" },
    { at: "0:26", kind: "place", day: 2, text: "Day 2 placed: Belém by tram 15E, home along the 2.1 km riverside walk" },
    { at: "0:31", kind: "compare", text: "Sintra: train + bus 434 beat the hire car — the Pena lot fills before 10:00" },
    { at: "0:34", kind: "place", day: 3, text: "Day 3 placed: Sintra by train, two palaces, back in Lisbon by 18:40" },
    { at: "0:39", kind: "compare", text: "Lisbon → Porto: train 3h35 door-to-door beat the flight at 4h10 and €94 more" },
    { at: "0:43", kind: "hotel", text: "Hotel 2 locked: Torel Avantgarde, Porto · 2 nights · €398 · 6 min downhill to Ribeira" },
    { at: "0:46", kind: "place", day: 4, text: "Day 4 placed: 10:04 Alfa Pendular, check-in 13:30, Livraria Lello at 16:00" },
    { at: "0:51", kind: "compare", text: "Douro: hire car kept — the quintas are 9 km apart with no bus between them" },
    { at: "0:54", kind: "place", day: 5, text: "Day 5 placed: Douro by road, tasting at 10:25, car returned by 18:45" },
    { at: "0:58", kind: "place", day: 6, text: "Day 6 placed: Bolhão at 09:00, metro to OPO, 14:05 departure, 2 h buffer" },
    { at: "1:05", kind: "price", text: "Re-priced both stays after the dates locked · €884 · saved €126" },
    { at: "1:11", kind: "check", text: "Checked opening hours for 21 places · 2 conflicts fixed" },
    { at: "1:18", kind: "check", text: "Best total €4,428 · 5 sources compared · handoff links ready" },
  ],
  days: [
    {
      day: 1,
      weekday: "Tue",
      date: "13 Oct",
      city: "Lisbon",
      title: "Land, drop bags, Alfama on foot",
      color: "#e11d48",
      hotel: "H1",
      legs: [
        { mode: "flight", label: "LHR → LIS · TAP TP1363", duration: "2h 45", cost: "€243 pp" },
        { mode: "metro", label: "Aeroporto → Santa Apolónia", duration: "26 min", cost: "€3.20" },
        { mode: "walk", label: "Alfama loop", duration: "1.4 km" },
      ],
      stops: [
        { time: "08:05", name: "Heathrow T2", detail: "Bags in, 2 h before departure", kind: "flight" },
        { time: "11:20", name: "Lisbon Portela", detail: "Lands · metro from arrivals", kind: "flight" },
        { time: "12:40", name: "Convento do Salvador", detail: "Bag drop before the 15:00 check-in", kind: "hotel", marker: "H1" },
        { time: "14:30", name: "Miradouro de Santa Luzia", detail: "8 min uphill from the door", kind: "attraction", marker: "1" },
        { time: "16:00", name: "Sé de Lisboa", kind: "attraction", marker: "2", cost: "€5" },
        { time: "19:30", name: "Taberna Sal Grosso", detail: "Booked · walk-ins queue from 19:00", kind: "meal", cost: "€64" },
      ],
    },
    {
      day: 2,
      weekday: "Wed",
      date: "14 Oct",
      city: "Lisbon",
      title: "Belém by tram, back along the river",
      color: "#0f766e",
      hotel: "H1",
      legs: [
        { mode: "tram", label: "15E · Praça da Figueira → Belém", duration: "24 min", cost: "€3.20" },
        { mode: "walk", label: "Riverside return", duration: "2.1 km" },
      ],
      stops: [
        { time: "09:10", name: "Tram 15E", detail: "Second tram — the 08:50 is the commuter crush", kind: "transport" },
        { time: "09:40", name: "Mosteiro dos Jerónimos", detail: "Timed entry beats the 10:30 queue", kind: "attraction", marker: "1", cost: "€12" },
        { time: "11:30", name: "Pastéis de Belém", kind: "meal", marker: "2", cost: "€9" },
        { time: "13:00", name: "Torre de Belém", kind: "attraction", marker: "3", cost: "€8" },
        { time: "16:00", name: "LX Factory", detail: "On the walk home, not a separate trip", kind: "attraction", marker: "4" },
        { time: "20:00", name: "Cantina LX", kind: "meal", cost: "€58" },
      ],
    },
    {
      day: 3,
      weekday: "Thu",
      date: "15 Oct",
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
      day: 4,
      weekday: "Fri",
      date: "16 Oct",
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
      day: 5,
      weekday: "Sat",
      date: "17 Oct",
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
      day: 6,
      weekday: "Sun",
      date: "18 Oct",
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
      nights: "3 nights · 13–16 Oct",
      price: "€486",
      source: "Booking.com rate feed",
      checked: "4 min ago",
      beat: "€612 in Baixa, 12 min further from the tram",
      why: "Sits inside the day 1–3 walking loop, so three days need no transport at all.",
    },
    {
      marker: "H2",
      name: "Torel Avantgarde",
      city: "Porto",
      area: "Vitória",
      nights: "2 nights · 16–18 Oct",
      price: "€398",
      source: "Booking.com rate feed",
      checked: "4 min ago",
      beat: "€352 riverside, but 68 steps up from Ribeira with luggage",
      why: "Six minutes downhill to dinner and level with the metro, which matters on a car day.",
    },
  ],
  compares: [
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
  ],
  lines: [
    { label: "Flights", detail: "Open jaw LHR → LIS, OPO → LHR, 2 travellers, 1 bag each", price: "€486", source: "Duffel · TAP Air Portugal", checked: "4 min ago", beat: "€598 returning to Lisbon, plus a €62 train back" },
    { label: "Stays", detail: "5 nights across 2 hotels, Alfama and Vitória", price: "€884", source: "Booking.com rate feed", checked: "4 min ago", beat: "€1,010 keeping one Lisbon base and commuting north" },
    { label: "Rail and transfers", detail: "Alfa Pendular, Sintra line, trams, metro, bus 434", price: "€148", source: "CP · Carris · Metro do Porto", checked: "11 min ago", beat: "€284 if the Porto leg had flown" },
    { label: "Car hire, day 5 only", detail: "Compact, collected and returned in Porto, tolls included", price: "€76", source: "Rentalcars", checked: "11 min ago", beat: "€190 for the guided minibus" },
    { label: "Entries and tickets", detail: "Pena, Regaleira, Jerónimos, Belém, Lello, Bomfim tasting", price: "€194", source: "Official sites", checked: "22 min ago", beat: "€0 on the first Sunday for two of the six" },
    { label: "Food and local spend", detail: "Estimated from the 21 planned places and the walking routes", price: "€2,640", source: "Tripplanner estimate", checked: "recomputed on every change", beat: "€2,180 if three dinners move to tascas" },
  ],
  first: "€4,910",
  best: "€4,428",
  saved: "€482",
  sources: "5 sources compared",
  shareUrl: "tripplanner.app/t/lisbon-porto-oct",
};

const kyoto: StageTrip = {
  id: "kyoto",
  label: "Kyoto and Osaka",
  title: "5 days in Kyoto and Osaka",
  request: "Kyoto and Osaka in April with a 6-year-old, slow mornings, no queue over 20 minutes",
  summary: "2 cities · 2 hotels · 5 days · 16 places",
  dateRange: "4–8 April 2026",
  travellers: "2 adults, 1 child",
  receipts: [
    { at: "0:02", kind: "read", text: "Read the request: Kyoto and Osaka, 5 days, 2 adults and a 6-year-old, slow mornings" },
    { at: "0:08", kind: "search", text: "Searched 47 stays · dropped 31 with no triple room or futon option" },
    { at: "0:13", kind: "price", text: "Flights LHR → KIX return: 16 pairings priced · best €1,842 for three · Duffel" },
    { at: "0:17", kind: "hotel", text: "Hotel 1 locked: Nohga Hotel Kiyomizu · 3 nights · €612 · family room" },
    { at: "0:22", kind: "place", day: 1, text: "Day 1 placed: Haruka express from KIX, bags down 16:10, Gion after dinner" },
    { at: "0:28", kind: "compare", text: "Fushimi Inari: 07:30 on foot beat the 10:00 bus — the queue rule needs the early gate" },
    { at: "0:31", kind: "place", day: 2, text: "Day 2 placed: Inari at 07:40, back for a 2 h hotel break at 12:30" },
    { at: "0:36", kind: "place", day: 3, text: "Day 3 placed: Arashiyama by JR Sagano, bamboo grove, monkeys, 14:00 stop" },
    { at: "0:41", kind: "compare", text: "Kyoto → Osaka: shinkansen 15 min beat the 44-minute local for a tired child" },
    { at: "0:45", kind: "hotel", text: "Hotel 2 locked: Hotel Zentis Osaka · 2 nights · €404 · 8 min from Umeda" },
    { at: "0:48", kind: "place", day: 4, text: "Day 4 placed: Nozomi 11:12, castle at 14:00, Dotonbori before the crowd" },
    { at: "0:53", kind: "place", day: 5, text: "Day 5 placed: Rapi:t to KIX, 3 h buffer for a family bag drop" },
    { at: "1:01", kind: "check", text: "Checked every queue estimate against April averages · 2 stops moved earlier" },
    { at: "1:09", kind: "check", text: "Best total €4,690 · 4 sources compared · handoff links ready" },
  ],
  days: [
    {
      day: 1,
      weekday: "Sat",
      date: "4 Apr",
      city: "Kyoto",
      title: "Land, express north, Gion in the dark",
      color: "#e11d48",
      hotel: "H1",
      legs: [
        { mode: "flight", label: "LHR → KIX · JAL JL42", duration: "13h 05", cost: "€614 pp" },
        { mode: "train", label: "Haruka express · KIX → Kyoto", duration: "78 min", cost: "¥2,200 pp" },
      ],
      stops: [
        { time: "11:35", name: "Kansai International", detail: "Lands · Haruka from the terminal", kind: "flight" },
        { time: "14:40", name: "Kyoto station", kind: "transport" },
        { time: "16:10", name: "Nohga Hotel Kiyomizu", detail: "Family room, futon for the six-year-old", kind: "hotel", marker: "H1" },
        { time: "18:00", name: "Gion Shirakawa", detail: "Flat, lit, 12 min walk — nothing to queue for", kind: "attraction", marker: "1" },
        { time: "19:15", name: "Gion Kappa", kind: "meal", cost: "¥7,800" },
      ],
    },
    {
      day: 2,
      weekday: "Sun",
      date: "5 Apr",
      city: "Kyoto",
      title: "Inari at first light, then a real break",
      color: "#0f766e",
      hotel: "H1",
      legs: [
        { mode: "train", label: "JR Nara line · Kyoto → Inari", duration: "5 min", cost: "¥150 pp" },
        { mode: "walk", label: "Torii path, lower loop", duration: "1.8 km" },
      ],
      stops: [
        { time: "07:40", name: "Fushimi Inari", detail: "Lower loop only · empty until 09:00", kind: "attraction", marker: "1" },
        { time: "10:20", name: "Tofuku-ji", kind: "attraction", marker: "2", cost: "¥500 pp" },
        { time: "12:30", name: "Nohga Hotel Kiyomizu", detail: "Two hours off — the rule you asked for", kind: "hotel", marker: "H1" },
        { time: "15:30", name: "Nishiki Market", kind: "meal", marker: "3", cost: "¥3,400" },
        { time: "18:30", name: "Kiyomizu-dera at dusk", kind: "attraction", marker: "4", cost: "¥400 pp" },
      ],
    },
    {
      day: 3,
      weekday: "Mon",
      date: "6 Apr",
      city: "Arashiyama",
      title: "West by local train, home by two",
      color: "#b45309",
      hotel: "H1",
      legs: [
        { mode: "train", label: "JR Sagano · Kyoto → Saga-Arashiyama", duration: "17 min", cost: "¥240 pp" },
        { mode: "walk", label: "Grove to monkey park", duration: "1.6 km" },
      ],
      stops: [
        { time: "08:30", name: "Bamboo Grove", detail: "Before the 10:00 coaches", kind: "attraction", marker: "1" },
        { time: "09:45", name: "Iwatayama Monkey Park", detail: "20 min uphill · the child's pick", kind: "attraction", marker: "2", cost: "¥600 pp" },
        { time: "12:00", name: "Arashiyama Yoshimura", kind: "meal", cost: "¥4,200" },
        { time: "14:00", name: "Back at the hotel", detail: "Afternoon deliberately empty", kind: "hotel", marker: "H1" },
      ],
    },
    {
      day: 4,
      weekday: "Tue",
      date: "7 Apr",
      city: "Kyoto → Osaka",
      title: "Fifteen minutes on the shinkansen",
      color: "#6d28d9",
      hotel: "H1 → H2",
      legs: [
        { mode: "train", label: "Nozomi · Kyoto → Shin-Osaka", duration: "15 min", cost: "¥1,450 pp" },
        { mode: "metro", label: "Midosuji line · Umeda", duration: "8 min", cost: "¥240 pp" },
      ],
      stops: [
        { time: "10:30", name: "Nohga Hotel Kiyomizu", detail: "Checkout, bags forwarded to Osaka", kind: "hotel", marker: "H1" },
        { time: "11:12", name: "Nozomi 15", detail: "Reserved, luggage rack booked", kind: "transport", cost: "¥4,350" },
        { time: "12:20", name: "Hotel Zentis Osaka", kind: "hotel", marker: "H2" },
        { time: "14:00", name: "Osaka Castle", kind: "attraction", marker: "1", cost: "¥600 pp" },
        { time: "17:30", name: "Dotonbori", detail: "Before the 19:00 crush", kind: "attraction", marker: "2" },
      ],
    },
    {
      day: 5,
      weekday: "Wed",
      date: "8 Apr",
      city: "Osaka → London",
      title: "Rapi:t to the plane",
      color: "#0369a1",
      hotel: "H2",
      legs: [
        { mode: "train", label: "Nankai Rapi:t · Namba → KIX", duration: "38 min", cost: "¥1,490 pp" },
        { mode: "flight", label: "KIX → LHR · JAL JL41", duration: "12h 40", cost: "€614 pp" },
      ],
      stops: [
        { time: "08:30", name: "Umeda Sky Building", detail: "Opens 09:30 — held for a slow morning", kind: "attraction", marker: "1", cost: "¥1,500 pp" },
        { time: "11:00", name: "Hotel Zentis Osaka", detail: "Checkout", kind: "hotel", marker: "H2" },
        { time: "12:10", name: "Rapi:t α", kind: "transport" },
        { time: "15:45", name: "JAL JL41", kind: "flight" },
      ],
    },
  ],
  hotels: [
    { marker: "H1", name: "Nohga Hotel Kiyomizu", city: "Kyoto", area: "Higashiyama", nights: "3 nights · 4–7 Apr", price: "€612", source: "Booking.com rate feed", checked: "6 min ago", beat: "€498 near the station, 22 min from every evening stop", why: "Walking distance to the two dusk stops, so no train after 18:00 with a tired child." },
    { marker: "H2", name: "Hotel Zentis Osaka", city: "Osaka", area: "Umeda", nights: "2 nights · 7–8 Apr", price: "€404", source: "Booking.com rate feed", checked: "6 min ago", beat: "€360 in Namba, louder until 01:00", why: "Eight minutes from Umeda, which is where the airport train and the shinkansen both land." },
  ],
  compares: [
    {
      id: "kyo-osa",
      subject: "Kyoto → Osaka",
      chosen: "Shinkansen · Nozomi",
      why: "Twenty-nine minutes saved does not sound like much until it is the difference between a child arriving fine and a child arriving done.",
      options: [
        { mode: "train", label: "Nozomi shinkansen", door: "15 min", cost: "¥4,350 for three", verdict: "Reserved seats, luggage rack, no standing.", picked: true },
        { mode: "train", label: "JR Special Rapid", door: "44 min", cost: "¥1,740 for three", verdict: "Cheaper, unreserved, and standing at that hour." },
        { mode: "road", label: "Taxi", door: "1h 05", cost: "¥18,000", verdict: "Door to door and four times the price of the fast train." },
      ],
    },
    {
      id: "kix",
      subject: "Getting in from KIX",
      chosen: "Haruka limited express",
      why: "The bus is direct but sits in the same traffic as everyone else; the express is the only option with a guaranteed seat after a 13-hour flight.",
      options: [
        { mode: "train", label: "Haruka express", door: "78 min", cost: "¥6,600 for three", verdict: "Reserved, luggage space, straight to Kyoto.", picked: true },
        { mode: "bus", label: "Airport limousine", door: "95 min", cost: "¥7,800 for three", verdict: "Direct to the hotel district, traffic dependent." },
        { mode: "road", label: "Private transfer", door: "80 min", cost: "¥32,000", verdict: "A car seat guaranteed, at six times the fare." },
      ],
    },
  ],
  lines: [
    { label: "Flights", detail: "LHR → KIX return, 2 adults and a child, 1 bag each", price: "€1,842", source: "Duffel · Japan Airlines", checked: "6 min ago", beat: "€2,120 for the one-stop pair that lands at 22:40" },
    { label: "Stays", detail: "5 nights across Kyoto and Osaka, family rooms", price: "€1,016", source: "Booking.com rate feed", checked: "6 min ago", beat: "€1,180 keeping one Kyoto base" },
    { label: "Rail", detail: "Haruka, Nozomi, Sagano and Nara lines, Rapi:t, metro", price: "€214", source: "JR · Nankai official", checked: "14 min ago", beat: "€388 for a 7-day JR pass this itinerary would not fill" },
    { label: "Entries and tickets", detail: "Kiyomizu, Tofuku-ji, monkey park, castle, Sky Building", price: "€96", source: "Official sites", checked: "22 min ago", beat: "€0 for the two shrines that never charge" },
    { label: "Food and local spend", detail: "Estimated from 16 planned places and the walking routes", price: "€1,522", source: "Tripplanner estimate", checked: "recomputed on every change", beat: "€1,290 with two convenience-store breakfasts" },
  ],
  first: "€5,180",
  best: "€4,690",
  saved: "€490",
  sources: "4 sources compared",
  shareUrl: "tripplanner.app/t/kyoto-osaka-apr",
};

const rome: StageTrip = {
  id: "rome",
  label: "Rome and Florence",
  title: "5 days in Rome and Florence",
  request: "Rome and Florence, long weekend, under £1,400 for two, no queueing",
  summary: "2 cities · 2 hotels · 5 days · 15 places",
  dateRange: "22–26 May 2026",
  travellers: "2 travellers",
  receipts: [
    { at: "0:02", kind: "read", text: "Read the request: Rome and Florence, 5 days, 2 travellers, under £1,400" },
    { at: "0:06", kind: "search", text: "Searched 58 stays in Monti, Trastevere and 3 Florence districts · kept 4" },
    { at: "0:11", kind: "price", text: "Flights LHR → FCO, FLR → LHR: 21 pairings priced · best €288 · Duffel" },
    { at: "0:15", kind: "hotel", text: "Hotel 1 locked: Hotel Nerva Boutique, Monti · 2 nights · €318" },
    { at: "0:20", kind: "place", day: 1, text: "Day 1 placed: Leonardo Express, bags down 14:20, Monti on foot" },
    { at: "0:25", kind: "compare", text: "Colosseum: 08:30 official slot beat every skip-the-line reseller by €34" },
    { at: "0:28", kind: "place", day: 2, text: "Day 2 placed: Colosseum at 08:30, Forum, Trastevere for dinner" },
    { at: "0:33", kind: "compare", text: "Rome → Florence: Frecciarossa 1h32 beat the flight, which is 4h05 door to door" },
    { at: "0:37", kind: "hotel", text: "Hotel 2 locked: Hotel Calimala · 3 nights · €486 · 90 seconds from the Duomo" },
    { at: "0:40", kind: "place", day: 3, text: "Day 3 placed: 10:35 Frecciarossa, check-in 13:00, Duomo climb at 16:20" },
    { at: "0:45", kind: "place", day: 4, text: "Day 4 placed: Uffizi first slot, Oltrarno afternoon, 4.1 km on foot" },
    { at: "0:49", kind: "place", day: 5, text: "Day 5 placed: San Lorenzo market, tram to FLR, 13:50 departure" },
    { at: "0:58", kind: "check", text: "Checked opening hours for 15 places · 1 Monday closure avoided" },
    { at: "1:06", kind: "check", text: "Best total €1,624 · 4 sources compared · handoff links ready" },
  ],
  days: [
    {
      day: 1,
      weekday: "Fri",
      date: "22 May",
      city: "Rome",
      title: "Express in from Fiumicino, Monti on foot",
      color: "#e11d48",
      hotel: "H1",
      legs: [
        { mode: "flight", label: "LHR → FCO · BA544", duration: "2h 35", cost: "€144 pp" },
        { mode: "train", label: "Leonardo Express · FCO → Termini", duration: "32 min", cost: "€14 pp" },
      ],
      stops: [
        { time: "11:45", name: "Fiumicino", kind: "flight" },
        { time: "13:10", name: "Roma Termini", kind: "transport" },
        { time: "14:20", name: "Hotel Nerva Boutique", detail: "Bag drop, 9 min walk from Termini", kind: "hotel", marker: "H1" },
        { time: "16:00", name: "Monti backstreets", kind: "attraction", marker: "1" },
        { time: "19:30", name: "Trattoria Vecchia Roma", kind: "meal", cost: "€58" },
      ],
    },
    {
      day: 2,
      weekday: "Sat",
      date: "23 May",
      city: "Rome",
      title: "Colosseum at opening, Trastevere at night",
      color: "#0f766e",
      hotel: "H1",
      legs: [
        { mode: "walk", label: "Monti → Colosseum", duration: "11 min" },
        { mode: "tram", label: "Tram 8 · Trastevere", duration: "14 min", cost: "€1.50 pp" },
      ],
      stops: [
        { time: "08:30", name: "Colosseum", detail: "Official first slot · 6 min queue", kind: "attraction", marker: "1", cost: "€18 pp" },
        { time: "10:45", name: "Roman Forum", detail: "Same ticket, no second queue", kind: "attraction", marker: "2" },
        { time: "13:30", name: "Roscioli", kind: "meal", cost: "€52" },
        { time: "16:00", name: "Pantheon", kind: "attraction", marker: "3", cost: "€5 pp" },
        { time: "20:00", name: "Trastevere", kind: "meal", marker: "4", cost: "€46" },
      ],
    },
    {
      day: 3,
      weekday: "Sun",
      date: "24 May",
      city: "Rome → Florence",
      title: "Frecciarossa north, Duomo at golden hour",
      color: "#b45309",
      hotel: "H1 → H2",
      legs: [
        { mode: "train", label: "Frecciarossa · Termini → S. M. Novella", duration: "1h 32", cost: "€39 pp" },
        { mode: "walk", label: "Station → Calimala", duration: "9 min" },
      ],
      stops: [
        { time: "09:30", name: "Hotel Nerva Boutique", detail: "Checkout", kind: "hotel", marker: "H1" },
        { time: "10:35", name: "Frecciarossa 9518", detail: "Seats 6A–6B, silent coach", kind: "transport", cost: "€78" },
        { time: "12:07", name: "Firenze S. M. Novella", kind: "transport" },
        { time: "13:00", name: "Hotel Calimala", detail: "90 seconds from the Duomo", kind: "hotel", marker: "H2" },
        { time: "16:20", name: "Duomo dome climb", detail: "Late slot · light and no queue", kind: "attraction", marker: "1", cost: "€30 pp" },
      ],
    },
    {
      day: 4,
      weekday: "Mon",
      date: "25 May",
      city: "Florence",
      title: "Uffizi first, Oltrarno after",
      color: "#6d28d9",
      hotel: "H2",
      legs: [{ mode: "walk", label: "Uffizi → Oltrarno loop", duration: "4.1 km" }],
      stops: [
        { time: "08:15", name: "Uffizi", detail: "First slot · Monday closure checked", kind: "attraction", marker: "1", cost: "€25 pp" },
        { time: "11:30", name: "Ponte Vecchio", kind: "attraction", marker: "2" },
        { time: "13:00", name: "Trattoria Cammillo", kind: "meal", cost: "€54" },
        { time: "15:30", name: "Palazzo Pitti gardens", kind: "attraction", marker: "3", cost: "€10 pp" },
        { time: "19:45", name: "Piazzale Michelangelo", detail: "Sunset at 20:34", kind: "attraction", marker: "4" },
      ],
    },
    {
      day: 5,
      weekday: "Tue",
      date: "26 May",
      city: "Florence → London",
      title: "Market morning, tram to the plane",
      color: "#0369a1",
      hotel: "H2",
      legs: [
        { mode: "tram", label: "T2 · Unità → Peretola", duration: "21 min", cost: "€1.70 pp" },
        { mode: "flight", label: "FLR → LHR · BA605", duration: "2h 20", cost: "€144 pp" },
      ],
      stops: [
        { time: "09:00", name: "Mercato Centrale", kind: "attraction", marker: "1" },
        { time: "10:40", name: "Hotel Calimala", detail: "Checkout", kind: "hotel", marker: "H2" },
        { time: "11:30", name: "Tram T2", detail: "2 h before departure", kind: "transport" },
        { time: "13:50", name: "BA605", kind: "flight" },
      ],
    },
  ],
  hotels: [
    { marker: "H1", name: "Hotel Nerva Boutique", city: "Rome", area: "Monti", nights: "2 nights · 22–24 May", price: "€318", source: "Booking.com rate feed", checked: "5 min ago", beat: "€284 near Termini, on the wrong side for every morning", why: "Eleven minutes from the Colosseum gate, which is what makes the 08:30 slot survivable." },
    { marker: "H2", name: "Hotel Calimala", city: "Florence", area: "Centro", nights: "3 nights · 24–26 May", price: "€486", source: "Booking.com rate feed", checked: "5 min ago", beat: "€402 across the river, 18 min from the Uffizi door", why: "Ninety seconds from the Duomo, so the late dome slot needs no plan to get home." },
  ],
  compares: [
    {
      id: "rome-flr",
      subject: "Rome → Florence",
      chosen: "Frecciarossa",
      why: "The flight is shorter in the air and longer in every other respect, and it moves you to two airports you would otherwise never see.",
      options: [
        { mode: "train", label: "Frecciarossa", door: "2h 10 door to door", cost: "€78 for two", verdict: "Centre to centre, silent coach, no bag drop.", picked: true },
        { mode: "flight", label: "ITA FCO → FLR", door: "4h 05 door to door", cost: "€214 for two", verdict: "Fifty minutes in the air, two airport transfers around it." },
        { mode: "road", label: "Hire car", door: "3h 30", cost: "€132 + ZTL risk", verdict: "Florence's restricted zone fines you for arriving at the hotel." },
        { mode: "bus", label: "Flixbus", door: "4h 15", cost: "€36 for two", verdict: "Half the price of the train and twice the day gone." },
      ],
    },
    {
      id: "colosseum",
      subject: "Colosseum entry",
      chosen: "Official 08:30 slot",
      why: "Every reseller sells the same timed slot with a fee on top; the only real variable is which slot you take.",
      options: [
        { mode: "walk", label: "Official first slot", door: "6 min queue", cost: "€36 for two", verdict: "Sold direct, cancellable, same ticket.", picked: true },
        { mode: "walk", label: "Skip-the-line reseller", door: "9 min queue", cost: "€70 for two", verdict: "€34 for a queue that is already short at 08:30." },
        { mode: "walk", label: "Midday walk-up", door: "50 min queue", cost: "€36 for two", verdict: "Free to change, expensive in the only currency that matters." },
      ],
    },
  ],
  lines: [
    { label: "Flights", detail: "Open jaw LHR → FCO, FLR → LHR, 2 travellers", price: "€288", source: "Duffel · British Airways", checked: "5 min ago", beat: "€342 returning to Rome, plus €78 back on the train" },
    { label: "Stays", detail: "5 nights across Monti and central Florence", price: "€804", source: "Booking.com rate feed", checked: "5 min ago", beat: "€910 for the riverside pair" },
    { label: "Rail and transfers", detail: "Leonardo Express, Frecciarossa, trams", price: "€146", source: "Trenitalia · official", checked: "13 min ago", beat: "€214 if the Florence leg had flown" },
    { label: "Entries and tickets", detail: "Colosseum, Pantheon, Duomo climb, Uffizi, Pitti", price: "€176", source: "Official sites", checked: "22 min ago", beat: "€244 through resellers for identical slots" },
    { label: "Food and local spend", detail: "Estimated from 15 planned places and the walking routes", price: "€210", source: "Tripplanner estimate", checked: "recomputed on every change", beat: "€168 with market lunches" },
  ],
  first: "€1,806",
  best: "€1,624",
  saved: "€182",
  sources: "4 sources compared",
  shareUrl: "tripplanner.app/t/rome-florence-may",
};

// Options E and F run a five-day cut of the same trip. Six days filled the console faster
// than a first-time visitor could read it; five still carries two cities, two hotels and
// flight, rail, road, tram, metro, coach and walking without a crowded card.
export const shortTrip: StageTrip = {
  id: "lisbon5",
  label: "Lisbon and Porto",
  title: "5 days in Lisbon and Porto",
  request: "Lisbon and Porto in October, 5 days, food-led, mid-budget, no early starts",
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
      checked: "4 min ago",
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
      checked: "4 min ago",
      beat: "€352 riverside, but 68 steps up from Ribeira with luggage",
      why: "Six minutes downhill to dinner and level with the metro, which matters on the car day.",
    },
  ],
  compares: [lisbon.compares[0], lisbon.compares[1], lisbon.compares[2]],
  lines: [
    { label: "Flights", detail: "Open jaw LHR → LIS, OPO → LHR, 2 travellers, 1 bag each", price: "€486", source: "Duffel · TAP Air Portugal", checked: "4 min ago", beat: "€598 returning to Lisbon, plus a €62 train back" },
    { label: "Stays", detail: "4 nights across 2 hotels, Alfama and Vitória", price: "€722", source: "Booking.com rate feed", checked: "4 min ago", beat: "€870 keeping one Lisbon base and commuting north" },
    { label: "Rail and transfers", detail: "Alfa Pendular, Sintra line, tram 28E, metro, bus 434", price: "€132", source: "CP · Carris · Metro do Porto", checked: "11 min ago", beat: "€268 if the Porto leg had flown" },
    { label: "Car hire, day 4 only", detail: "Compact, collected and returned in Porto, tolls included", price: "€76", source: "Rentalcars", checked: "11 min ago", beat: "€190 for the guided minibus" },
    { label: "Entries and tickets", detail: "Pena, Regaleira, Lello, Bomfim tasting", price: "€168", source: "Official sites", checked: "22 min ago", beat: "€0 on the first Sunday for two of the four" },
    { label: "Food and local spend", detail: "Estimated from the 17 planned places and the walking routes", price: "€2,180", source: "Tripplanner estimate", checked: "recomputed on every change", beat: "€1,840 if three dinners move to tascas" },
  ],
  first: "€4,180",
  best: "€3,764",
  saved: "€416",
  sources: "5 sources compared",
  shareUrl: "tripplanner.app/t/lisbon-porto-5day",
};

export const trips: StageTrip[] = [lisbon, kyoto, rome];
export const baseTrip = lisbon;

export function tripById(id: string): StageTrip {
  return trips.find((trip) => trip.id === id) ?? baseTrip;
}

// Option D turns the receipt log into the decisions behind it, and lets a visitor overrule
// one. The outcome is deliberately not free: a planner that never names the cost of your
// preference is not defending anything.
export interface StageDecision {
  id: string;
  at: string;
  subject: string;
  verdict: string;
  reason: string;
  rule: string;
  options: ModeOption[];
  overrule: string;
  /** One line short enough to sit inside the receipt console when the choice is offered there. */
  inline?: string;
  outcome: {
    headline: string;
    changes: string[];
    total: string;
    delta: string;
    warning: string;
  };
}

export const decisions: StageDecision[] = [
  {
    id: "lis-opo",
    at: "0:39",
    subject: "Lisbon → Porto, on day 4",
    verdict: "Train, not the flight",
    reason:
      "Four ways north were priced. The Alfa Pendular is 35 minutes quicker door to door than flying, €94 cheaper, and the only one with no bag drop at either end.",
    rule: "Whole-journey time, not the time in the air",
    options: lisbon.compares[0].options,
    overrule: "I would rather fly it",
    outcome: {
      headline: "Re-planned around TAP TP1938 at 14:20",
      changes: [
        "Day 4 now starts at 11:15 for the airport transfer, so the slow morning is gone",
        "Livraria Lello moves to day 5 at 09:30 — the 16:00 slot no longer fits",
        "The Douro tasting shifts 10:25 → 11:40 and loses the São Leonardo viewpoint",
        "Two airport transfers added: Humberto Delgado and Francisco Sá Carneiro",
      ],
      total: "€4,522",
      delta: "+€94",
      warning: "Three of the six days now contain a transfer. The pace rule you set is broken on day 5.",
    },
  },
  {
    id: "sintra",
    at: "0:31",
    subject: "Getting to Sintra, on day 3",
    verdict: "Train and bus 434, not a car",
    reason:
      "Driving is 20 minutes quicker until you arrive. The Pena car park fills before 10:00 in October and the overflow adds a 25-minute climb.",
    rule: "Arrival time at the gate, not arrival time in the town",
    options: lisbon.compares[1].options,
    overrule: "Give me the car anyway",
    outcome: {
      headline: "Re-planned around a day-3 hire car",
      changes: [
        "Pena Palace moves 09:20 → 11:40, the first slot after the overflow lot clears",
        "Quinta da Regaleira drops out — 11:40 and 12:15 cannot both stand",
        "Lunch moves to 15:10, which breaks the food-led request for that day",
        "Car collected 07:50 and returned 19:20, so day 3 is 40 minutes longer",
      ],
      total: "€4,460",
      delta: "+€32",
      warning: "One of the two palaces you came for is now missing from the plan.",
    },
  },
  {
    id: "hotel-1",
    at: "0:16",
    subject: "Where you sleep for the first three nights",
    verdict: "Alfama, not the cheaper Baixa room",
    reason:
      "The Baixa room is €126 less. It is also 12 minutes further from every day 1–3 stop, and those 12 minutes are paid six times.",
    rule: "Hotel cost plus the transport it forces, not the room rate alone",
    options: [
      { mode: "walk", label: "Convento do Salvador · Alfama", door: "0 transfers on days 1–3", cost: "€486", verdict: "Inside the walking loop the first three days use.", picked: true },
      { mode: "walk", label: "Baixa alternative", door: "12 min extra, each way", cost: "€360", verdict: "€126 cheaper and 72 minutes of extra walking." },
      { mode: "metro", label: "Parque das Nações", door: "22 min by metro", cost: "€298", verdict: "€188 cheaper, and every evening ends on a train." },
    ],
    overrule: "Take the cheaper room",
    outcome: {
      headline: "Re-planned around the Baixa room",
      changes: [
        "€126 comes off the total — the largest single saving available",
        "72 minutes of extra walking added across days 1–3",
        "Day 2's tram becomes the 28E from a different stop, 6 min further",
        "The day 1 miradouro drops out: it is no longer on the way to anything",
      ],
      total: "€4,302",
      delta: "−€126",
      warning: "This is a genuinely reasonable trade. The plan is showing you what it costs, not refusing it.",
    },
  },
];

// Two, not three. A third card turned the page into a reading exercise and buried the
// plan it was arguing about.
export const shortDecisions: StageDecision[] = [
  {
    id: "lis-opo-5",
    at: "0:33",
    subject: "Lisbon → Porto, on day 3",
    verdict: "Train, not the flight",
    reason:
      "Four ways north were priced. The Alfa Pendular is 35 minutes quicker door to door than flying, €94 cheaper, and the only one with no bag drop at either end.",
    rule: "Whole-journey time, not the time in the air",
    options: lisbon.compares[0].options,
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
    options: lisbon.compares[1].options,
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

export const signInMoments: Record<string, { when: string; copy: string; risk: string }> = {
  exact: {
    when: "At the first overrule — the first thing on the page that is the visitor's own",
    copy: "You changed the Porto leg. Sign in to keep it, and the rest of the plan comes with it.",
    risk: "A visitor who never argues is never asked, so the take-over path still has to carry the account moment on its own.",
  },
  ledger: {
    when: "After the run finishes, beside the two calls it wants you to check",
    copy: "Keep this plan and the two decisions behind it. Nothing is re-planned; it moves with you as it is.",
    risk: "The ask lands after the payoff, which is safe, but a visitor who leaves during the run is never asked at all.",
  },
  asis: {
    when: "At take-over: the moment you replace the demo destination with your own",
    copy: "You are about to make this yours. Sign in and it is saved from the first second — or carry on as a guest.",
    risk: "Asking at take-over is early; if it reads as a wall, the demo's momentum is spent.",
  },
  plain: {
    when: "After your own plan exists, at the first save — the demo never asks",
    copy: "Keep this plan. Nothing is re-planned; it moves with you exactly as it is.",
    risk: "A visitor who closes the tab inside 30 days still finds the trip. After that it is gone.",
  },
  yours: {
    when: "Never during planning. The account is offered when the plan is worth keeping, and it adopts the guest trip whole",
    copy: "This is your Lisbon and Porto plan, made 4 minutes ago. Keep it, and the preferences behind it come too.",
    risk: "Nothing is asked for until value exists, so the guest trip must genuinely survive a browser restart.",
  },
  argue: {
    when: "After the first overrule, because that is the first thing a visitor has made that is theirs",
    copy: "You changed the Porto leg. Sign in to keep that decision — and the three the planner made under it.",
    risk: "If the overrule is trivial, asking straight after it looks like a trick. The ask must follow a real change.",
  },
};

export const faq = [
  {
    q: "Is this a recording?",
    a: "No. It is the same engine the workspace uses, running against the same sources, in your browser session. Replay it and the timings differ.",
  },
  {
    q: "Do I have to watch it?",
    a: "No. Every option here has a control that jumps to the finished plan, and one of them never runs a demo at all — it plans your destination from the first keystroke.",
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
