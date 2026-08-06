import { Columns2 } from "lucide-react";
import { allLabs } from "./labRecords";

interface ContrastRow {
  option: string;
  idea: string;
  buys: string;
  costs: string;
  choose: string;
}

interface ContrastDefinition {
  /** The single sentence naming what the options genuinely disagree about. */
  axis: string;
  rows: ContrastRow[];
  /** What every option holds identical, so the table above is the whole difference. */
  same: string;
  /** Option label that was selected, for Labs that are already decided. */
  chosen?: string;
}

const contrasts: Record<string, ContrastDefinition> = {
  "travel-documents": {
    axis:
      "All three read a document once, keep the fields, and discard the file. They disagree about where the kept record lives, and whether you sort a document before or after you hand it over.",
    rows: [
      {
        option: "A · Trip readiness rail",
        idea: "The trip owns the whole subject, in its third pane.",
        buys: "One place to look, and nothing to manage anywhere else.",
        costs: "The Details pane, which is where you decide about a place.",
        choose: "Paperwork is the thing you open the trip to check.",
      },
      {
        option: "B · Account vault, trip shows gaps",
        idea: "Two homes for two lifetimes: passports are yours, references are the trip's.",
        buys: "The trip never turns into a document manager, and Details stays.",
        costs: "The answer is one click away instead of already on screen.",
        choose: "Most trips are already in order and only need a badge.",
      },
      {
        option: "C · Document inbox",
        idea: "Intake is separated from placement; items route themselves afterwards.",
        buys: "Six email attachments emptied in one gesture, triaged later.",
        costs: "A second queue that goes stale, and a trip that looks ready while it does.",
        choose: "Documents arrive in batches rather than one at a time.",
      },
    ],
    same: "The retention rule, the Lisbon fixture and its travellers, and every deterministic check.",
  },
  "agentic-planning": {
    axis:
      "All three give the agent the same typed operations and the same trip model. They disagree about where the stop-and-ask line sits, and how much of its reasoning is standing furniture.",
    rows: [
      {
        option: "A · Proposal first",
        idea: "Nothing is written until you apply it.",
        buys: "Zero silent damage, and the reasoning arrives before the change.",
        costs: "One extra interaction on every change that was always safe.",
        choose: "You do not yet trust the agent to write to the trip.",
      },
      {
        option: "B · Guarded autonomy",
        idea: "Safe edits land with an Undo receipt; dangerous ones hard-stop into a proposal.",
        buys: "Today's speed for ordinary edits, with the damaging class made impossible.",
        costs: "You are trusting the invariant list to be complete.",
        choose: "Most of your edits are routine and you want them to feel it.",
      },
      {
        option: "C · Plan console",
        idea: "A standing rail holds your declared rules, live invariants, and a revertible ledger.",
        buys: "A readable history and per-entry revert across a long editing life.",
        costs: "A permanent 20rem rail, even on a trip you never argue with.",
        choose: "You edit one trip repeatedly over weeks.",
      },
    ],
    same: "The trip data model, the agent's phases and tools, and the verdict every channel receives.",
  },
  "map-canvas": {
    axis:
      "All three keep the same route colours, marker numbers, and day identity. They disagree about how much of the pane is geography, and whether the map is also a route-planning surface.",
    rows: [
      {
        option: "A · Floating deck",
        idea: "The map runs edge to edge; controls float over it as glass cards.",
        buys: "The most map per pixel, and controls that feel weightless.",
        costs: "Floating cards can cover pins once the pane is narrow.",
        choose: "You mostly look at the map rather than edit from it.",
      },
      {
        option: "B · Route dock",
        idea: "A bottom dock carries day tabs, day facts, and the day's route timeline.",
        buys: "The map becomes a place to plan the sequence, not just see it.",
        costs: "About 7rem of the pane, permanently, at the bottom.",
        choose: "You work out the order of a day on the map itself.",
      },
      {
        option: "C · Command ribbon",
        idea: "Today's three stacked control rows collapse into one row and one fact ribbon.",
        buys: "The smallest change from today and the safest to ship.",
        costs: "The least new capability of the three.",
        choose: "Today's map is nearly right and only feels cluttered.",
      },
    ],
    same: "Google Maps behaviour, provider search, geocoding, and every trip mutation.",
  },
  "itinerary-canvas": {
    axis:
      "All three keep every one of the 31 production facts on a stop, a day, and the trip. They disagree about which handful of facts are always loud, and what carries your eye down a day.",
    rows: [
      {
        option: "A · Journey spine",
        idea: "One continuous time rail runs the whole trip, with travel legs on the line.",
        buys: "You feel the shape of a day, and the gaps between stops are visible.",
        costs: "About 5rem of horizontal space that never holds a fact.",
        choose: "Travel time between stops is what you most often get wrong.",
      },
      {
        option: "B · Layered stop cards",
        idea: "Time, name, and booking status are loud; everything else is a quiet chip row.",
        buys: "The fastest scan of a long day, with notes opening in place.",
        costs: "Notes and tips are one click away rather than always printed.",
        choose: "You scan a 20-stop trip looking for one stop.",
      },
      {
        option: "C · Editorial agenda",
        idea: "Morning, Afternoon and Evening chapters under Fraunces titles.",
        buys: "The most pleasant read from beginning to end.",
        costs: "The densest single meta line of facts per stop.",
        choose: "You read the plan far more often than you edit it.",
      },
    ],
    same: "All 31 facts, the 20-stop fixture, and the 16-minute ferry conflict staying visible without a click.",
  },
  "chat-agent-workspace": {
    axis:
      "All three run the same agent over the same trip. They disagree about what the Assistant costs the other panes while you are not talking to it.",
    rows: [
      {
        option: "A · Conversation dock",
        idea: "A fourth permanent column beside Itinerary, Map, and Details.",
        buys: "Never reopened, never overlapping the plan.",
        costs: "About 22rem of workspace width, whether you are using it or not.",
        choose: "You converse continuously while planning.",
      },
      {
        option: "B · Focus composer",
        idea: "A 4rem command line at rest; the transcript rises only when asked for.",
        buys: "Zero column cost when you are not talking.",
        costs: "The conversation is never side by side with the map.",
        choose: "You ask short questions occasionally.",
      },
      {
        option: "C · Turn thread",
        idea: "The right rail becomes turn cards, each linked to the stops it changed.",
        buys: "An auditable trail that stays visible while you work the map.",
        costs: "Details loses its permanent rail to an on-demand overlay.",
        choose: "You need to see exactly what the agent changed, and when.",
      },
    ],
    same: "Itinerary, Map and Details content, the fixture trip, the agent's tools, and the SSE contract.",
  },
  "intercity-map": {
    axis:
      "All three show the same day with the same timing and place order. They disagree about whether the inter-city leg is real map geometry, fixed chrome above the map, or something you switch on.",
    rows: [
      {
        option: "A · Connected day journey",
        idea: "Both city circuits and the leg between them share one canvas.",
        buys: "Every transfer endpoint stays real geometry, in itinerary order.",
        costs: "The destination circuit is smaller, because the frame must hold both cities.",
        choose: "You want one honest picture of a day that moves.",
      },
      {
        option: "B · Journey strip + local map",
        idea: "The leg moves off the canvas into a pinned strip above it.",
        buys: "The map stays at the scale of the city you are actually in.",
        costs: "The origin circuit and terminals never appear as geometry at all.",
        choose: "The destination city is where the day's real work is.",
      },
      {
        option: "C · Optional inter-city layer",
        idea: "Both scales render together, with independent visibility controls.",
        buys: "You choose what to see, and the leg stays real geometry either way.",
        costs: "Two more persistent controls on the map.",
        choose: "The right answer depends on the day.",
      },
    ],
    same: "Itinerary timing, hotel endpoints, route facts, place order, and provider routing.",
  },
  "multi-city-itinerary": {
    axis:
      "All three keep every event on a transition day and every fact on it. They disagree only about how that day is grouped, and therefore what the grouping makes prominent.",
    rows: [
      {
        option: "A · Transition spine",
        idea: "One chronological chain: checkout, travel, arrival, check-in.",
        buys: "The handoff is auditable step by step, in true order.",
        costs: "Nothing is emphasised; it reads as one long timeline.",
        choose: "You want to verify the sequence rather than skim it.",
      },
      {
        option: "B · Stay handoff",
        idea: "The old and new stays frame one prominent transfer object.",
        buys: "The change of base is the most visible thing on the day.",
        costs: "The rest of the day reads as context around that object.",
        choose: "Changing hotels is where transition days go wrong for you.",
      },
      {
        option: "C · City chapters",
        idea: "Morning, Journey and Evening sections split the day by city context.",
        buys: "The change of destination is unmissable.",
        costs: "The continuous order is broken into three blocks.",
        choose: "The two halves of the day feel like two separate days.",
      },
    ],
    same: "Every event, every stop fact, and the order they occur in.",
  },
  "destination-guide": {
    axis:
      "All three draw on the same places and the same ratings. They disagree about how you travel from 'show me options' to the one place you actually add.",
    rows: [
      {
        option: "A · Contextual explorer",
        idea: "Mixed trip highlights, narrowing to same-type alternatives once focused.",
        buys: "Relevant alternatives without leaving the stop you are questioning.",
        costs: "There is no single complete index to browse.",
        choose: "You are comparing against a stop you already have.",
      },
      {
        option: "B · City chapters",
        idea: "One destination at a time, in Hotels, Attractions and Food sections.",
        buys: "The same predictable structure in every city.",
        costs: "Comparing across cities means switching chapters.",
        choose: "You plan a multi-city trip one city at a time.",
      },
      {
        option: "C · Filtered directory",
        idea: "Search plus city and category filters over one dense index.",
        buys: "It can find anything, with the widest coverage on screen.",
        costs: "You have to know what to ask for.",
        choose: "You already know what you are looking for.",
      },
    ],
    same: "Place data, ratings, review counts, and the trip fixture behind them.",
  },
  "account-settings": {
    axis:
      "All three expose exactly the same settings. They disagree about how many doors those settings have, and how far that arrangement scales.",
    rows: [
      {
        option: "A · Unified account menu",
        idea: "One avatar owns identity, travel profile, analytics, privacy and sign-out.",
        buys: "One door, and no destination reachable two ways.",
        costs: "That single menu grows every time a setting is added.",
        choose: "The settings list is expected to stay small.",
      },
      {
        option: "B · Clear account/settings split",
        idea: "Profile owns identity; Settings owns preferences, analytics and privacy.",
        buys: "Two familiar icons, with every duplicated destination removed.",
        costs: "You have to remember which icon holds which thing.",
        choose: "Preferences are expected to outgrow identity.",
      },
      {
        option: "C · Account settings hub",
        idea: "One labelled command opens a larger, sectioned sheet.",
        buys: "The most room to grow without redesigning anything.",
        costs: "A heavier interaction than a popover, for small changes too.",
        choose: "Settings will keep expanding for a long time.",
      },
    ],
    same: "Which settings exist, and what each one does.",
  },
  "shell-visual-refresh": {
    axis:
      "All three expose the same workspace surfaces from the same top bar. They disagree about how much of the meaning is carried by an icon and how much by a word.",
    chosen: "A · Semantic icon + text",
    rows: [
      {
        option: "A · Semantic icon + text",
        idea: "Every surface gets a meaning-first icon and a short label.",
        buys: "Unambiguous at a glance, with nothing depending on hover.",
        costs: "The widest command row of the three.",
        choose: "Clarity matters more than width.",
      },
      {
        option: "B · Compact control rail",
        idea: "Persistent surfaces become icon buttons; commands keep text where it matters.",
        buys: "The narrowest row, and the most space left for the workspace.",
        costs: "Meaning depends on recognising the icon or hovering it.",
        choose: "Horizontal space is the scarce resource.",
      },
      {
        option: "C · Text-led command bar",
        idea: "Surface names do the navigation; icons are reserved for unambiguous actions.",
        buys: "No icon can be misread.",
        costs: "It reads as a text menu, which scans more slowly.",
        choose: "The surfaces are named better than they can be drawn.",
      },
    ],
    same: "Which surfaces the bar exposes and what each one opens.",
  },
  "workspace-command-bar": {
    axis:
      "All three toggle the same panes. They disagree about whether pane visibility is many direct switches, one mode control, or something you open a menu for.",
    chosen: "A · Direct pane toggles",
    rows: [
      {
        option: "A · Direct pane toggles",
        idea: "One toggle per pane, always present.",
        buys: "The fastest path for someone who does this many times a day.",
        costs: "The most controls in the top row.",
        choose: "Repeated expert use is the case to optimise.",
      },
      {
        option: "B · Segmented view group",
        idea: "Pane visibility reads as one coherent workspace mode.",
        buys: "The current layout is legible as a single state.",
        costs: "Changing one pane is less direct than a dedicated switch.",
        choose: "You think in layouts rather than in panes.",
      },
      {
        option: "C · Layout popover",
        idea: "One Layout command opens visibility and focus together.",
        buys: "The calmest top row by a wide margin.",
        costs: "Every pane change begins by opening a menu.",
        choose: "Layout changes are rare.",
      },
    ],
    same: "Which panes exist, and the pane-local Hide and Maximize controls.",
  },
  "trip-snapshot-hierarchy": {
    axis:
      "All three have the same trip facts available. They disagree about how much the header should say before the itinerary is allowed to start.",
    chosen: "B · Decision brief",
    rows: [
      {
        option: "A · Scan ledger",
        idea: "Dense facts in a stable left-to-right hierarchy.",
        buys: "The fastest repeat scan once you know where things sit.",
        costs: "No room for trip character or for guidance.",
        choose: "You already know what the numbers mean.",
      },
      {
        option: "B · Decision brief",
        idea: "Identity, readiness, weather and budget form one planning brief.",
        buys: "Context plus a clear story about what still needs attention.",
        costs: "Taller than a pure ledger.",
        choose: "The header should tell you what to do next.",
      },
      {
        option: "C · Progressive summary",
        idea: "Core identity stays compact; secondary context expands on demand.",
        buys: "The most itinerary space protected.",
        costs: "Important constraints can stay hidden behind a click.",
        choose: "Vertical space matters more than completeness.",
      },
    ],
    same: "Which trip facts are available to show.",
  },
  "map-controls": {
    axis:
      "All three offer the same map commands and the same route evidence. They disagree about how much of the pane those commands hold, and whether route evidence is standing or summoned.",
    chosen: "A · Unified route ribbon",
    rows: [
      {
        option: "A · Unified route ribbon",
        idea: "Scope, Add stop and a structured route brief share two stable rows.",
        buys: "The fastest scan, with the fewest moving parts.",
        costs: "Two rows are always present, used or not.",
        choose: "Route evidence is something you check constantly.",
      },
      {
        option: "B · Contextual command deck",
        idea: "A quiet primary bar opens focused drawers for adding and evidence.",
        buys: "The maximum map area whenever commands are idle.",
        costs: "Evidence has to be summoned before it can be read.",
        choose: "The map is mostly for looking, not for arranging.",
      },
      {
        option: "C · Schedule-first strip",
        idea: "A bottom timeline makes day sequence and timing the dominant control.",
        buys: "The best day-to-day comparison and travel rhythm.",
        costs: "Bottom space, and commands move away from the top edge.",
        choose: "Timing, not geography, is what you are judging.",
      },
    ],
    same: "Which map commands exist and what route facts they can show.",
  },
  "pane-control-polish": {
    axis:
      "All three offer exactly two commands, Hide and Maximize. They disagree about how loudly a pane header should carry them.",
    chosen: "B · Restrained icon pair",
    rows: [
      {
        option: "A · Compact semantic actions",
        idea: "Short icon-and-text actions state both commands outright.",
        buys: "Nothing has to be learned or hovered.",
        costs: "The most header width, repeated in every pane.",
        choose: "First-time clarity outweighs repetition.",
      },
      {
        option: "B · Restrained icon pair",
        idea: "Two quiet icons in a light local group, with precise tooltips.",
        buys: "Readable without competing with the pane's content.",
        costs: "First use depends on a tooltip.",
        choose: "The commands are used often and learned quickly.",
      },
      {
        option: "C · Pane action menu",
        idea: "One calm trigger reveals clearly labelled actions.",
        buys: "The quietest possible pane header.",
        costs: "Every hide or maximize costs an extra click.",
        choose: "Pane headers must stay almost invisible.",
      },
    ],
    same: "The two commands themselves and what they do.",
  },
  "itinerary-trip-book": {
    axis:
      "All three carry the same operational facts and the same appendix. They disagree about what the printed packet is optimised for, which shows up directly as page count.",
    rows: [
      {
        option: "A · Operations binder",
        idea: "Checklist-led and as short as it can be. 14 pages.",
        buys: "The least to carry and the fastest to reprint.",
        costs: "Almost no context or reassurance around the facts.",
        choose: "The packet is a working document and nothing else.",
      },
      {
        option: "B · Layered Trip Book",
        idea: "Trip control first, then day spreads, then evidence and documents. 18 pages.",
        buys: "Executable in the moment, with proof sitting behind it.",
        costs: "Four more pages than the binder.",
        choose: "You want one artefact that answers both kinds of question.",
      },
      {
        option: "C · Visual journey book",
        idea: "Photography and destination context around the full appendix. 24 pages.",
        buys: "Something worth keeping after the trip ends.",
        costs: "The most pages, and the most printing.",
        choose: "The packet doubles as a keepsake.",
      },
    ],
    same: "Every operational fact, and the complete appendix behind all three.",
  },
  "itinerary-density": {
    axis:
      "All three keep every production detail and the exact endpoint behaviour. They disagree about how much vertical space hotel endpoints and per-stop detail are allowed to claim.",
    chosen: "B · Circuit header",
    rows: [
      {
        option: "A · One-line ledger",
        idea: "Every circuit endpoint stays its own row.",
        buys: "The most detail visible at once, with nothing to open.",
        costs: "The most vertical space, spent on rows that repeat.",
        choose: "Nothing may ever be collapsed.",
      },
      {
        option: "B · Circuit header",
        idea: "Hotel endpoints move into one truthful day-level circuit line.",
        buys: "Rows recovered without losing a single fact.",
        costs: "The endpoint becomes a line rather than a row you can act on.",
        choose: "The repetition, not the detail, is the problem.",
      },
      {
        option: "C · Progressive focus",
        idea: "Rows stay quiet until one stop is selected and expands.",
        buys: "The calmest default view of a long day.",
        costs: "Booking and route detail require a selection first.",
        choose: "You work one stop at a time.",
      },
    ],
    same: "Every production detail on a stop, and exact endpoint behaviour.",
  },
  "chat-assistant-overlay": {
    axis:
      "All three keep the conversation mounted and continuous. They disagree about how much workspace it borrows while open, and how quickly you get that workspace back.",
    chosen: "B · Corner conversation sheet",
    rows: [
      {
        option: "A · Collapsible edge drawer",
        idea: "A full-height right drawer over Details, collapsing to a slim rail. 420 px.",
        buys: "The most room for a long conversation.",
        costs: "Details is covered for as long as it is open.",
        choose: "Conversations are long and Details can wait.",
      },
      {
        option: "B · Corner conversation sheet",
        idea: "A lower-right sheet over one corner, collapsing to a button. 480 px.",
        buys: "Most of the map and itinerary stay visible while you ask.",
        costs: "Less room for a transcript you want to read back.",
        choose: "You ask short follow-ups while comparing the map.",
      },
      {
        option: "C · Prompt popover + rail",
        idea: "Only the active prompt opens beside a 48 px persistent rail.",
        buys: "The three panes keep the highest possible priority.",
        costs: "Completed planning recedes immediately.",
        choose: "The plan matters more than the conversation about it.",
      },
    ],
    same: "The mounted conversation, its history, and its continuity across opens.",
  },
  "itinerary-row-design": {
    axis:
      "All three carry every stop fact. They disagree about what the eye follows down a day: the clock, the journey between places, or the places themselves.",
    chosen: "B · Compact agenda",
    rows: [
      {
        option: "A · Journey timeline",
        idea: "Transport becomes the connector between destinations.",
        buys: "The movement between stops is explicit rather than implied.",
        costs: "Transport competes with the stops for attention.",
        choose: "Getting between places is the hard part of the day.",
      },
      {
        option: "B · Compact agenda",
        idea: "Time-first rows, tuned for scanning and density.",
        buys: "The most stops legible at once.",
        costs: "The least guidance for someone reading it for the first time.",
        choose: "You know the trip and are looking for one row.",
      },
      {
        option: "C · Guided place cards",
        idea: "Labelled sections put the place first.",
        buys: "The clearest read for first-time use.",
        costs: "The fewest stops on screen at any moment.",
        choose: "Clarity for a new reader outweighs density.",
      },
    ],
    same: "Every fact on every stop.",
  },
  "itinerary-summary-design": {
    axis:
      "All three say the same thing about a day: its narrative, its journey line, and its booking readiness. They disagree about how much vertical space that is worth.",
    chosen: "C · Compact brief",
    rows: [
      {
        option: "A · Editorial brief",
        idea: "A spacious narrative opening leads with the character of the day.",
        buys: "The strongest sense of what the day will feel like.",
        costs: "The most space before the first stop appears.",
        choose: "Tone is what the summary is for.",
      },
      {
        option: "B · Balanced brief",
        idea: "Narrative first, then the journey line and readiness signals.",
        buys: "Story and logistics both present, in that order.",
        costs: "Still a tall header above every day.",
        choose: "Neither tone nor logistics should win outright.",
      },
      {
        option: "C · Compact brief",
        idea: "The same narrative and logistics, in a denser header.",
        buys: "Identical facts for noticeably less space.",
        costs: "The least room for tone to breathe.",
        choose: "The agenda below is what people came for.",
      },
    ],
    same: "The narrative, the journey line, and the readiness facts.",
  },
  "workspace-shell": {
    axis:
      "All four surfaces exist in every layout. They disagree about which one is the persistent centre of the workspace, and which are demoted to a support lane.",
    chosen: "C · Spatial workspace",
    rows: [
      {
        option: "A · Map-first",
        idea: "Map and Details stay persistent; Itinerary and Chat share a support column.",
        buys: "Geography is never more than a glance away.",
        costs: "The itinerary is demoted to a secondary lane.",
        choose: "The map is where planning actually happens.",
      },
      {
        option: "B · Story-first",
        idea: "Itinerary becomes dominant, with Map and Chat in a secondary lane.",
        buys: "The plan itself leads, at full width.",
        costs: "The map stops being a working surface.",
        choose: "The plan is read far more than the geography.",
      },
      {
        option: "C · Spatial workspace",
        idea: "Itinerary left, dominant Map centre, Details right, Assistant lower-right.",
        buys: "All four reachable at once, with nothing to switch between.",
        costs: "Every pane is narrower than it would be alone.",
        choose: "The four surfaces are used together, not in turns.",
      },
    ],
    same: "The four surfaces themselves and what each one is responsible for.",
  },
};

