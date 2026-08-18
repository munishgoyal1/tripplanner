import { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  Check,
  Database,
  MessageCircle,
  RefreshCcw,
  Send,
  Shield,
  Star as StarIcon,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import { options, type OptionId } from "./options";
import "../../../src/index.css";
import "./styles.css";

type Device = "desktop" | "mobile";
type Sentiment = "up" | "down";

interface Submission {
  sentiment?: Sentiment;
  rating?: number;
  comment?: string;
  day?: number;
  at: string;
}

const days = [
  {
    day: 1,
    date: "Thu 12 Mar",
    title: "Arrival and Alfama",
    stops: [
      { time: "14:20", name: "Check in · Hotel do Chiado", detail: "Stay · 2 nights" },
      { time: "16:30", name: "Miradouro de Santa Luzia", detail: "Viewpoint · 45 min" },
      { time: "19:30", name: "Dinner · Taberna Real", detail: "Booked" },
    ],
  },
  {
    day: 2,
    date: "Fri 13 Mar",
    title: "Belém and the river",
    stops: [
      { time: "09:15", name: "Jerónimos Monastery", detail: "Opens 09:00 · 1h 30m" },
      { time: "11:30", name: "Pastéis de Belém", detail: "Snack · 30 min" },
      { time: "15:00", name: "MAAT", detail: "Museum · 1h 15m" },
    ],
  },
  {
    day: 3,
    date: "Sat 14 Mar",
    title: "Sintra day trip",
    stops: [
      { time: "08:40", name: "Train to Sintra", detail: "Transfer · 40 min" },
      { time: "10:00", name: "Pena Palace", detail: "Timed entry · 2h" },
      { time: "18:10", name: "Return to Lisbon", detail: "Transfer · 45 min" },
    ],
  },
];

function Stars({ value, onRate, size = 17 }: { value: number; onRate: (n: number) => void; size?: number }) {
  return (
    <span className="tf-stars" role="group" aria-label="Star rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          className={`tf-star ${n <= value ? "on" : ""}`}
          aria-label={`${n} star${n > 1 ? "s" : ""}`}
          aria-pressed={n <= value}
          onClick={() => onRate(n)}
        >
          <StarIcon size={size} fill={n <= value ? "currentColor" : "none"} />
        </button>
      ))}
    </span>
  );
}

function Thumbs({ value, onPick, mini = false }: {
  value?: Sentiment;
  onPick: (next: Sentiment) => void;
  mini?: boolean;
}) {
  return (
    <span className="tf-thumbs">
      <button
        type="button"
        className={`tf-thumb up ${mini ? "mini" : ""} ${value === "up" ? "on" : ""}`}
        aria-label="This plan works"
        aria-pressed={value === "up"}
        onClick={() => onPick("up")}
      >
        <ThumbsUp size={mini ? 12 : 14} />
      </button>
      <button
        type="button"
        className={`tf-thumb down ${mini ? "mini" : ""} ${value === "down" ? "on" : ""}`}
        aria-label="This plan misses"
        aria-pressed={value === "down"}
        onClick={() => onPick("down")}
      >
        <ThumbsDown size={mini ? 12 : 14} />
      </button>
    </span>
  );
}

function SentMarker({ count }: { count: number }) {
  if (count < 1) return null;
  return (
    <span className="tf-badge">
      <Check size={11} /> Feedback sent{count > 1 ? ` · ${count}` : ""}
    </span>
  );
}

interface FeedbackApi {
  current?: Submission;
  count: number;
  record: (patch: Partial<Submission>) => void;
  reset: () => void;
}

