# A Sleeker Itinerary Pane

Lab #31 compares seven look-and-feel directions for the itinerary pane. It is available at
`http://127.0.0.1:5175/lab-31-itinerary-pane-polish.html` while the UX Lab server is running.
Append `?option=<id>` (`flow`, `sections`, `crisp`, `timeline`, `warm`, `agenda`, `cards`) and optionally
`&view=compare` or `&view=today` to open a specific preview.

## Meta

- Owner: Munish Goyal
- Date started: 14-Sep-2026
- Status: Open
- Branch: `claude/itinerary-pane-polish-lab`
- Related: Lab #17 (itinerary canvas, Lisbon) asked a broader re-ranking question before the
  Lab #30 workspace refinement shipped; this Lab starts from today's production pane instead.

## Owner brief

The current pane is lengthy, dense and not easy to consume. The Lab targets UX, look and feel —
sleeker, more professional, more user friendly — with no compromise on functionality and no
loss of any fact shown today (ratings, must-visit score, text summaries, the travel-from-previous
leg and so on). Two options may make smaller compatibility changes to the look and feel of the
whole workspace so the itinerary blends in; none may make major layout changes.

## Shared fixture and baseline

Every option renders the same four-day Jaipur and Udaipur trip, typed against the production
client contracts (`Itinerary`, `TripOverview`, `TripVerification`). The fixture exercises every
branch the pane renders: a flight and arrival airport, a hotel circuit with a return row, a
transition day with Check out and Check in, inter-city road legs, estimated times, buffers and a
timing conflict, a concern, notes and insights, a stop the map could not pin, and a rainy day.

The **Today** view is the unmodified production `ItineraryPanel` fed that fixture, with its API
calls answered in-page, so the comparison is against the real component rather than a
re-drawing. Views: *In workspace* (1440 × 900 with pane width 340 px, 27%, 38%, 50% or maximized),
*Side by side with today* (two 400 px panes), and *Today only*. A *Plan checks* toggle switches
between gaps and a contradiction so Rearrange the trip can be exercised.

All derivations (timing labels, duration and leave text, map labels, hotel transition, notes and
insight de-duplication, arrival with buffer or conflict) live once in
`frontend/labs/src/itinerary-pane-polish/model.ts`, mirroring `ItineraryPanel.DayCard` and
`ItineraryStopRow`. Options change how a fact looks and where it sits, never what it says.

## Options

First round, ranked best first. Letters were assigned by rank in this round and are locked from round 2 on.

- **A · Crisp workspace harmony (92, pane + workspace).** Hairline list rows with line icons in
  place of emoji, bordered fact tags, a sticky day header with a 2 × 2 fact table, and a trip
  snapshot folded into Overview, Weather and Budget tabs. Workspace-wide: slightly cooler neutral
  tokens, one-line pane headers, day bar colour dots with an ink selection, flatter toolbar groups
  and matching Details tags.
- **B · Quiet timeline (90, pane only).** Time gutter plus a continuous day-coloured rail; each
  travel-from-previous leg is drawn as the rail segment between stops. Rating, must-visit, cost
  and hours share one quiet line. Weather, budget and trip needs fold behind one summary row.
- **C · Warm editorial harmony (85, pane + workspace).** Day covers tinted in the day's colour,
  serif titles, borderless rounded tiles, pill signals and dotted travel connectors; every trip
  fact stays visible at rest. Workspace-wide: serif one-line pane headers, softer pane radius and
  shadow, the notification strip as an inline pill, day bar colour dots.
- **D · Precise agenda (82, pane only).** Ledger rows (time block, content, status), a four-cell
  metric table per day, slim travel rows with a signed buffer or conflict badge, and one-line
  expandable rows for trip weather, needs and budget.
- **E · Clean stop cards (78, pane only).** Today's cards with labelled fact grids, a must-visit
  meter and connector pills; days are accordions, so the focused day is open and other days show
  only their header facts until expanded.

## Round 2: F and G (14-Sep-2026)

The owner preferred **A**, liked the pane-plus-workspace approach, and asked for two more
options built on A: slimmer rows, a clearer boundary when the day changes with a slightly larger
day title, rows that get shorter when the pane is wider because the information fits
horizontally, and more readable text, plus other improvements of the agent's choosing.

Letters are now locked (`lockLetters` in `OptionContrast.tsx`) so the new options are F and G
and A–E keep their names, while every list still renders best first.

Shared by F and G (`crisp2` workspace finish): A's snapshot, tags and chrome; darker secondary
text and borders (`.ipp-readable`); day-bar chips with date and booked/planned count; readiness
(`7/19 ready`) in the itinerary pane header; a shorter `To book` status; Notes & tips at the end
of the tag row instead of on its own line. Rows are CSS grids driven by container queries on the
pane (`.ippx-pane`), not the viewport: on a narrow pane only the name shares a line with the
status, and from about 600 px the signals, notes toggle and status join the stop's line.

- **F · Crisp flow rows (95).** Slim time gutter with the marker inline; a sticky day band with a
  3 px day-colour top rule, day tint, 16.5 px title and booking progress, and a gap before the
  next day; travel legs as one line whose arrival and spare time move right on a wide pane,
  coloured green, amber (under 5 min) or red (conflict); a Comfortable / Compact density switch.
- **G · Crisp day sections (93).** Each day a framed section with a colour bar, 17 px title and
  labelled stat tiles with a booking progress bar; a Jump to day strip; the travel leg folded into
  the arriving stop as a ↳ line; on a wide pane a table with column headings, a time-range column
  and zebra striping.

The pane-width control gained a 50% step so the reflow between narrow and maximized can be seen.

## Nothing removed

The page carries a fact matrix recording, for each production fact or control, whether each
option shows it at rest, one tap away, or on hover. No option removes anything. The only moves
from *visible* to *one tap* are trip weather/packing and budget (A, B, D, F, G), trip needs (B, D), and
stops of unfocused days (E). Notes and insights stay one tap away and Show on map / Remove stay
on hover, exactly as today.

`frontend/labs/src/itinerary-pane-polish/lab.test.ts` (node project, server rendering) enforces
this: every option must render the at-rest fact list, and weather and budget must be at rest
exactly where the matrix says. An interaction pass drove booking toggles, focus, notes, Add a day,
Rearrange the trip and filters in all five first-round options and the Today view with no console errors; round 2 repeated booking and density or jump-to-day checks for F and G.

## Evaluation notes

- The previews are production scale; the map and Details content are context-only stand-ins.
- Planner-side effects (add or reduce a day, rearrange, recheck prices and place facts) are
  simulated and reported in the *Last action* line; the Lab judges the controls, not the agent.
- Maximized width stretches each option's single column, as production does today; no option
  proposes a multi-column maximized layout.
- A saved selection authorizes only the declared scope; production implementation needs a
  separate handoff.

## Decision

Pending owner selection.
