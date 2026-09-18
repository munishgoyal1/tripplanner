import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, ExternalLink, LockKeyhole, RefreshCw } from "lucide-react";
import { bookingCommand, bookingJsonUrl, fetchBookings, shareBookings,
  type Actual, type BookingResult, type BookingRow, type BookingView, type Category,
  type Choice, type Command, type Search } from "../bookingApi";
import ExportModal from "./ExportModal";

const categories: Category[] = ["flights", "hotels", "tickets", "transport"];
const money = (row: Pick<Choice, "currency" | "amount">) =>
  row.amount == null ? "Price unknown" : `${row.currency} ${row.amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
const dateLine = (row: Choice) => [row.start_date, row.end_date && `to ${row.end_date}`, row.time].filter(Boolean).join(" ");
const label = (key: string) => key.replaceAll("_", " ").replace(/([a-z])([A-Z])/g, "$1 $2");
function describe(value: unknown): string {
  if (value == null || value === "") return "Unknown";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.map(describe).join("; ") : "None recorded";
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${label(key)}: ${describe(item)}`).join(" · ");
  return String(value);
}

function Facts({ choice }: { choice: Choice }) {
  return <div className="space-y-1 text-sm text-muted">
    <p>{dateLine(choice) || "Dates need confirmation"}</p>
    <p>{choice.provider || "Provider unverified"} · Checked {choice.checked_at || "unknown"}</p>
    <p>{choice.expires_at ? `Offer expires ${choice.expires_at}` : "Availability must be rechecked"}</p>
    {!choice.complete_cost && <p className="text-amber-800">Mandatory fees and inclusions are not fully verified.</p>}
    {choice.context_warning && <p className="text-amber-800">{choice.context_warning}</p>}
    {Object.entries(choice.details).map(([key, value]) => <p key={key} className="break-words">
      <strong className="font-medium">{label(key)}: </strong>{describe(value)}
    </p>)}
  </div>;
}

function ReportForm({ row, disabled, onPreview, intent = false }: {
  row: BookingRow; disabled: boolean; onPreview: (command: Command) => void; intent?: boolean;
}) {
  const [actual, setActual] = useState<Actual>(row.actual || {
    product: row.name, provider: intent ? row.provider : "", amount: intent ? row.amount : null, currency: row.currency || "INR",
    start_date: row.start_date, end_date: row.end_date, time: row.time,
    reference: "", notes: intent ? String(row.details.booking_variant || "") : "", url: row.url,
  });
  const change = (key: keyof Actual, value: string) =>
    setActual((previous) => ({ ...previous, [key]: key === "amount" ? (value === "" ? null : Number(value)) : value }));
  return <form className="mt-4 grid gap-3 rounded-xl bg-sand p-4 sm:grid-cols-2"
    onSubmit={(event) => { event.preventDefault(); onPreview({ action: intent ? "manual" : "report", item_id: row.id, actual }); }}>
    <p className="text-sm text-muted sm:col-span-2">{intent ? "Save your researched product, ticket variant, slot and provider link as an unverified intention. This does not mark it booked." : "Record what you booked through any provider, an agent or offline. Leave an unknown amount blank. Your original intention is retained."}</p>
    {(["product", "provider", "amount", "currency", "start_date", "end_date", "time", "reference", "notes", "url"] as const).filter((key) => !intent || key !== "reference").map((key) =>
      <label key={key} className="text-sm font-medium">
        {({ product: intent ? "Intended product" : "Booked product", provider: intent ? "Suggested provider" : "Booked through / offline", amount: intent ? "Researched total amount" : "Actual paid amount",
          currency: "Currency (ISO)", start_date: "Start date", end_date: "End date", time: "Local time",
          reference: "Confirmation reference (private)", notes: intent ? "Variant, slot and inclusions" : "Private notes", url: "Provider link (HTTPS)" })[key]}
        <input className="input mt-1 w-full" type={key === "amount" ? "number" : key.includes("date") ? "date" : key === "time" ? "time" : "text"}
          required={["product", "provider", "currency"].includes(key)} min={key === "amount" ? 0 : undefined}
          step={key === "amount" ? "0.01" : undefined} maxLength={key === "currency" ? 3 : key === "notes" ? 500 : key === "url" ? 2048 : 180}
          value={actual[key] ?? ""} onChange={(event) => change(key, key === "currency" ? event.target.value.toUpperCase() : event.target.value)} />
      </label>)}
    <button disabled={disabled} className="btn-primary sm:col-span-2">{intent ? "Preview intent details" : "Preview booking update"}</button>
  </form>;
}