/** The body every option shares. Only its container changes between options. */
function FeedbackBody({ api, compact, onClose }: { api: FeedbackApi; compact?: boolean; onClose?: () => void }) {
  const [draft, setDraft] = useState("");
  const current = api.current;

  return (
    <>
      <div className="tf-row" style={{ justifyContent: "space-between" }}>
        <div>
          <h4>{current ? "Thanks — anything else?" : "How does this trip read?"}</h4>
          {!compact && (
            <p>One tap is enough. The rating and the note are optional.</p>
          )}
        </div>
        {onClose && (
          <button type="button" className="tf-star" aria-label="Close" onClick={onClose}>
            <X size={15} />
          </button>
        )}
      </div>

      <div className="tf-row">
        <Thumbs value={current?.sentiment} onPick={(sentiment) => api.record({ sentiment })} />
        <Stars value={current?.rating ?? 0} onRate={(rating) => api.record({ rating })} />
        {current && <SentMarker count={api.count} />}
      </div>

      <textarea
        className="tf-comment"
        placeholder="Optional: what would you change?"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
      />

      <div className="tf-row" style={{ justifyContent: "space-between" }}>
        <button
          type="button"
          className="tf-send"
          onClick={() => {
            api.record({ comment: draft.trim() || undefined });
            setDraft("");
          }}
        >
          <Send size={13} /> {current ? "Add to feedback" : "Send feedback"}
        </button>
        {api.count > 0 && (
          <button type="button" className="tf-again" onClick={() => { api.reset(); setDraft(""); }}>
            <RefreshCcw size={11} style={{ verticalAlign: "-1px" }} /> Give feedback again
          </button>
        )}
      </div>
    </>
  );
}

function Plan({ option, api }: { option: OptionId; api: FeedbackApi }) {
  return (
    <div className="tf-plan">
      {days.map((entry) => (
        <article key={entry.day} className="tf-day">
          <header className="tf-day-head">
            <div>
              <strong>Day {entry.day} · {entry.title}</strong>
              <small>{entry.date}</small>
            </div>
            {option === "per-day" && (
              <Thumbs
                mini
                value={api.current?.day === entry.day ? api.current.sentiment : undefined}
                onPick={(sentiment) => api.record({ sentiment, day: entry.day })}
              />
            )}
          </header>
          {entry.stops.map((stop) => (
            <div key={stop.name} className="tf-stop">
              <time>{stop.time}</time>
              <span>
                <b>{stop.name}</b>
                <em>{stop.detail}</em>
              </span>
            </div>
          ))}
        </article>
      ))}

      {option === "itinerary-footer" && (
        <section className="tf-card accent">
          <FeedbackBody api={api} />
        </section>
      )}

      {option === "per-day" && (
        <section className="tf-card">
          <div className="tf-row" style={{ justifyContent: "space-between" }}>
            <div>
              <h4>And the trip overall?</h4>
              <p>Day thumbs roll up here, so one verdict still exists for the whole plan.</p>
            </div>
            <SentMarker count={api.count} />
          </div>
          <div className="tf-row">
            <Stars value={api.current?.rating ?? 0} onRate={(rating) => api.record({ rating })} />
            <span className="tf-hint">Optional comment appears once a day is marked.</span>
          </div>
        </section>
      )}
    </div>
  );
}