export function OptionContrast({ labId }: { labId: string }) {
  const contrast = contrasts[labId];
  const lab = allLabs.find((candidate) => candidate.id === labId);
  if (!contrast || !lab) return null;

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
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[46rem] text-left text-xs">
          <thead className="bg-slate-50 text-[10px] font-bold uppercase text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-2">Option</th>
              <th scope="col" className="px-4 py-2">The idea</th>
              <th scope="col" className="px-4 py-2">What it buys</th>
              <th scope="col" className="px-4 py-2">What it costs</th>
              <th scope="col" className="px-4 py-2">Choose it when</th>
            </tr>
          </thead>
          <tbody>
            {contrast.rows.map((row) => (
              <tr key={row.option} className="border-t border-slate-100 align-top">
                <th scope="row" className="px-4 py-2.5 text-left font-semibold text-ink">
                  {row.option}
                  {contrast.chosen === row.option ? (
                    <span className="mt-1 block w-fit rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-800 ring-1 ring-emerald-200">
                      Selected
                    </span>
                  ) : null}
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
      <p className="border-t border-slate-100 bg-slate-50/60 px-4 py-2.5 text-xs leading-relaxed text-slate-600">
        <span className="font-semibold text-ink">Identical in every option:</span> {contrast.same} If it is not in the
        table above, it is not part of this choice.
      </p>
    </section>
  );
}