function ResearchForm({ view, disabled, onSearch }: {
  view: BookingView; disabled: boolean; onSearch: (command: Command) => void;
}) {
  const initialCategory = view.rows.some((row) => row.category === "hotels") ? "hotels" : "flights";
  const fallback = (category: Search["category"]): Search => {
    const row = view.rows.find((item) => item.category === category);
    return { category, origin: String(row?.details.from || ""), destination: view.destination,
      start_date: row?.start_date || "", end_date: row?.end_date || "", adults: 1, rooms: 1,
      children: 0, infants: 0, children_ages: [], currency: row?.currency || "INR",
      nationality: "", cabin: "ECONOMY", refundable_only: false };
  };
  const initial = view.research_defaults?.[initialCategory]?.[0];
  const [query, setQuery] = useState<Search>(initial?.search || fallback(initialCategory));
  const [targetId, setTargetId] = useState(initial?.id || "");
  const [assumptions, setAssumptions] = useState(initial?.assumptions || ["Saved search context is unavailable. Confirm all party and date fields."]);
  const [ages, setAges] = useState((initial?.search.children_ages || []).join(", "));
  const [formError, setFormError] = useState("");
  const selectTarget = (category: Search["category"], id?: string) => {
    const targets = view.research_defaults?.[category] || [];
    const target = targets.find((item) => item.id === id) || targets[0];
    setQuery(target?.search || fallback(category));
    setTargetId(target?.id || "");
    setAges((target?.search.children_ages || []).join(", "));
    setAssumptions(target?.assumptions || ["Confirm the party and dates for this search."]);
    setFormError("");
  };
  return <details className="rounded-2xl border border-border bg-paper p-5">
    <summary className="cursor-pointer font-semibold">Research / recheck flights and hotels</summary>
    <form className="mt-4 grid gap-3 sm:grid-cols-3" onSubmit={(event) => {
      event.preventDefault();
      const childAges = ages.trim() ? ages.split(",").map((age) => Number(age.trim())) : [];
      if (query.category === "hotels" && (childAges.length !== query.children + query.infants
        || childAges.some((age) => !Number.isInteger(age) || age < 0 || age > 17))) {
        setFormError("Enter one whole-year age (0–17) for every child and infant."); return;
      }
      setFormError(""); onSearch({ action: "research", search: {
        ...query, children_ages: childAges,
      } });
    }}>
      <p className="text-sm text-muted sm:col-span-3">Saved trip party and selected journey/stay dates are prefilled. Research does not book or replace your selections.</p>
      {assumptions.map((note) => <p key={note} className="text-sm text-amber-800 sm:col-span-3">{note}</p>)}
      {formError && <p role="alert" className="text-sm text-red-700 sm:col-span-3">{formError}</p>}
      <label>Category<select className="input w-full" value={query.category} onChange={(e) => selectTarget(e.target.value as Search["category"])}><option value="flights">Flights</option><option value="hotels">Hotels</option></select></label>
      {(view.research_defaults?.[query.category]?.length || 0) > 0 && <label>Saved journey or stay<select className="input w-full" value={targetId} onChange={(e) => selectTarget(query.category, e.target.value)}>
        {view.research_defaults?.[query.category].map((target) => <option key={target.id} value={target.id}>{target.label} · {target.search.start_date} → {target.search.end_date}</option>)}
      </select></label>}
      {(["origin", "destination", "start_date", "end_date", "adults", "rooms", "children", "infants", "currency", "nationality"] as const).map((key) =>
        <label key={key} className="text-sm capitalize">{key === "adults" && query.category === "hotels" ? "Adults per room" : key.replaceAll("_", " ")}
          <input className="input mt-1 w-full" type={key.includes("date") ? "date" : typeof query[key] === "number" ? "number" : "text"}
            min={["children", "infants"].includes(key) ? 0 : 1} max={9}
            required={["destination", "start_date"].includes(key) || (query.category === "hotels" && ["end_date", "nationality"].includes(key))} value={query[key]}
            onChange={(e) => setQuery({ ...query, [key]: typeof query[key] === "number" ? Number(e.target.value) : ["currency", "nationality"].includes(key) ? e.target.value.toUpperCase() : e.target.value })} />
        </label>)}
      {query.category === "flights" ? <label>Cabin<select className="input w-full" value={query.cabin} onChange={(e) => setQuery({ ...query, cabin: e.target.value })}>
        {["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"].map((c) => <option key={c}>{c}</option>)}
      </select></label> : <>
        <label>Child ages, comma-separated<input className="input w-full" value={ages} onChange={(e) => setAges(e.target.value)} /></label>
        <label><input type="checkbox" checked={query.refundable_only} onChange={(e) => setQuery({ ...query, refundable_only: e.target.checked })} /> Refundable only</label>
      </>}
      <button disabled={disabled} className="btn-primary sm:col-span-3"><RefreshCw size={15} /> Research exact options</button>
    </form>
  </details>;
}

