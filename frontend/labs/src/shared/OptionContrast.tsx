import { Columns2 } from "lucide-react";
import { allLabs } from "./labRecords";

interface ContrastRow {
  option: string;
  /** 0-100 fit for this product. Rows are authored A-C but always render best first. */
  score: number;
  idea: string;
  buys: string;
  costs: string;
  choose: string;
}

interface ContrastDefinition {
  /** The single sentence naming what the options genuinely disagree about. */
  axis: string;
  rows: ContrastRow[];
  /** Plain prose saying why the ranking lands where it does, in one paragraph. */
  verdict: string;
  /** What every option holds identical, so the table above is the whole difference. */
  same: string;
  /** Option label that was selected, for Labs that are already decided. */
  chosen?: string;
}

const contrasts: Record<string, ContrastDefinition> = {
  "localization": {
    axis:
      "Every option formats the same four trips and keeps provider currency honest. They disagree about when locale is confirmed, where the durable setting lives, and whether a trip can temporarily override display currency.",
    rows: [
      {
        option: "A · Welcome setup",
        score: 74,
        idea: "Country and language are a deliberate first-visit step.",
        buys: "No ambiguity about the chosen formats before planning starts.",
        costs: "Configuration blocks the first proof of value and asks obvious questions of most visitors.",
        choose: "A wrong regional default would be more damaging than one extra onboarding step.",
      },
      {
        option: "B · Detect, then confirm",
        score: 86,
        idea: "Browser region seeds one compact Home confirmation.",
        buys: "A fast default with an explicit correction path that disappears after use.",
        costs: "VPNs, travel, shared devices, and browser settings can make the inference wrong.",
        choose: "Most visitors use a device configured for the formats they expect.",
      },
      {
        option: "C · Profile-first",
        score: 92,
        idea: "A quiet Home chip leads to a durable Region and language destination in Account settings.",
        buys: "One stable cross-device preference without spending daily workspace space.",
        costs: "A first-time visitor may not notice an inferred default until a format looks wrong.",
        choose: "Locale changes rarely and belongs beside the other reusable travel defaults.",
      },
      {
        option: "D · Workspace quick switch",
        score: 68,
        idea: "Country and currency sit persistently beside Export.",
        buys: "Immediate switching while comparing trips, quotes, or screenshots.",
        costs: "An infrequent preference permanently competes with planning controls.",
        choose: "The owner regularly presents or compares the same plan for different regional audiences.",
      },
      {
        option: "E · Profile + trip lens",
        score: 89,
        idea: "Profile owns the default; Trip actions can override display currency and show source currency.",
        buys: "The most honest cross-border comparison without changing the durable account preference.",
        costs: "Users must understand account default, trip override, provider currency, and conversion freshness.",
        choose: "Cross-border provider quotes are common enough that dual-currency review is core work.",
      },
    ],
    same: "The four trip fixtures, itinerary choices, provider quote amounts and currencies, English copy, Home hierarchy, workspace content, profile identity, and export action. Every option supports INR, USD, GBP, and EUR and applies the same date, time, unit, temperature, tax, service, driving, holiday, address, and phone rules.",
    verdict:
      "C is the best default because locale is a durable account preference, not a command used often enough to occupy the workspace. Pair it with B's one-time confirmation so an inferred setting never becomes invisible. E is the right extension when real cross-border quotes arrive: it keeps provider currency and conversion freshness visible without turning the whole toolbar into a locale switcher. A is too much ceremony for first value, while D spends permanent space on an occasional correction.",
  },
  "product-themes": {
    axis:
      "All six render the same production landing, copy, controls, trip, and interaction model. They disagree only about the product's visual language: palette, typography, surface character, contrast, and signal colours.",
    rows: [
      {
        option: "A · Postcard editorial",
        score: 88,
        idea: "Warm paper, editorial serif, coral action, and blue-green evidence.",
        buys: "A humane travel voice that bridges inspiration and serious planning.",
        costs: "The warmer surfaces can feel less operational in dense workspace views.",
        choose: "The product should feel considered and travel-specific before it feels technical.",
      },
      {
        option: "B · Midnight atlas",
        score: 84,
        idea: "The current dark stage extended into a cinematic atlas system.",
        buys: "Strong continuity with the landing already in production and confident contrast.",
        costs: "A dark family across every surface can become heavy during long planning sessions.",
        choose: "The existing public identity is the strongest product signal to preserve.",
      },
      {
        option: "C · Coastal mineral",
        score: 91,
        idea: "Sea-glass neutrals, mineral blue, terracotta action, and restrained type.",
        buys: "The calmest and most legible system for dense itinerary work.",
        costs: "It is quieter and less immediately theatrical than the public dark stage.",
        choose: "Dependable planning should lead and visual drama should stay secondary.",
      },
      {
        option: "D · Citrus modernist",
        score: 80,
        idea: "Chalk surfaces, cobalt navigation, and citrus action signals.",
        buys: "A crisp, energetic identity with clear command emphasis.",
        costs: "The brighter signals can compete with trip content and status colours.",
        choose: "The product should feel contemporary and fast rather than contemplative.",
      },
      {
        option: "E · Aegean sun",
        score: 93,
        idea: "Salt-white space, ultramarine structure, bougainvillea action, and warm sun signals.",
        buys: "The clearest travel identity here: optimistic, geographic, and vibrant without losing legibility.",
        costs: "The island references need restraint so the system does not narrow the product to beach travel.",
        choose: "Travel character should be unmistakable from the first screen while planning still feels rigorous.",
      },
      {
        option: "F · Tropical wayfinder",
        score: 89,
        idea: "Palm green, mango action, lagoon evidence, and hibiscus detail used like a wayfinding system.",
        buys: "Warmth, adventure, and strong navigation cues with enough deep green to anchor dense information.",
        costs: "Its richer signals require discipline around warning, booking, and map-status colours.",
        choose: "The product should feel lively and exploratory while retaining an operational backbone.",
      },
    ],
    same: "The production PublicEntry DOM and behavior, every word of copy, the replay sequence, inline overruling and undo, the Plan mine and Skip actions, the Lisbon and Porto fixture, evidence content, order, and responsive layout.",
    verdict:
      "E is now the strongest travel-specific direction: its salt-white, ultramarine, bougainvillea, and sun palette feels geographic and optimistic while keeping the information hierarchy crisp. C remains the calmest system for long planning sessions, and F offers a warmer, more adventurous alternative with a strong wayfinding logic. A is editorial, B preserves the current stage most directly, and D supplies modernist energy. The decision here is entirely visual: the current landing experience is fixed in every row.",
  },
  "live-plan": {
    axis:
      "All six keep Lab 21's bet that the product is best proved by planning in front of you. They disagree about the visitor's role while it runs: audience, reader, subject, or opponent — and, for E and F, about when the argument is offered.",
    rows: [
      {
        option: "A · Daylight stage",
        score: 68,
        idea: "Lab 21's stage with the theme changed and nothing else.",
        buys: "A clean read on whether the dark console was carrying the idea.",
        costs: "Every wording problem survives: 'Take over', an indeterminate spinner, someone else's trip.",
        choose: "The only complaint about the shipped version was that it looked unlike the app.",
      },
      {
        option: "B · The same stage, said plainly",
        score: 81,
        idea: "Identical choreography, rewritten so nothing reads as a game.",
        buys: "A skip control, a step count, labelled pending days, and a call to action about your trip.",
        costs: "It is still a demo of Lisbon, and it adds no reason to stay past the first read.",
        choose: "The mechanic was fine and only the language was working against it.",
      },
      {
        option: "C · Your trip from the first keystroke",
        score: 84,
        idea: "No demo at all — the destination is the hero and the plan is already yours.",
        buys: "Nothing has to be taken over, and the account is never asked for during planning.",
        costs: "An honest version runs a real agent for anonymous traffic, which is the one genuinely expensive answer here.",
        choose: "Visitors arrive knowing where they want to go.",
      },
      {
        option: "D · The decision replay",
        score: 89,
        idea: "The stream is judgement, not activity, and you can overrule it.",
        buys: "The visitor acts before signing up, and the shared link carries reasoning no competitor can copy.",
        costs: "Decisions must become first-class data, and a scripted overrule is a promise the planner then has to keep.",
        choose: "The differentiator is the reasoning, and it has to be felt rather than described.",
      },
      {
        option: "E · Dark stage, argued during the run",
        score: 92,
        idea: "Lab 21's dark stage untouched, with two overrulable choices offered inside the receipt stream.",
        buys: "The mechanic without a redesign: same layout, same page length, and the argument arrives while attention is highest.",
        costs: "Interrupting a run that is still going risks reading as a modal, and the strip is too small to show the full comparison.",
        choose: "The stage was already right and the only thing missing was the visitor's hand on it.",
      },
      {
        option: "F · Dark stage, argued after it finishes",
        score: 90,
        idea: "The same dark stage, run through uninterrupted, then the console swaps into a two-item decision ledger.",
        buys: "The run stays clean, and the argument gets the whole comparison table because there is room for it once the plan exists.",
        costs: "A visitor who leaves during the run never sees the differentiator at all, and the swap has to be discoverable.",
        choose: "Nothing should interrupt the proof, and the argument is a second act rather than part of the first.",
      },
    ],
    same: "The Lisbon and Porto fixture, its two hotels, its flight, train, car and tram legs, its priced lines and their sources, the guest trip and its expiry, and the promise never to hold a card. A to D run the six-day cut; E and F run the five-day one.",
    verdict:
      "E and F are the two to choose between; everything above them is now working material. Both are Lab 21's option D in its dark console with the layout, the choreography and the receipt stream intact, and both add exactly one thing — that the visitor can push back, twice, on the Porto leg and the Sintra day. E offers the choice while the run is still going, which puts the argument where attention is highest and costs nothing in page height, but a one-line strip cannot show the comparison that justifies the answer. F waits until the plan is finished and swaps the console into a two-item ledger, which buys room for the whole rejected-options table and keeps the run clean, at the price that a visitor who leaves early never meets the differentiator at all. D remains the maximal version of the same idea and is worth keeping visible: it replaces the receipt console entirely, which is more honest about what the product is but abandons the stage you liked. C answers the sharpest objection to the whole Lab — that somebody else's Lisbon is not evidence about your Kyoto — but pays for it with a real agent run before an account exists. B is a floor rather than a choice: its wording fixes belong in whichever option wins, and E and F have already taken the important one. A exists to settle the theme question and has done so.",
  },
  "first-visit": {
    axis:
      "All four sell the same product with the same plan and the same prices. They disagree about what the first ten seconds are spent on: asking, proving, interviewing, or performing.",
    rows: [
      {
        option: "A · Prompt-first hero",
        score: 76,
        idea: "The input is the hero; proof waits below the fold.",
        buys: "The shortest path from arrival to a real trip, and the least to build.",
        costs: "It claims rather than proves, and looks like every other AI product.",
        choose: "Visitors mostly arrive already convinced, by word of mouth.",
      },
      {
        option: "B · Proof-first magazine",
        score: 86,
        idea: "A finished plan, with sourced prices, is the page.",
        buys: "Belief before the ask, plus destination pages worth indexing.",
        costs: "The one action is pushed down, and content has to be maintained.",
        choose: "Strangers need a reason to believe before they will type.",
      },
      {
        option: "C · Guided intake",
        score: 64,
        idea: "A short form writes the first prompt for you.",
        buys: "Nobody stares at an empty box, and the answers seed preferences.",
        costs: "Five decisions before anything happens, and it reads like a booking site.",
        choose: "The audience cannot describe a trip in a sentence.",
      },
      {
        option: "D · Live agent stage",
        score: 83,
        idea: "The product plans a trip in front of you, price falling live.",
        buys: "Both claims — the reasoning and the best total — become visible at once.",
        costs: "Autoplay, a dark theme unlike the app, and one destination that is not yours.",
        choose: "The differentiator is invisible until someone watches it happen.",
      },
    ],
    same: "The Lisbon fixture plan, its four days, its priced lines and their sources, the guest trip URL and its expiry, and the promise never to hold a card.",
    verdict:
      "B wins on the ordering question because this product's hard problem is belief, not intent: a stranger has no reason to trust that the times, transfers and totals are real until they read a finished plan, and that same content is the only thing here worth indexing. D wins the demonstration question outright — it is the only option that makes the reasoning and the falling price legible at the same moment — but it rests on one destination, needs JavaScript to say anything, and speaks a visual language the workspace does not. A is the safe answer and the cheapest to ship, and it is also the one a competitor can copy in an afternoon. C solves a real problem for people who cannot write the prompt, and pays for it by feeling like a booking form on first contact. The honest recommendation is B's structure with A's composer promoted into the hero and D's stage as the proof block, and C's four questions kept as a fallback behind an 'I'm not sure where' link.",
  },
  "travel-documents": {
    axis:
      "All three read a document once, keep the fields, and discard the file. They disagree about where the kept record lives, and whether you sort a document before or after you hand it over.",
    rows: [
      {
        option: "A · Trip readiness rail",
        score: 71,
        idea: "The trip owns the whole subject, in its third pane.",
        buys: "One place to look, and nothing to manage anywhere else.",
        costs: "The Details pane, which is where you decide about a place.",
        choose: "Paperwork is the thing you open the trip to check.",
      },
      {
        option: "B · Account vault, trip shows gaps",
        score: 82,
        idea: "Two homes for two lifetimes: passports are yours, references are the trip's.",
        buys: "The trip never turns into a document manager, and Details stays.",
        costs: "The answer is one click away instead of already on screen.",
        choose: "Most trips are already in order and only need a badge.",
      },
      {
        option: "C · Document inbox",
        score: 64,
        idea: "Intake is separated from placement; items route themselves afterwards.",
        buys: "Six email attachments emptied in one gesture, triaged later.",
        costs: "A second queue that goes stale, and a trip that looks ready while it does.",
        choose: "Documents arrive in batches rather than one at a time.",
      },
    ],
    same: "The retention rule, the Lisbon fixture and its travellers, and every deterministic check.",
    verdict:
      "B wins because it splits the problem the way your life already splits it: a passport belongs to a person and outlives every trip, while a booking reference belongs to one trip and dies with it. A puts both inside the trip, which is easier to explain but spends the Details pane and turns a planner into a document manager. C is the only option that solves batch intake, and it pays for that with a second queue that goes stale and a trip that looks ready while unsorted paper sits behind it. Take B, and borrow C's drop-anything intake later if attachments ever arrive six at a time.",
  },
  "agentic-planning": {
    axis:
      "All three give the agent the same typed operations and the same trip model. They disagree about where the stop-and-ask line sits, and how much of its reasoning is standing furniture.",
    rows: [
      {
        option: "A · Proposal first",
        score: 74,
        idea: "Nothing is written until you apply it.",
        buys: "Zero silent damage, and the reasoning arrives before the change.",
        costs: "One extra interaction on every change that was always safe.",
        choose: "You do not yet trust the agent to write to the trip.",
      },
      {
        option: "B · Guarded autonomy",
        score: 86,
        idea: "Safe edits land with an Undo receipt; dangerous ones hard-stop into a proposal.",
        buys: "Today's speed for ordinary edits, with the damaging class made impossible.",
        costs: "You are trusting the invariant list to be complete.",
        choose: "Most of your edits are routine and you want them to feel it.",
      },
      {
        option: "C · Plan console",
        score: 63,
        idea: "A standing rail holds your declared rules, live invariants, and a revertible ledger.",
        buys: "A readable history and per-entry revert across a long editing life.",
        costs: "A permanent 20rem rail, even on a trip you never argue with.",
        choose: "You edit one trip repeatedly over weeks.",
      },
    ],
    same: "The trip data model, the agent's phases and tools, and the verdict every channel receives.",
    verdict:
      "B wins because it sorts edits by how much damage they can do instead of treating every edit as equally dangerous, so routine changes stay fast and the destructive class becomes impossible. A is safer on paper and is the right answer while you still distrust the agent, but it charges an approval for the many changes that were never risky. C gives the best long-term audit trail and earns its 20rem rail only on a trip you keep arguing with for weeks. Start at B; C's ledger can be added behind it if history turns out to be the thing you miss.",
  },
  "map-canvas": {
    axis:
      "All three keep the same route colours, marker numbers, and day identity. They disagree about how much of the pane is geography, and whether the map is also a route-planning surface.",
    rows: [
      {
        option: "A · Floating deck",
        score: 72,
        idea: "The map runs edge to edge; controls float over it as glass cards.",
        buys: "The most map per pixel, and controls that feel weightless.",
        costs: "Floating cards can cover pins once the pane is narrow.",
        choose: "You mostly look at the map rather than edit from it.",
      },
      {
        option: "B · Route dock",
        score: 84,
        idea: "A bottom dock carries day tabs, day facts, and the day's route timeline.",
        buys: "The map becomes a place to plan the sequence, not just see it.",
        costs: "About 7rem of the pane, permanently, at the bottom.",
        choose: "You work out the order of a day on the map itself.",
      },
      {
        option: "C · Command ribbon",
        score: 66,
        idea: "Today's three stacked control rows collapse into one row and one fact ribbon.",
        buys: "The smallest change from today and the safest to ship.",
        costs: "The least new capability of the three.",
        choose: "Today's map is nearly right and only feels cluttered.",
      },
    ],
    same: "Google Maps behaviour, provider search, geocoding, and every trip mutation.",
    verdict:
      "B wins because it turns the map from something you look at into somewhere you arrange a day, and the bottom dock is the only place a route timeline can sit without covering pins. A gives the most geography per pixel and is better if you only ever read the map, but its floating cards start hiding the markers they describe as soon as the pane narrows. C is the smallest and safest change, fixes the clutter, and adds no capability whatsoever. Pay B's 7rem to get sequence planning on the canvas; fall back to C only if the dock proves too tall in practice.",
  },
  "itinerary-canvas": {
    axis:
      "All three keep every one of the 31 production facts on a stop, a day, and the trip. They disagree about which handful of facts are always loud, and what carries your eye down a day.",
    rows: [
      {
        option: "A · Journey spine",
        score: 74,
        idea: "One continuous time rail runs the whole trip, with travel legs on the line.",
        buys: "You feel the shape of a day, and the gaps between stops are visible.",
        costs: "About 5rem of horizontal space that never holds a fact.",
        choose: "Travel time between stops is what you most often get wrong.",
      },
      {
        option: "B · Layered stop cards",
        score: 87,
        idea: "Time, name, and booking status are loud; everything else is a quiet chip row.",
        buys: "The fastest scan of a long day, with notes opening in place.",
        costs: "Notes and tips are one click away rather than always printed.",
        choose: "You scan a 20-stop trip looking for one stop.",
      },
      {
        option: "C · Editorial agenda",
        score: 68,
        idea: "Morning, Afternoon and Evening chapters under Fraunces titles.",
        buys: "The most pleasant read from beginning to end.",
        costs: "The densest single meta line of facts per stop.",
        choose: "You read the plan far more often than you edit it.",
      },
    ],
    same: "All 31 facts, the 20-stop fixture, and the 16-minute ferry conflict staying visible without a click.",
    verdict:
      "B wins on the job you do most often: finding one stop inside a twenty-stop trip. Keeping only time, name and booking status loud, and demoting the rest to a chip row, is what makes a long day scan rather than read. A is the only option that makes travel time between stops feel real, which matters if that is what you keep getting wrong, but it spends 5rem of width on a rail that never holds a fact. C is the most pleasant end-to-end read and the worst for hunting, because every stop is compressed into one dense meta line. Choose B; the spine's travel legs can be folded into it later.",
  },
  "chat-agent-workspace": {
    axis:
      "All three run the same agent over the same trip. They disagree about what the Assistant costs the other panes while you are not talking to it.",
    rows: [
      {
        option: "A · Conversation dock",
        score: 65,
        idea: "A fourth permanent column beside Itinerary, Map, and Details.",
        buys: "Never reopened, never overlapping the plan.",
        costs: "About 22rem of workspace width, whether you are using it or not.",
        choose: "You converse continuously while planning.",
      },
      {
        option: "B · Focus composer",
        score: 76,
        idea: "A 4rem command line at rest; the transcript rises only when asked for.",
        buys: "Zero column cost when you are not talking.",
        costs: "The conversation is never side by side with the map.",
        choose: "You ask short questions occasionally.",
      },
      {
        option: "C · Turn thread",
        score: 83,
        idea: "The right rail becomes turn cards, each linked to the stops it changed.",
        buys: "An auditable trail that stays visible while you work the map.",
        costs: "Details loses its permanent rail to an on-demand overlay.",
        choose: "You need to see exactly what the agent changed, and when.",
      },
    ],
    same: "Itinerary, Map and Details content, the fixture trip, the agent's tools, and the SSE contract.",
    verdict:
      "C wins because it answers the question you ask after every agent turn - what exactly did that change - by binding each turn to the stops it touched. B costs nothing while you are silent and is right if the Assistant is an occasional question, but the conversation can never sit beside the map. A never has to be reopened and charges 22rem of workspace width for that, used or not. Take C and accept Details becoming an on-demand overlay; take B instead if you would rather give up the trail than the rail.",
  },
  "intercity-map": {
    axis:
      "All three show the same day with the same timing and place order. They disagree about whether the inter-city leg is real map geometry, fixed chrome above the map, or something you switch on.",
    rows: [
      {
        option: "A · Connected day journey",
        score: 85,
        idea: "Both city circuits and the leg between them share one canvas.",
        buys: "Every transfer endpoint stays real geometry, in itinerary order.",
        costs: "The destination circuit is smaller, because the frame must hold both cities.",
        choose: "You want one honest picture of a day that moves.",
      },
      {
        option: "B · Journey strip + local map",
        score: 64,
        idea: "The leg moves off the canvas into a pinned strip above it.",
        buys: "The map stays at the scale of the city you are actually in.",
        costs: "The origin circuit and terminals never appear as geometry at all.",
        choose: "The destination city is where the day's real work is.",
      },
      {
        option: "C · Optional inter-city layer",
        score: 71,
        idea: "Both scales render together, with independent visibility controls.",
        buys: "You choose what to see, and the leg stays real geometry either way.",
        costs: "Two more persistent controls on the map.",
        choose: "The right answer depends on the day.",
      },
    ],
    same: "Itinerary timing, hotel endpoints, route facts, place order, and provider routing.",
    verdict:
      "A wins because a day that moves between cities is one journey, and only A draws it as one: both circuits and the leg between them stay real geometry, in itinerary order. C keeps that same honesty and lets you choose the scale, which is genuinely better on some days, but it buys the choice with two more permanent map controls. B keeps the destination city at a comfortable zoom and pays by never showing the origin circuit or the terminals as geometry at all. Ship A; add C's layer toggles if the combined frame turns out to be too small too often.",
  },
  "multi-city-itinerary": {
    axis:
      "All three keep every event on a transition day and every fact on it. They disagree only about how that day is grouped, and therefore what the grouping makes prominent.",
    rows: [
      {
        option: "A · Transition spine",
        score: 84,
        idea: "One chronological chain: checkout, travel, arrival, check-in.",
        buys: "The handoff is auditable step by step, in true order.",
        costs: "Nothing is emphasised; it reads as one long timeline.",
        choose: "You want to verify the sequence rather than skim it.",
      },
      {
        option: "B · Stay handoff",
        score: 72,
        idea: "The old and new stays frame one prominent transfer object.",
        buys: "The change of base is the most visible thing on the day.",
        costs: "The rest of the day reads as context around that object.",
        choose: "Changing hotels is where transition days go wrong for you.",
      },
      {
        option: "C · City chapters",
        score: 66,
        idea: "Morning, Journey and Evening sections split the day by city context.",
        buys: "The change of destination is unmissable.",
        costs: "The continuous order is broken into three blocks.",
        choose: "The two halves of the day feel like two separate days.",
      },
    ],
    same: "Every event, every stop fact, and the order they occur in.",
    verdict:
      "A wins because a transition day is judged on whether the sequence is right - checkout, travel, arrival, check-in - and the chronological chain is the only one you can audit step by step. B makes the change of base the loudest thing on the day, which reads better if hotels are where these days go wrong for you, but it turns everything else into context. C is the clearest about changing city and the weakest about continuity, because it cuts one day into three blocks. A was implemented for exactly that reason: order is the thing that has to survive.",
  },
  "destination-guide": {
    axis:
      "All three draw on the same places and the same ratings. They disagree about how you travel from 'show me options' to the one place you actually add.",
    rows: [
      {
        option: "A · Contextual explorer",
        score: 83,
        idea: "Mixed trip highlights, narrowing to same-type alternatives once focused.",
        buys: "Relevant alternatives without leaving the stop you are questioning.",
        costs: "There is no single complete index to browse.",
        choose: "You are comparing against a stop you already have.",
      },
      {
        option: "B · City chapters",
        score: 66,
        idea: "One destination at a time, in Hotels, Attractions and Food sections.",
        buys: "The same predictable structure in every city.",
        costs: "Comparing across cities means switching chapters.",
        choose: "You plan a multi-city trip one city at a time.",
      },
      {
        option: "C · Filtered directory",
        score: 72,
        idea: "Search plus city and category filters over one dense index.",
        buys: "It can find anything, with the widest coverage on screen.",
        costs: "You have to know what to ask for.",
        choose: "You already know what you are looking for.",
      },
    ],
    same: "Place data, ratings, review counts, and the trip fixture behind them.",
    verdict:
      "A wins because browsing almost always starts from a stop you are already questioning, and it keeps you there while offering same-type alternatives. C can find anything and puts the widest coverage on screen, but only once you know what to ask for. B is the most predictable structure and the most awkward the moment you want to compare across cities. A was implemented with search added, which folds C's one real advantage into A's context.",
  },
  "account-settings": {
    axis:
      "All three expose exactly the same settings. They disagree about how many doors those settings have, and how far that arrangement scales.",
    rows: [
      {
        option: "A · Unified account menu",
        score: 82,
        idea: "One avatar owns identity, travel profile, analytics, privacy and sign-out.",
        buys: "One door, and no destination reachable two ways.",
        costs: "That single menu grows every time a setting is added.",
        choose: "The settings list is expected to stay small.",
      },
      {
        option: "B · Clear account/settings split",
        score: 70,
        idea: "Profile owns identity; Settings owns preferences, analytics and privacy.",
        buys: "Two familiar icons, with every duplicated destination removed.",
        costs: "You have to remember which icon holds which thing.",
        choose: "Preferences are expected to outgrow identity.",
      },
      {
        option: "C · Account settings hub",
        score: 65,
        idea: "One labelled command opens a larger, sectioned sheet.",
        buys: "The most room to grow without redesigning anything.",
        costs: "A heavier interaction than a popover, for small changes too.",
        choose: "Settings will keep expanding for a long time.",
      },
    ],
    same: "Which settings exist, and what each one does.",
    verdict:
      "A wins because the settings list is small, and one door means no destination is ever reachable two ways. B is the more scalable arrangement and the right move once preferences outgrow identity, but until then it makes you remember which of two icons holds a thing. C has the most room to grow and charges a full sheet for flipping one toggle. Take A now and treat B as the upgrade path rather than a competitor.",
  },
  "shell-visual-refresh": {
    axis:
      "All three expose the same workspace surfaces from the same top bar. They disagree about how much of the meaning is carried by an icon and how much by a word.",
    chosen: "A · Semantic icon + text",
    rows: [
      {
        option: "A · Semantic icon + text",
        score: 87,
        idea: "Every surface gets a meaning-first icon and a short label.",
        buys: "Unambiguous at a glance, with nothing depending on hover.",
        costs: "The widest command row of the three.",
        choose: "Clarity matters more than width.",
      },
      {
        option: "B · Compact control rail",
        score: 72,
        idea: "Persistent surfaces become icon buttons; commands keep text where it matters.",
        buys: "The narrowest row, and the most space left for the workspace.",
        costs: "Meaning depends on recognising the icon or hovering it.",
        choose: "Horizontal space is the scarce resource.",
      },
      {
        option: "C · Text-led command bar",
        score: 65,
        idea: "Surface names do the navigation; icons are reserved for unambiguous actions.",
        buys: "No icon can be misread.",
        costs: "It reads as a text menu, which scans more slowly.",
        choose: "The surfaces are named better than they can be drawn.",
      },
    ],
    same: "Which surfaces the bar exposes and what each one opens.",
    verdict:
      "A wins because a command bar is glanced at, not studied: an icon plus a word is unambiguous the first time and still fast the hundredth. B is narrower and leaves more room for the workspace, but the meaning moves into hover, which does not exist on touch. C cannot be misread and scans slowest, because text without shape gives the eye nothing to aim at. A was selected and applied to the desktop top command bar only.",
  },
  "workspace-command-bar": {
    axis:
      "All three toggle the same panes. They disagree about whether pane visibility is many direct switches, one mode control, or something you open a menu for.",
    chosen: "A · Direct pane toggles",
    rows: [
      {
        option: "A · Direct pane toggles",
        score: 85,
        idea: "One toggle per pane, always present.",
        buys: "The fastest path for someone who does this many times a day.",
        costs: "The most controls in the top row.",
        choose: "Repeated expert use is the case to optimise.",
      },
      {
        option: "B · Segmented view group",
        score: 78,
        idea: "Pane visibility reads as one coherent workspace mode.",
        buys: "The current layout is legible as a single state.",
        costs: "Changing one pane is less direct than a dedicated switch.",
        choose: "You think in layouts rather than in panes.",
      },
      {
        option: "C · Layout popover",
        score: 63,
        idea: "One Layout command opens visibility and focus together.",
        buys: "The calmest top row by a wide margin.",
        costs: "Every pane change begins by opening a menu.",
        choose: "Layout changes are rare.",
      },
    ],
    same: "Which panes exist, and the pane-local Hide and Maximize controls.",
    verdict:
      "A wins because pane visibility is toggled many times a day, and a direct switch is the shortest path on every one of those times. B reads the whole layout as one legible state, which is the nicer mental model, and makes changing a single pane less direct than it should be. C gives the calmest top row and puts a menu in front of every change. A was selected, leaving the pane-local controls untouched.",
  },
  "trip-snapshot-hierarchy": {
    axis:
      "All three have the same trip facts available. They disagree about how much the header should say before the itinerary is allowed to start.",
    chosen: "B · Decision brief",
    rows: [
      {
        option: "A · Scan ledger",
        score: 72,
        idea: "Dense facts in a stable left-to-right hierarchy.",
        buys: "The fastest repeat scan once you know where things sit.",
        costs: "No room for trip character or for guidance.",
        choose: "You already know what the numbers mean.",
      },
      {
        option: "B · Decision brief",
        score: 86,
        idea: "Identity, readiness, weather and budget form one planning brief.",
        buys: "Context plus a clear story about what still needs attention.",
        costs: "Taller than a pure ledger.",
        choose: "The header should tell you what to do next.",
      },
      {
        option: "C · Progressive summary",
        score: 66,
        idea: "Core identity stays compact; secondary context expands on demand.",
        buys: "The most itinerary space protected.",
        costs: "Important constraints can stay hidden behind a click.",
        choose: "Vertical space matters more than completeness.",
      },
    ],
    same: "Which trip facts are available to show.",
    verdict:
      "B wins because the header's job is to say what still needs attention, not only to print numbers. A scans fastest once you already know what every figure means, and leaves no room for that guidance. C protects the most itinerary space by hiding constraints behind a click, which is the one thing a header must never do. B was selected, with the duplicated Trip fit block removed.",
  },
  "map-controls": {
    axis:
      "All three offer the same map commands and the same route evidence. They disagree about how much of the pane those commands hold, and whether route evidence is standing or summoned.",
    chosen: "A · Unified route ribbon",
    rows: [
      {
        option: "A · Unified route ribbon",
        score: 86,
        idea: "Scope, Add stop and a structured route brief share two stable rows.",
        buys: "The fastest scan, with the fewest moving parts.",
        costs: "Two rows are always present, used or not.",
        choose: "Route evidence is something you check constantly.",
      },
      {
        option: "B · Contextual command deck",
        score: 71,
        idea: "A quiet primary bar opens focused drawers for adding and evidence.",
        buys: "The maximum map area whenever commands are idle.",
        costs: "Evidence has to be summoned before it can be read.",
        choose: "The map is mostly for looking, not for arranging.",
      },
      {
        option: "C · Schedule-first strip",
        score: 66,
        idea: "A bottom timeline makes day sequence and timing the dominant control.",
        buys: "The best day-to-day comparison and travel rhythm.",
        costs: "Bottom space, and commands move away from the top edge.",
        choose: "Timing, not geography, is what you are judging.",
      },
    ],
    same: "Which map commands exist and what route facts they can show.",
    verdict:
      "A wins because route evidence is checked constantly, and standing evidence beats summoned evidence for anything you look at that often. B gives the most map whenever the commands are idle, and a gesture every time they are not. C is the best way to compare days and timing, and moves the commands away from the top edge to get it. A was selected, changing only the Map command hierarchy.",
  },
  "pane-control-polish": {
    axis:
      "All three offer exactly two commands, Hide and Maximize. They disagree about how loudly a pane header should carry them.",
    chosen: "B · Restrained icon pair",
    rows: [
      {
        option: "A · Compact semantic actions",
        score: 73,
        idea: "Short icon-and-text actions state both commands outright.",
        buys: "Nothing has to be learned or hovered.",
        costs: "The most header width, repeated in every pane.",
        choose: "First-time clarity outweighs repetition.",
      },
      {
        option: "B · Restrained icon pair",
        score: 86,
        idea: "Two quiet icons in a light local group, with precise tooltips.",
        buys: "Readable without competing with the pane's content.",
        costs: "First use depends on a tooltip.",
        choose: "The commands are used often and learned quickly.",
      },
      {
        option: "C · Pane action menu",
        score: 62,
        idea: "One calm trigger reveals clearly labelled actions.",
        buys: "The quietest possible pane header.",
        costs: "Every hide or maximize costs an extra click.",
        choose: "Pane headers must stay almost invisible.",
      },
    ],
    same: "The two commands themselves and what they do.",
    verdict:
      "B wins because Hide and Maximize are learned in a day and then used constantly, so the header should carry them quietly rather than announce them. A never has to be learned and repeats its width in every pane header, forever. C is the quietest of the three and charges an extra click for a command you use all the time. B was selected and applied to the Itinerary, Map and Details pane headers.",
  },
  "itinerary-trip-book": {
    axis:
      "All three carry the same operational facts and the same appendix. They disagree about what the printed packet is optimised for, which shows up directly as page count.",
    rows: [
      {
        option: "A · Operations binder",
        score: 72,
        idea: "Checklist-led and as short as it can be. 14 pages.",
        buys: "The least to carry and the fastest to reprint.",
        costs: "Almost no context or reassurance around the facts.",
        choose: "The packet is a working document and nothing else.",
      },
      {
        option: "B · Layered Trip Book",
        score: 85,
        idea: "Trip control first, then day spreads, then evidence and documents. 18 pages.",
        buys: "Executable in the moment, with proof sitting behind it.",
        costs: "Four more pages than the binder.",
        choose: "You want one artefact that answers both kinds of question.",
      },
      {
        option: "C · Visual journey book",
        score: 67,
        idea: "Photography and destination context around the full appendix. 24 pages.",
        buys: "Something worth keeping after the trip ends.",
        costs: "The most pages, and the most printing.",
        choose: "The packet doubles as a keepsake.",
      },
    ],
    same: "Every operational fact, and the complete appendix behind all three.",
    verdict:
      "B wins because a printed packet gets asked two kinds of question - what now, and is this actually booked - and the layered book is the only one that answers both, for four pages more than the binder. A is the least to carry and the fastest to reprint, with almost nothing around the facts to reassure you. C is the one you would keep afterwards and the most to print. Take B; A is right only if the packet is purely operational.",
  },
  "itinerary-density": {
    axis:
      "All three keep every production detail and the exact endpoint behaviour. They disagree about how much vertical space hotel endpoints and per-stop detail are allowed to claim.",
    chosen: "B · Circuit header",
    rows: [
      {
        option: "A · One-line ledger",
        score: 70,
        idea: "Every circuit endpoint stays its own row.",
        buys: "The most detail visible at once, with nothing to open.",
        costs: "The most vertical space, spent on rows that repeat.",
        choose: "Nothing may ever be collapsed.",
      },
      {
        option: "B · Circuit header",
        score: 88,
        idea: "Hotel endpoints move into one truthful day-level circuit line.",
        buys: "Rows recovered without losing a single fact.",
        costs: "The endpoint becomes a line rather than a row you can act on.",
        choose: "The repetition, not the detail, is the problem.",
      },
      {
        option: "C · Progressive focus",
        score: 64,
        idea: "Rows stay quiet until one stop is selected and expands.",
        buys: "The calmest default view of a long day.",
        costs: "Booking and route detail require a selection first.",
        choose: "You work one stop at a time.",
      },
    ],
    same: "Every production detail on a stop, and exact endpoint behaviour.",
    verdict:
      "B wins because the problem was repetition, not detail: two identical hotel endpoints a day were spending rows to repeat something the day already knew. A keeps every row and therefore keeps the problem. C is the calmest default and makes booking and route facts wait for a selection. B was implemented, adapted so production detail and exact endpoint behaviour survived the consolidation.",
  },
  "chat-assistant-overlay": {
    axis:
      "All three keep the conversation mounted and continuous. They disagree about how much workspace it borrows while open, and how quickly you get that workspace back.",
    chosen: "B · Corner conversation sheet",
    rows: [
      {
        option: "A · Collapsible edge drawer",
        score: 76,
        idea: "A full-height right drawer over Details, collapsing to a slim rail. 420 px.",
        buys: "The most room for a long conversation.",
        costs: "Details is covered for as long as it is open.",
        choose: "Conversations are long and Details can wait.",
      },
      {
        option: "B · Corner conversation sheet",
        score: 85,
        idea: "A lower-right sheet over one corner, collapsing to a button. 480 px.",
        buys: "Most of the map and itinerary stay visible while you ask.",
        costs: "Less room for a transcript you want to read back.",
        choose: "You ask short follow-ups while comparing the map.",
      },
      {
        option: "C · Prompt popover + rail",
        score: 64,
        idea: "Only the active prompt opens beside a 48 px persistent rail.",
        buys: "The three panes keep the highest possible priority.",
        costs: "Completed planning recedes immediately.",
        choose: "The plan matters more than the conversation about it.",
      },
    ],
    same: "The mounted conversation, its history, and its continuity across opens.",
    verdict:
      "B wins because most Assistant use is a short follow-up asked while you are comparing the map, and a corner sheet leaves that comparison on screen. A has the most room for a long transcript and covers Details for as long as it stays open. C protects the three panes best and makes finished planning recede immediately. B was selected, preserving the mounted conversation and a usable workspace.",
  },
  "itinerary-row-design": {
    axis:
      "All three carry every stop fact. They disagree about what the eye follows down a day: the clock, the journey between places, or the places themselves.",
    chosen: "B · Compact agenda",
    rows: [
      {
        option: "A · Journey timeline",
        score: 66,
        idea: "Transport becomes the connector between destinations.",
        buys: "The movement between stops is explicit rather than implied.",
        costs: "Transport competes with the stops for attention.",
        choose: "Getting between places is the hard part of the day.",
      },
      {
        option: "B · Compact agenda",
        score: 85,
        idea: "Time-first rows, tuned for scanning and density.",
        buys: "The most stops legible at once.",
        costs: "The least guidance for someone reading it for the first time.",
        choose: "You know the trip and are looking for one row.",
      },
      {
        option: "C · Guided place cards",
        score: 71,
        idea: "Labelled sections put the place first.",
        buys: "The clearest read for first-time use.",
        costs: "The fewest stops on screen at any moment.",
        choose: "Clarity for a new reader outweighs density.",
      },
    ],
    same: "Every fact on every stop.",
    verdict:
      "B wins on density: time-first rows put the most stops on screen legibly, which is what matters once you know the trip and are hunting for one row. C is the clearest for a first read and shows the fewest stops at a time. A makes the movement between places explicit, and lets transport compete with the stops for attention. B was selected, paired with the Compact Brief summary above it.",
  },
  "itinerary-summary-design": {
    axis:
      "All three say the same thing about a day: its narrative, its journey line, and its booking readiness. They disagree about how much vertical space that is worth.",
    chosen: "C · Compact brief",
    rows: [
      {
        option: "A · Editorial brief",
        score: 65,
        idea: "A spacious narrative opening leads with the character of the day.",
        buys: "The strongest sense of what the day will feel like.",
        costs: "The most space before the first stop appears.",
        choose: "Tone is what the summary is for.",
      },
      {
        option: "B · Balanced brief",
        score: 76,
        idea: "Narrative first, then the journey line and readiness signals.",
        buys: "Story and logistics both present, in that order.",
        costs: "Still a tall header above every day.",
        choose: "Neither tone nor logistics should win outright.",
      },
      {
        option: "C · Compact brief",
        score: 86,
        idea: "The same narrative and logistics, in a denser header.",
        buys: "Identical facts for noticeably less space.",
        costs: "The least room for tone to breathe.",
        choose: "The agenda below is what people came for.",
      },
    ],
    same: "The narrative, the journey line, and the readiness facts.",
    verdict:
      "C wins because all three say the same things about a day, so the only live question is what that costs in vertical space above the agenda. B keeps story and logistics in a comfortable order and is still a tall header on every single day. A gives the strongest sense of the day's character and delays the first stop the longest. C was selected, with explicit travel rhythm, day plan and booking readiness.",
  },
  "workspace-shell": {
    axis:
      "All four surfaces exist in every layout. They disagree about which one is the persistent centre of the workspace, and which are demoted to a support lane.",
    chosen: "C · Spatial workspace",
    rows: [
      {
        option: "A · Map-first",
        score: 70,
        idea: "Map and Details stay persistent; Itinerary and Chat share a support column.",
        buys: "Geography is never more than a glance away.",
        costs: "The itinerary is demoted to a secondary lane.",
        choose: "The map is where planning actually happens.",
      },
      {
        option: "B · Story-first",
        score: 64,
        idea: "Itinerary becomes dominant, with Map and Chat in a secondary lane.",
        buys: "The plan itself leads, at full width.",
        costs: "The map stops being a working surface.",
        choose: "The plan is read far more than the geography.",
      },
      {
        option: "C · Spatial workspace",
        score: 88,
        idea: "Itinerary left, dominant Map centre, Details right, Assistant lower-right.",
        buys: "All four reachable at once, with nothing to switch between.",
        costs: "Every pane is narrower than it would be alone.",
        choose: "The four surfaces are used together, not in turns.",
      },
    ],
    same: "The four surfaces themselves and what each one is responsible for.",
    verdict:
      "C wins because the four surfaces are used together rather than in turns, and it is the only layout where none of them has to be switched to. A keeps geography permanent and demotes the plan to a support lane. B leads with the plan at full width and stops the map being a working surface. C was chosen: itinerary left, dominant map centre, details right, Assistant lower-right.",
  },
};