function Preview({ option, device, api }: { option: OptionId; device: Device; api: FeedbackApi }) {
  const [open, setOpen] = useState(false);
  const mobile = device === "mobile";

  return (
    <div className={`tf-stage ${mobile ? "mobile" : ""}`}>
      <section className={`tf-shell ${mobile ? "mobile" : ""}`} aria-label="Workspace preview">
        <header className="tf-bar">
          <div className="tf-bar-left">
            <strong>Lisbon · 3 days</strong>
            {!mobile && <small>12–14 Mar · 2 travellers</small>}
          </div>
          {!mobile && (
            <div className="tf-panes">
              <span className="on">Itinerary</span>
              <span>Map</span>
              <span>Details</span>
              <span>Assistant</span>
            </div>
          )}
          <div className="tf-bar-right">
            {option === "toolbar-pill" && (
              <>
                <SentMarker count={api.count} />
                <Thumbs
                  mini
                  value={api.current?.sentiment}
                  onPick={(sentiment) => { api.record({ sentiment }); setOpen(true); }}
                />
                <button type="button" className="tf-send ghost" onClick={() => setOpen((prev) => !prev)}>
                  <StarIcon size={12} /> Rate
                </button>
              </>
            )}
            {option !== "toolbar-pill" && api.count > 0 && <SentMarker count={api.count} />}
          </div>
        </header>

        <div className="tf-body">
          <Plan option={option} api={api} />
          <div className="tf-map" />
        </div>

        {option === "assistant-ask" && (
          <div className="tf-thread">
            <div className="tf-msg">
              <span className="tf-avatar">TP</span>
              <div className="tf-bubble">
                Your Lisbon plan is ready. Does this read the way you wanted?
                <div className="tf-row" style={{ marginTop: 8 }}>
                  <Thumbs value={api.current?.sentiment} onPick={(sentiment) => api.record({ sentiment })} />
                  <Stars value={api.current?.rating ?? 0} onRate={(rating) => api.record({ rating })} size={15} />
                  <SentMarker count={api.count} />
                </div>
              </div>
            </div>
          </div>
        )}

        {option === "toolbar-pill" && open && (
          <div className="tf-card accent tf-pop">
            <FeedbackBody api={api} compact onClose={() => setOpen(false)} />
          </div>
        )}

        {option === "floating-tab" && !open && (
          <button type="button" className="tf-float" onClick={() => setOpen(true)}>
            <MessageCircle size={13} /> Rate this trip
            {api.count > 0 && <Check size={12} />}
          </button>
        )}
        {option === "floating-tab" && open && (
          <div className="tf-card accent tf-sheet">
            <FeedbackBody api={api} compact onClose={() => setOpen(false)} />
          </div>
        )}
      </section>
    </div>
  );
}