export default function BookingPage() {
  const [view, setView] = useState<BookingView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [preview, setPreview] = useState<{ command: Command; result: BookingResult; base: BookingView } | null>(null);
  const [reportId, setReportId] = useState("");
  const [intentId, setIntentId] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState("");
  const [researchResult, setResearchResult] = useState("");
  const previewHeading = useRef<HTMLHeadingElement>(null);
  const reload = async () => {
    setBusy(true); setError(""); setPreview(null);
    try { setView(await fetchBookings(view?.trip_id || new URLSearchParams(location.search).get("trip_id") || "")); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => {
    const controller = new AbortController();
    fetchBookings(new URLSearchParams(location.search).get("trip_id") || "", controller.signal).then(setView)
      .catch((e: Error) => { if (e.name !== "AbortError") setError(e.message); });
    return () => controller.abort();
  }, []);
  useEffect(() => { if (preview) previewHeading.current?.focus(); }, [preview]);
  const run = async (command: Command) => {
    if (!view || busy) return;
    setBusy(true); setError(""); setStatus(""); setPreview(null);
    try {
      const result = await bookingCommand(view, command);
      if (command.action === "research") {
        setView(result.bookings); setResearchResult(result.research_result || ""); setStatus(result.message);
      } else setPreview({ command, result, base: view });
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const apply = async () => {
    if (!preview || busy) return;
    setBusy(true); setError("");
    try {
      const result = await bookingCommand(preview.base, preview.command, preview.result.preview_token);
      setView(result.bookings); setPreview(null); setReportId(""); setIntentId(""); setStatus(result.message);
    } catch (e) { setError((e as Error).message); setPreview(null); } finally { setBusy(false); }
  };
  const share = async () => {
    if (!view) return;
    setBusy(true); setError("");
    try {
      const url = await shareBookings(view); setShareUrl(url);
      try { await navigator.clipboard.writeText(url); setStatus("Read-only booking intent link copied."); }
      catch { setStatus("Your read-only link is ready below."); }
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <main className="product-theme-aegean min-h-screen bg-sand text-ink">
    <header className="sticky top-0 z-10 border-b border-border bg-paper px-4 py-3">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
        <a href="/planner" className="btn-ghost"><ArrowLeft size={16} /> Back to itinerary</a>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" disabled={busy} onClick={() => void reload()}>Reload saved plan</button>
          <button className="btn-primary" disabled={!view || busy} onClick={() => setExportOpen(true)}>Export booking intent list</button>
          <button className="btn-ghost" disabled={!view || busy} onClick={() => void share()}>Share list</button>
        </div>
      </div>
    </header>
    <div className="mx-auto max-w-6xl space-y-5 p-4 sm:p-7">
      <div><p className="text-sm font-semibold uppercase tracking-wide text-brand">Your final choices</p>
        <h1 className="display mt-1 text-3xl">Bookings{view?.destination ? ` · ${view.destination}` : ""}</h1>
        <p className="mt-2 max-w-3xl text-muted">Compare the research, adjust your choices and save what you intend to book. Complete purchases elsewhere, then record what you booked here.</p>
      </div>
      {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">{error}</p>}
      {status && <p role="status" className="rounded-xl bg-white p-3">{status}</p>}
      {shareUrl && <a className="block break-all text-brand underline" href={shareUrl} target="_blank" rel="noopener noreferrer">{shareUrl}</a>}
      {!view && !error && <p role="status">Loading saved choices…</p>}
      {view && <>
        <div className="flex flex-wrap gap-5 rounded-2xl bg-paper p-5 text-sm">
          <span><strong>{view.rows.length}</strong> purchase items</span>
          <span><strong>{view.locked_count}</strong> locked intentions</span>
          <span><strong>{view.booked_count}</strong> reported / marked booked</span>
          <span>Party: {String(view.travelers) || "Confirm travelers"}</span>
          <p className="w-full text-muted">{view.coverage} Locks do not hold prices or inventory.</p>
        </div>
        <form key={view.updated_at} className="rounded-2xl border border-border bg-paper p-5" onSubmit={(event) => {
          event.preventDefault(); const data = new FormData(event.currentTarget);
          const caps: Command["caps"] = {};
          for (const category of categories) {
            const amount = String(data.get(category) || "");
            if (amount !== "") caps[category] = { amount: Number(amount), currency: String(data.get(`${category}-currency`) || "INR").toUpperCase() };
          }
          void run({ action: "caps", caps });
        }}>
          <h2 className="font-semibold">Category budgets · whole party, all nights</h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{categories.map((category) =>
            <div key={category}><label className="text-sm capitalize">{category} cap
              <input className="input mt-1 w-full" name={category} type="number" min="0" step="0.01" defaultValue={view.category_caps[category]?.amount ?? ""} placeholder="No cap" />
            </label><label className="mt-1 block text-xs">Currency<input className="input w-full" name={`${category}-currency`} maxLength={3} pattern="[A-Za-z]{3}" defaultValue={view.category_caps[category]?.currency || "INR"} /></label>
            {view.budgets[category] && <p className="mt-1 text-xs">{view.budgets[category]?.known_total.toLocaleString()} known · {view.budgets[category]?.status.replaceAll("_", " ")}
              {Boolean(view.budgets[category]?.unknown_items) && " · unpriced or different-currency items"}</p>}</div>)}</div>
          <button disabled={busy} className="btn-ghost mt-3">Preview budget changes</button>
        </form>
        <ResearchForm view={view} disabled={busy} onSearch={(command) => void run(command)} />
        {researchResult && <p role="status" className="rounded-xl bg-paper p-4 text-sm">{researchResult}</p>}
        {preview && <section aria-label="Adjustment preview" className="rounded-2xl border-2 border-brand bg-white p-5">
          <h2 ref={previewHeading} tabIndex={-1} className="text-xl font-semibold">Review before saving</h2>
          <p className="mt-2">Action: {preview.command.action}. Nothing has been saved yet.</p>
          {preview.result.warnings?.map((warning) => <p key={warning} className="mt-2 text-sm text-amber-800">{warning}</p>)}
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            {([["Before", preview.base], ["After", preview.result.bookings]] as const).map(([label, state]) =>
              <div key={label}><h3 className="font-semibold">{label}</h3>
                {state.rows.filter((row) => !preview.command.item_id || row.id === preview.command.item_id).map((row) =>
                  <div key={row.id} className="mt-2 space-y-1 text-sm"><p>{row.name} · {money(row)} · {dateLine(row)} · {row.intent_state}{row.booked ? " · booked" : ""} · {row.disposition.replaceAll("_", " ")}</p>
                    <Facts choice={row} />
                    {row.actual && <p>Reported through {row.actual.provider}{row.actual.reference ? ` · Private reference: ${row.actual.reference}` : ""}{row.actual.notes ? ` · Private notes: ${row.actual.notes}` : ""}</p>}
                  </div>)}
                {Object.entries(state.budgets).map(([category, budget]) => <p key={category} className="mt-1 text-sm">{category}: {budget.currency} {budget.known_total} / {budget.amount} · {budget.status}</p>)}
                {state.schedule?.filter((day) => JSON.stringify(preview.base.schedule?.find((d) => d.date === day.date)) !== JSON.stringify(preview.result.bookings.schedule?.find((d) => d.date === day.date))).map((day) =>
                  <div key={day.date} className="mt-3 text-sm"><h4 className="font-semibold">Affected day · {day.date}</h4>
                    <ul>{day.stops.map((stop, index) => <li key={index}>{stop.time || "Time unknown"} · {stop.name}{stop.booked ? " · booked" : ""}</li>)}</ul>
                  </div>)}
              </div>)}
          </div>
          <div className="mt-4 flex gap-3"><button disabled={busy} onClick={() => void apply()} className="btn-primary">Confirm adjustment</button>
            <button disabled={busy} onClick={() => setPreview(null)} className="btn-ghost">Cancel</button></div>
        </section>}
        {view.rows.length === 0 && <p className="rounded-xl bg-paper p-5">No bookable items are saved yet. Research flights or hotels above, or add ticketed stops in the itinerary.</p>}
        {view.rows.map((row) => <article key={row.id} className="rounded-2xl border border-border bg-paper p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><p className="text-xs font-semibold uppercase text-brand">{row.category} · {row.intent_state.replaceAll("_", " ")} · {row.evidence.replaceAll("_", " ")}</p>
              <h2 className="mt-1 text-xl font-semibold">{row.name}</h2>
              {!row.selected && <p className="text-sm text-muted">Researched proposal · choose or lock to add to the itinerary</p>}
              {row.booked && <p className="mt-1 flex items-center gap-1 text-sm text-green-800"><Check size={14} /> {row.actual ? `Reported booked through ${row.actual.provider}` : "Marked booked in itinerary"}</p>}
            </div><strong className="text-lg">{money(row)}</strong>
          </div>
          <div className="mt-3"><Facts choice={row} /></div>
          {row.warnings?.map((warning) => <p key={warning} className="mt-2 text-sm text-amber-800">{warning}</p>)}
          <div className="mt-4 flex flex-wrap gap-2">
            {!row.booked && <button disabled={busy} className="btn-ghost" onClick={() => void run({ action: row.intent_state === "locked" ? "unlock" : "lock", item_id: row.id })}><LockKeyhole size={14} /> {row.intent_state === "locked" ? "Unlock intention" : "Lock intention"}</button>}
            {row.url ? <a className="btn-ghost" href={row.url} target="_blank" rel="noopener noreferrer"><ExternalLink size={14} /> Open provider · product page</a> : <span className="self-center text-xs text-muted">No verified booking link. Use these details with any provider.</span>}
            <button disabled={busy} className="btn-ghost" onClick={() => setReportId(reportId === row.id ? "" : row.id)}>{row.actual ? "Edit reported booking" : "Record booking made elsewhere"}</button>
            {!row.booked && <button disabled={busy} className="btn-ghost" onClick={() => setIntentId(intentId === row.id ? "" : row.id)}>Edit researched intent details</button>}
            <label className="text-xs">Booking requirement<select className="input block" value={row.disposition} disabled={busy || row.booked} onChange={(e) => void run({ action: "disposition", item_id: row.id, disposition: e.target.value })}>
              <option value="needs_booking">Needs booking</option><option value="pay_locally">Pay locally</option><option value="not_needed">No booking needed</option>
            </select></label>
          </div>
          {row.intended && row.actual && <p className="mt-3 text-sm text-muted">Original intention: {row.intended.name} · {money(row.intended)} · {dateLine(row.intended)}</p>}
          {row.actual?.reference && <p className="mt-2 text-sm">Private confirmation: {row.actual.reference}</p>}
          {reportId === row.id && <ReportForm key={view.updated_at + row.id} row={row} disabled={busy} onPreview={(command) => void run(command)} />}
          {intentId === row.id && <ReportForm key={"intent" + view.updated_at + row.id} intent row={row} disabled={busy} onPreview={(command) => void run(command)} />}
          {row.alternatives.length > 0 && <details className="mt-4 border-t border-border pt-3">
            <summary className="cursor-pointer font-medium">{row.alternatives.length} saved options · compare exact terms</summary>
            <div className="mt-3 grid gap-3 md:grid-cols-2">{row.alternatives.map((option) => <section key={option.id} className="rounded-xl border border-border p-4">
              <div className="flex justify-between gap-2"><h3 className="font-semibold">{option.name}</h3><span>{money(option)}</span></div>
              <p className="mb-2 text-xs text-brand">{option.id === row.option_id ? "Selected / recommended intention" : option.recommended ? "Original recommendation" : "Alternative"}</p>
              <Facts choice={option} />{option.reason && <p className="mt-2 text-sm">{option.reason}</p>}
              <button className="btn-ghost mt-3" disabled={busy || row.booked} onClick={() => void run({ action: "choose", item_id: row.id, option_id: option.id })}>Preview this choice</button>
            </section>)}</div>
          </details>}
        </article>)}
        <a className="inline-block text-sm text-brand underline" href={bookingJsonUrl(view)} download>Download booking intent data (JSON)</a>
      </>}
    </div>
    {exportOpen && view && <ExportModal bookingTrip={{ trip_id: view.trip_id, updated_at: view.updated_at }} onClose={() => setExportOpen(false)} />}
  </main>;
}