export function OptionContrast({ labId }: { labId: string }) {
  const contrast = contrasts[labId];
  const lab = allLabs.find((candidate) => candidate.id === labId);
  if (!contrast || !lab) return null;

  const ranked = [...contrast.rows].sort((a, b) => b.score - a.score);

  return (
    <section
      className="mt-5 overflow-hidden rounded-md bg-white shadow-card ring-1 ring-slate-200"
      aria-labelledby={`${labId}-contrast-title`}
    >
      <div className="border-b border-slate-100 px-4 py-3">
        <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-brand">
          <Columns2 size={12} aria-hidden /> Lab #{lab.labNumber} · The difference, in one place
        </p>
        <h2 id={`${labId}-contrast-title`} className="mt-0.5 text-sm font-semibold text-ink">
          What the options actually disagree about
        </h2>
        <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-500">{contrast.axis}</p>
        <p className="mt-1.5 max-w-4xl text-xs leading-relaxed text-slate-500">
          Ranked best first. The score is a 0-100 judgement of how well an option serves the job named above once its
          cost is subtracted. It ranks these options against each other and means nothing outside this Lab.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[48rem] text-left text-xs">
          <thead className="bg-slate-50 text-[10px] font-bold uppercase text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-2">Rank · Option</th>
              <th scope="col" className="px-4 py-2">The idea</th>
              <th scope="col" className="px-4 py-2">What it buys</th>
              <th scope="col" className="px-4 py-2">What it costs</th>
              <th scope="col" className="px-4 py-2">Choose it when</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((row, index) => (
              <tr key={row.option} className="border-t border-slate-100 align-top">
                <th scope="row" className="px-4 py-2.5 text-left font-semibold text-ink">
                  <span className="flex items-baseline gap-2">
                    <span className="text-[11px] font-bold text-slate-400">{index + 1}</span>
                    <span>{row.option}</span>
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ${index === 0 ? "bg-brand/10 text-brand-600 ring-brand/30" : "bg-slate-50 text-slate-600 ring-slate-200"}`}
                    >
                      {row.score}/100
                    </span>
                    {contrast.chosen === row.option ? (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-800 ring-1 ring-emerald-200">
                        Selected
                      </span>
                    ) : index === 0 ? (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-800 ring-1 ring-emerald-200">
                        Most recommended
                      </span>
                    ) : null}
                  </span>
                </th>
                <td className="px-4 py-2.5 leading-relaxed text-slate-700">{row.idea}</td>
                <td className="px-4 py-2.5 leading-relaxed text-emerald-800">{row.buys}</td>
                <td className="px-4 py-2.5 leading-relaxed text-rose-800">{row.costs}</td>
                <td className="px-4 py-2.5 leading-relaxed text-slate-600">{row.choose}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="border-t border-slate-100 px-4 py-3">
        <p className="text-[10px] font-bold uppercase text-brand">Reading the three against each other</p>
        <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">{contrast.verdict}</p>
      </div>
      <p className="border-t border-slate-100 bg-slate-50/60 px-4 py-2.5 text-xs leading-relaxed text-slate-600">
        <span className="font-semibold text-ink">Identical in every option:</span> {contrast.same} If it is not in the
        table above, it is not part of this choice.
      </p>
    </section>
  );
}