function App() {
  const [option, setOption] = useState<OptionId>("toolbar-pill");
  const [device, setDevice] = useState<Device>("desktop");
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [openRound, setOpenRound] = useState(false);
  const active = options.find((item) => item.id === option)!;

  // A round is one visit to the control: the first input submits, anything else
  // in the same visit amends that submission rather than inflating the count.
  const api: FeedbackApi = {
    current: openRound ? submissions[submissions.length - 1] : undefined,
    count: submissions.length,
    record: (patch) => {
      setSubmissions((previous) => {
        if (!openRound) {
          return [...previous, { ...patch, at: new Date().toISOString() }];
        }
        const next = [...previous];
        next[next.length - 1] = { ...next[next.length - 1], ...patch };
        return next;
      });
      setOpenRound(true);
    },
    reset: () => setOpenRound(false),
  };

  return (
    <main className="lab-page"><div className="lab-wrap">
      <LabNavigation detail labId="trip-feedback" />
      <header className="lab-header">
        <div>
          <p className="lab-kicker"><StarIcon size={16} /> Trip feedback capture</p>
          <h1>Say how the<br />trip reads.</h1>
          <p>Once a traveller has an itinerary and has actually read it, they should always be able to say whether it works. The inputs are settled: a thumbs pair, an optional five-star rating, and an optional comment, where a single tap already counts as feedback. What is not settled is where that control lives in a workspace whose real estate is already spoken for, and how a trip shows that feedback has been sent before without turning into a nag.</p>
        </div>
        <div className="principle-card">
          <span>The constraint</span>
          <strong>Always available.<br />Almost no room.</strong>
          <small>One tap to submit · repeatable · trip-scoped</small>
        </div>
      </header>
      <LabScope labId="trip-feedback" />
      <OptionContrast labId="trip-feedback" />

      <section className="option-picker">
        <div className="section-kicker">Five homes for the same control</div>
        <div className="option-grid">
          {options.map((item) => (
            <button
              key={item.id}
              className={option === item.id ? "selected" : ""}
              onClick={() => setOption(item.id)}
            >
              <span className="option-label">{item.label}</span>
              <strong>{item.summary}</strong>
              <small>{item.cost}</small>
              <span className="option-rest">
                <span>Rests as: {item.resting}</span>
                <span>Reach: {item.reach}</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      <div className="tf-toolbar">
        <div>
          <p className="section-kicker">Exact delta · live</p>
          <strong>{active.label}</strong>
          <p className="tf-delta">
            Unique to this option: {active.summary.toLowerCase()} It rests as {active.resting.toLowerCase()} and is reachable from {active.reach.toLowerCase()}. The other four keep the identical inputs but move the control elsewhere, so any difference you see below is placement and resting cost, never what is being asked.
          </p>
        </div>
        <SentMarker count={submissions.length} />
        <div className="tf-devices">
          {(["desktop", "mobile"] as Device[]).map((item) => (
            <button
              key={item}
              type="button"
              className={device === item ? "active" : ""}
              onClick={() => setDevice(item)}
            >
              {item === "desktop" ? "Desktop" : "Mobile"}
            </button>
          ))}
        </div>
      </div>

      <Preview option={option} device={device} api={api} />

      <section className="tf-model">
        <div>
          <p className="section-kicker"><Database size={12} style={{ verticalAlign: "-2px" }} /> Where it is stored</p>
          <h3>A separate container, not the trip document</h3>
          <p>Feedback is append-only and unbounded, while a trip document is read on every workspace load and replaced under an ETag. Embedding submissions would make every trip read pay for them and would put feedback writes in conflict with ordinary itinerary edits.</p>
          <pre>{`trip_feedback            partition key: /user_id
{
  "id": "fb_01JD9…",          // one doc per submission
  "user_id": "google-1018…",  // or guest capability id
  "identified": true,
  "trip_id": "lisbon-2027-03-12",
  "trip_revision": 14,        // what they actually read
  "sentiment": "up",          // "up" | "down" | null
  "rating": 4,                // 1-5 | null
  "comment": "Day 3 too long",// optional, trimmed, capped
  "day": null,                // set only by per-day thumbs
  "surface": "toolbar-pill",
  "client": "web",
  "created_at": "2026-08-18T…"
}`}</pre>
        </div>
        <div>
          <p className="section-kicker"><Shield size={12} style={{ verticalAlign: "-2px" }} /> What the trip carries</p>
          <h3>The trip keeps a small summary</h3>
          <p>The already-sent marker must render without a second query, so the trip document carries only a rollup. The submissions themselves stay in their own container.</p>
          <pre>{`trips/<trip_id>
"feedback": {
  "count": 2,
  "last_at": "2026-08-18T09:14:22Z",
  "last_rating": 4,
  "last_sentiment": "up"
}`}</pre>
          <ul>
            <li><strong>Repeat submissions are normal.</strong> Nothing is overwritten; the count is what the marker shows.</li>
            <li><strong>The user id is recorded when one exists.</strong> A guest keeps their capability id, and neither path blocks the comment box behind sign-in.</li>
            <li><strong>Comments are user content.</strong> Trimmed, length-capped, never echoed into a prompt, and covered by the same erasure path as the rest of the account.</li>
            <li><strong>Deleting a trip</strong> deletes its feedback with it, since both live under the same partition key.</li>
          </ul>
        </div>
      </section>

      <section className="tf-notes">
        <div><ThumbsUp size={15} /><span><strong>One tap is a complete submission.</strong> The rating and the comment are enrichment, never a requirement, in all five options.</span></div>
        <div><RefreshCcw size={15} /><span><strong>Feedback can be given again.</strong> Later submissions append; the quiet marker shows that some already exist without blocking a new one.</span></div>
        <div><MessageCircle size={15} /><span><strong>Nothing blocks the plan.</strong> No option uses a modal, a takeover, or a rating gate before the traveller can keep reading.</span></div>
      </section>

      <DecisionCapture
        labId="trip-feedback"
        labTitle="Say how the trip reads"
        options={options.map(({ id, label }) => ({ id, label }))}
        activeOption={option}
        onChoose={(id) => setOption(id as OptionId)}
      />
    </div></main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
