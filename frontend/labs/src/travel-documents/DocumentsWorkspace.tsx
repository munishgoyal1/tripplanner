import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Building2,
  Camera,
  Check,
  ChevronDown,
  CircleUserRound,
  Download,
  FileText,
  Inbox,
  List,
  Loader2,
  Lock,
  Map as MapIcon,
  MessageCircle,
  PanelRight,
  Plane,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
  UtensilsCrossed,
  X,
} from "lucide-react";
import {
  bookingDocuments,
  blockerCount,
  itinerary,
  pendingExtraction,
  readinessChecks,
  travellerDocuments,
  travellers,
  tripLabel,
  type ExtractedField,
  type ItineraryStop,
  type ReadinessCheck,
  type TravellerDocument,
} from "./fixture";

export type DocumentsOption = "readiness" | "vault" | "inbox";

type CaptureStage = "reading" | "extracting" | "review" | "saved";

interface CaptureState {
  fileName: string;
  travellerId: string;
  label: string;
  stage: CaptureStage;
  fields: ExtractedField[];
  remember: boolean;
}

const stopIcon: Record<ItineraryStop["kind"], typeof Camera> = {
  flight: Plane,
  hotel: Building2,
  attraction: Camera,
  meal: UtensilsCrossed,
};

function marker(label: string) {
  return { "data-lab-change": label };
}

function confidenceTone(confidence: number): string {
  if (confidence >= 0.97) return "text-emerald-700";
  if (confidence >= 0.92) return "text-amber-700";
  return "text-rose-700";
}

/* ---------------------------------------------------------------- primitives */

function SeverityDot({ severity }: { severity: ReadinessCheck["severity"] }) {
  const tone = severity === "blocker" ? "bg-rose-500" : severity === "warning" ? "bg-amber-500" : "bg-emerald-500";
  return <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${tone}`} aria-hidden />;
}

function CheckRow({ check, onFix }: { check: ReadinessCheck; onFix?: () => void }) {
  const traveller = travellers.find((person) => person.id === check.travellerId);
  return (
    <li className="flex gap-2 border-b border-slate-100 px-3 py-2.5 last:border-0">
      <SeverityDot severity={check.severity} />
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-semibold leading-snug text-ink">{check.title}</p>
        <p className="mt-0.5 text-[11px] leading-relaxed text-slate-600">{check.detail}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {traveller ? <span className="chip">{traveller.name.split(" ")[0]}</span> : null}
          <span className="chip font-mono text-[10px]">{check.rule}</span>
          {check.origin === "grounded" ? (
            <span className="chip bg-sky-50 text-sky-700">Source · {check.source}</span>
          ) : (
            <span className="chip bg-slate-100">Computed here</span>
          )}
        </div>
        {check.action && onFix ? (
          <button
            type="button"
            onClick={onFix}
            className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-brand hover:underline"
          >
            {check.action} <ArrowRight size={11} aria-hidden />
          </button>
        ) : check.action ? (
          <p className="mt-1.5 text-[11px] font-medium text-slate-500">{check.action}</p>
        ) : null}
      </div>
    </li>
  );
}

function DocumentRow({
  doc,
  onDelete,
  justAdded,
}: {
  doc: TravellerDocument;
  onDelete: (id: string) => void;
  justAdded?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const expiringSoon = doc.expiry ? doc.expiry < "2026-12-01" : false;
  return (
    <li className="border-b border-slate-100 last:border-0">
      <div className="flex items-start gap-2 px-3 py-2">
        <FileText size={14} className="mt-0.5 shrink-0 text-slate-400" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-1.5">
            <p className="text-[12px] font-semibold text-ink">{doc.title}</p>
            <span className="text-[11px] text-slate-500">{doc.issuer}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {doc.expiryLabel ? (
              <span className={`chip ${expiringSoon ? "bg-rose-50 text-rose-700" : ""}`}>
                Expires {doc.expiryLabel}
              </span>
            ) : null}
            {justAdded ? (
              <span className="chip bg-emerald-50 text-emerald-700">Added just now</span>
            ) : doc.reusedFrom ? (
              <span className="chip bg-slate-100">Reused from {doc.reusedFrom}</span>
            ) : null}
            <span className="chip bg-slate-100">
              <Lock size={9} aria-hidden /> Fields only
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="rounded-md px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-100"
            aria-expanded={open}
          >
            {open ? "Hide" : "View"}
          </button>
          <button
            type="button"
            onClick={() => onDelete(doc.id)}
            className="rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
            aria-label={`Delete ${doc.title}`}
          >
            <Trash2 size={13} aria-hidden />
          </button>
        </div>
      </div>
      {open ? (
        <dl className="mx-3 mb-2.5 rounded-xl bg-slate-50 px-3 py-2">
          {doc.fields.map((field) => (
            <div key={field.label} className="flex items-baseline justify-between gap-3 py-0.5">
              <dt className="text-[11px] text-slate-500">{field.label}</dt>
              <dd className="text-[11px] font-semibold text-ink">
                {field.value}
                {field.masked ? <span className="ml-1 font-normal text-slate-400">masked</span> : null}
              </dd>
            </div>
          ))}
          <p className="mt-1.5 border-t border-slate-200 pt-1.5 text-[10px] leading-relaxed text-slate-500">
            Captured {doc.capturedOn}. The original image was read once and discarded — these fields are all that
            exist.
          </p>
        </dl>
      ) : null}
    </li>
  );
}

function CaptureCard({
  capture,
  onToggleRemember,
  onSave,
  onCancel,
  compact,
}: {
  capture: CaptureState;
  onToggleRemember: () => void;
  onSave: () => void;
  onCancel: () => void;
  compact?: boolean;
}) {
  if (capture.stage === "reading" || capture.stage === "extracting") {
    return (
      <div className="rounded-2xl bg-white p-4 text-center shadow-card ring-1 ring-slate-200">
        <Loader2 size={18} className="mx-auto animate-spin text-brand" aria-hidden />
        <p className="mt-2 text-[12px] font-semibold text-ink">
          {capture.stage === "reading" ? "Reading the file" : "Pulling out the fields"}
        </p>
        <p className="mt-0.5 text-[11px] text-slate-500">{capture.fileName}</p>
        <p className="mx-auto mt-2 max-w-xs text-[11px] leading-relaxed text-slate-500">
          Nothing has been stored yet. The image is held in memory only for as long as this takes.
        </p>
      </div>
    );
  }

  if (capture.stage === "saved") {
    return (
      <div className="rounded-2xl bg-emerald-50 p-4 text-center ring-1 ring-emerald-200">
        <BadgeCheck size={18} className="mx-auto text-emerald-600" aria-hidden />
        <p className="mt-1.5 text-[12px] font-semibold text-emerald-900">{capture.label} saved</p>
        <p className="mt-0.5 text-[11px] leading-relaxed text-emerald-800">
          {capture.remember
            ? "Kept on your account for future trips. The image itself was deleted."
            : "Kept on this trip only. The image itself was deleted."}
        </p>
      </div>
    );
  }

  return (
    <div className={`rounded-2xl bg-white shadow-pop ring-1 ring-slate-200 ${compact ? "" : "w-[26rem]"}`}>
      <div className="flex items-start gap-2 border-b border-slate-100 px-4 py-3">
        <ShieldCheck size={15} className="mt-0.5 shrink-0 text-brand" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-semibold text-ink">Check what we read</p>
          <p className="text-[11px] text-slate-500">{capture.fileName}</p>
        </div>
        <button type="button" onClick={onCancel} className="rounded-md p-1 text-slate-400 hover:bg-slate-100">
          <X size={14} aria-hidden />
        </button>
      </div>
      <div className="px-4 py-2.5">
        {capture.fields.map((field) => (
          <label key={field.label} className="flex items-center gap-2 border-b border-slate-50 py-1.5 last:border-0">
            <span className="w-28 shrink-0 text-[11px] text-slate-500">{field.label}</span>
            <input
              defaultValue={field.value}
              className="min-w-0 flex-1 rounded-lg border border-slate-200 px-2 py-1 text-[12px] font-semibold text-ink focus:border-brand focus:outline-none"
            />
            <span className={`w-10 shrink-0 text-right text-[10px] font-semibold ${confidenceTone(field.confidence)}`}>
              {Math.round(field.confidence * 100)}%
            </span>
          </label>
        ))}
      </div>
      <div className="border-t border-slate-100 px-4 py-2.5">
        <button
          type="button"
          onClick={onToggleRemember}
          className="flex w-full items-start gap-2 rounded-xl bg-slate-50 p-2.5 text-left hover:bg-slate-100"
          aria-pressed={capture.remember}
        >
          <span
            className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
              capture.remember ? "border-brand bg-brand text-white" : "border-slate-300 bg-white"
            }`}
            aria-hidden
          >
            {capture.remember ? <Check size={11} /> : null}
          </span>
          <span className="min-w-0">
            <span className="block text-[11px] font-semibold text-ink">Remember for future trips</span>
            <span className="block text-[11px] leading-relaxed text-slate-600">
              Keeps these fields on your account so the next trip is checked without asking again.
            </span>
          </span>
        </button>
        <p className="mt-2 flex items-start gap-1.5 text-[10px] leading-relaxed text-slate-500">
          <Lock size={11} className="mt-px shrink-0" aria-hidden />
          The file is deleted when you save. Only the fields above are kept, and the document number is stored masked.
        </p>
        <div className="mt-2.5 flex items-center gap-2">
          <button type="button" onClick={onSave} className="btn-primary h-8 flex-1 text-xs">
            Save details
          </button>
          <button type="button" onClick={onCancel} className="btn-ghost h-8">
            Discard
          </button>
        </div>
      </div>
    </div>
  );
}

function ExportSheet({
  include,
  reveal,
  onToggleInclude,
  onToggleReveal,
  onClose,
}: {
  include: boolean;
  reveal: boolean;
  onToggleInclude: () => void;
  onToggleReveal: () => void;
  onClose: () => void;
}) {
  return (
    <div className="absolute inset-0 z-50 flex justify-end bg-ink/25">
      <section className="flex h-full w-[24rem] flex-col bg-white shadow-pop" aria-label="Export trip">
        <header className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
          <Download size={15} className="text-brand" aria-hidden />
          <h2 className="text-sm font-semibold text-ink">Export trip</h2>
          <button type="button" onClick={onClose} className="ml-auto rounded-md p-1 text-slate-400 hover:bg-slate-100">
            <X size={14} aria-hidden />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <p className="text-[11px] leading-relaxed text-slate-600">
            One PDF for the whole trip: days, stops, maps, and every confirmation reference you have added.
          </p>
          <div className="mt-3 rounded-2xl bg-slate-50 p-3">
            <p className="text-[10px] font-bold uppercase text-slate-500">Always included</p>
            <ul className="mt-1.5 space-y-1 text-[11px] text-slate-700">
              <li>Day-by-day itinerary and maps</li>
              <li>Booking references · TAP 4XQ2P9, Bairro Alto BA-88421</li>
              <li>Insurance assistance line</li>
            </ul>
          </div>
          <button
            type="button"
            onClick={onToggleInclude}
            className="mt-3 flex w-full items-start gap-2 rounded-2xl bg-white p-3 text-left ring-1 ring-slate-200 hover:bg-slate-50"
            aria-pressed={include}
          >
            <span
              className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                include ? "border-brand bg-brand text-white" : "border-slate-300 bg-white"
              }`}
              aria-hidden
            >
              {include ? <Check size={11} /> : null}
            </span>
            <span>
              <span className="block text-[11px] font-semibold text-ink">Include traveller documents</span>
              <span className="block text-[11px] leading-relaxed text-slate-600">
                Passport and visa details for all three travellers. Off by default.
              </span>
            </span>
          </button>
          {include ? (
            <div className="mt-2 rounded-2xl bg-amber-50 p-3 ring-1 ring-amber-200">
              <button
                type="button"
                onClick={onToggleReveal}
                className="flex w-full items-start gap-2 text-left"
                aria-pressed={reveal}
              >
                <span
                  className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                    reveal ? "border-amber-600 bg-amber-600 text-white" : "border-amber-400 bg-white"
                  }`}
                  aria-hidden
                >
                  {reveal ? <Check size={11} /> : null}
                </span>
                <span>
                  <span className="block text-[11px] font-semibold text-amber-900">Show full document numbers</span>
                  <span className="block text-[11px] leading-relaxed text-amber-800">
                    {reveal
                      ? "Z1234567 will be printed in full. Anyone holding this PDF holds the number."
                      : "Numbers print as Z••••••7. Enough to recognise, not enough to misuse."}
                  </span>
                </span>
              </button>
              {reveal ? (
                <p className="mt-2 flex items-start gap-1.5 border-t border-amber-200 pt-2 text-[10px] leading-relaxed text-amber-900">
                  <AlertTriangle size={11} className="mt-px shrink-0" aria-hidden />
                  Emailing this file will ask you to confirm a second time.
                </p>
              ) : null}
            </div>
          ) : null}
          <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
            Share links never include any of this, whatever you choose here.
          </p>
        </div>
        <footer className="border-t border-slate-200 p-3">
          <button type="button" className="btn-primary h-9 w-full text-xs">
            Download PDF
          </button>
        </footer>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------- panes */

function ItineraryPane() {
  const byDay = useMemo(() => {
    const groups = new Map<number, ItineraryStop[]>();
    itinerary.forEach((stop) => {
      const list = groups.get(stop.day) || [];
      list.push(stop);
      groups.set(stop.day, list);
    });
    return Array.from(groups.entries());
  }, []);

  return (
    <section className="flex min-h-0 flex-col border-r border-[#dce2df] bg-white" aria-label="Itinerary">
      <div className="flex items-center gap-2 border-b border-slate-200 px-3 py-2.5">
        <p className="text-[10px] font-bold uppercase text-slate-500">Itinerary</p>
        <span className="chip ml-auto">6 days</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {byDay.map(([day, stops]) => (
          <div key={day}>
            <div className="sticky top-0 z-10 flex items-baseline gap-2 border-b border-slate-100 bg-slate-50/95 px-3 py-1.5 backdrop-blur">
              <p className="text-[11px] font-bold text-ink">Day {day}</p>
              <p className="text-[10px] text-slate-500">{day === 1 ? "Thu 8 Oct" : day === 2 ? "Fri 9 Oct" : "Sat 10 Oct"}</p>
            </div>
            {stops.map((stop) => {
              const Icon = stopIcon[stop.kind];
              const booking = bookingDocuments.find((item) => item.stopId === stop.id);
              return (
                <div key={stop.id} className="flex items-start gap-2 border-b border-slate-50 px-3 py-2">
                  <span className="w-9 shrink-0 pt-0.5 text-[10px] font-semibold text-slate-500">{stop.time}</span>
                  <Icon size={13} className="mt-0.5 shrink-0 text-slate-400" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12px] font-medium text-ink">{stop.name}</p>
                    {booking ? (
                      <span
                        className="mt-0.5 inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700"
                        {...marker("Booking reference on the stop it belongs to")}
                      >
                        <Check size={9} aria-hidden /> {booking.provider} · {booking.reference}
                      </span>
                    ) : stop.kind !== "meal" ? (
                      <button
                        type="button"
                        className="mt-0.5 inline-flex items-center gap-1 text-[10px] font-semibold text-slate-400 hover:text-brand"
                      >
                        <Plus size={9} aria-hidden /> Add booking
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}

function MapPane() {
  return (
    <section className="relative min-h-0 overflow-hidden bg-[#e8ece9]" aria-label="Map">
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(120% 90% at 30% 20%, #dbe7e2 0%, #cfdfd9 40%, #c3d4cf 100%)",
        }}
        aria-hidden
      />
      <svg className="absolute inset-0 h-full w-full" aria-hidden>
        <path d="M 90 320 C 180 240, 260 260, 330 180" stroke="#e11d48" strokeWidth="2.5" fill="none" strokeDasharray="1 0" />
        <path d="M 330 180 C 400 120, 470 150, 540 110" stroke="#e11d48" strokeWidth="2.5" fill="none" />
      </svg>
      {[
        { x: 90, y: 320, n: 1 },
        { x: 330, y: 180, n: 2 },
        { x: 540, y: 110, n: 3 },
      ].map((pin) => (
        <span
          key={pin.n}
          className="absolute flex h-6 w-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-brand text-[10px] font-bold text-white shadow-pop"
          style={{ left: pin.x, top: pin.y }}
        >
          {pin.n}
        </span>
      ))}
      <div className="absolute left-3 top-3 rounded-xl bg-white/95 px-3 py-1.5 text-[11px] font-semibold text-ink shadow-card">
        Day 2 · 3 stops · 11.4 km
      </div>
    </section>
  );
}

function DetailsRail() {
  return (
    <aside className="flex min-h-0 flex-col overflow-y-auto border-l border-[#dce2df] bg-white" aria-label="Details">
      <div className="border-b border-slate-200 px-3 py-2.5">
        <p className="text-[10px] font-bold uppercase text-slate-500">Details</p>
      </div>
      <div className="p-3">
        <div
          className="h-24 w-full rounded-2xl"
          style={{ background: "linear-gradient(135deg,#fde7ea 0%,#f7d7c6 45%,#cfe6e2 100%)" }}
          aria-hidden
        />
        <h3 className="display mt-2.5 text-base font-semibold text-ink">Jerónimos Monastery</h3>
        <p className="mt-0.5 text-[11px] text-slate-500">Praça do Império 1400-206</p>
        <div className="mt-1.5 flex flex-wrap gap-1">
          <span className="chip">★ 4.7 · 61.3K</span>
          <span className="chip">€12</span>
          <span className="chip">10:00 – 17:30</span>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-600">
          The cloister queue is shortest before 10:30 and worst after 12:00.
        </p>
        <button type="button" className="btn-primary mt-2.5 h-8 w-full text-xs">
          Confirm booking
        </button>
      </div>
    </aside>
  );
}

/* ------------------------------------------------------- documents surfaces */

interface SurfaceProps {
  docs: TravellerDocument[];
  capture: CaptureState | null;
  savedDocId: string | null;
  onStartCapture: (travellerId: string, label: string, fileName: string) => void;
  onDelete: (id: string) => void;
  onToggleRemember: () => void;
  onSaveCapture: () => void;
  onCancelCapture: () => void;
}

function TravellerBlock({
  travellerId,
  docs,
  onStartCapture,
  onDelete,
  savedDocId,
}: {
  travellerId: string;
  docs: TravellerDocument[];
  onStartCapture: SurfaceProps["onStartCapture"];
  onDelete: (id: string) => void;
  savedDocId: string | null;
}) {
  const person = travellers.find((item) => item.id === travellerId);
  const mine = docs.filter((doc) => doc.travellerId === travellerId);
  const hasPassport = mine.some((doc) => doc.kind === "passport");
  if (!person) return null;
  return (
    <div className="border-b border-slate-100 last:border-0">
      <div className="flex items-center gap-2 bg-slate-50/80 px-3 py-1.5">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ink text-[9px] font-bold text-white">
          {person.initials}
        </span>
        <p className="text-[11px] font-semibold text-ink">{person.name}</p>
        <span className="text-[10px] text-slate-500">{person.relationship}</span>
        {!hasPassport ? <span className="chip ml-auto bg-rose-50 text-rose-700">Nothing on file</span> : null}
      </div>
      {mine.length ? (
        <ul>
          {mine.map((doc) => (
            <DocumentRow key={doc.id} doc={doc} onDelete={onDelete} justAdded={doc.id === savedDocId} />
          ))}
        </ul>
      ) : null}
      <div className="px-3 py-2">
        <button
          type="button"
          onClick={() => onStartCapture(travellerId, "Passport", `${person.name.split(" ")[0].toLowerCase()}-passport.jpg`)}
          className="btn-ghost h-7 w-full justify-center text-[11px]"
        >
          <Plus size={11} aria-hidden /> Add a document for {person.name.split(" ")[0]}
        </button>
      </div>
    </div>
  );
}

function ReadinessRail(props: SurfaceProps) {
  const blockers = readinessChecks.filter((check) => check.severity === "blocker");
  const clear = readinessChecks.filter((check) => check.severity === "ok");
  return (
    <aside
      className="flex min-h-0 flex-col overflow-y-auto border-l border-[#dce2df] bg-white"
      aria-label="Trip readiness"
      {...marker("Documents live inside the trip's Details rail")}
    >
      <div className="flex items-center gap-2 border-b border-slate-200 px-3 py-2.5">
        <p className="text-[10px] font-bold uppercase text-slate-500">Readiness</p>
        <span className="chip ml-auto bg-rose-50 text-rose-700">{blockerCount} to fix</span>
      </div>
      {props.capture ? (
        <div className="border-b border-slate-100 p-3">
          <CaptureCard
            compact
            capture={props.capture}
            onToggleRemember={props.onToggleRemember}
            onSave={props.onSaveCapture}
            onCancel={props.onCancelCapture}
          />
        </div>
      ) : null}
      <div className="border-b border-slate-100">
        <p className="px-3 pb-1 pt-2.5 text-[10px] font-bold uppercase text-slate-500">Before you go</p>
        <ul>
          {blockers.map((check) => (
            <CheckRow
              key={check.id}
              check={check}
              onFix={
                check.travellerId === "child"
                  ? () => props.onStartCapture("child", "Passport", "aarav-passport.jpg")
                  : undefined
              }
            />
          ))}
        </ul>
      </div>
      <div className="border-b border-slate-100">
        <p className="px-3 pb-1 pt-2.5 text-[10px] font-bold uppercase text-slate-500">Travellers</p>
        {travellers.map((person) => (
          <TravellerBlock
            key={person.id}
            travellerId={person.id}
            docs={props.docs}
            onStartCapture={props.onStartCapture}
            onDelete={props.onDelete}
            savedDocId={props.savedDocId}
          />
        ))}
      </div>
      <div>
        <p className="px-3 pb-1 pt-2.5 text-[10px] font-bold uppercase text-slate-500">Already clear</p>
        <ul>
          {clear.map((check) => (
            <CheckRow key={check.id} check={check} />
          ))}
        </ul>
      </div>
    </aside>
  );
}

function VaultSheet(props: SurfaceProps & { onClose: () => void }) {
  return (
    <div className="absolute inset-0 z-50 flex justify-end bg-ink/25" {...marker("Documents live in the account, not the trip")}>
      <section className="flex h-full w-[26rem] flex-col bg-white shadow-pop" aria-label="Travel documents">
        <header className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
          <CircleUserRound size={15} className="text-brand" aria-hidden />
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-ink">Travel documents</h2>
            <p className="text-[10px] text-slate-500">Account · used by every trip</p>
          </div>
          <button type="button" onClick={props.onClose} className="ml-auto rounded-md p-1 text-slate-400 hover:bg-slate-100">
            <X size={14} aria-hidden />
          </button>
        </header>
        {props.capture ? (
          <div className="border-b border-slate-100 p-3">
            <CaptureCard
              compact
              capture={props.capture}
              onToggleRemember={props.onToggleRemember}
              onSave={props.onSaveCapture}
              onCancel={props.onCancelCapture}
            />
          </div>
        ) : null}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <p className="bg-slate-50 px-4 py-2 text-[11px] leading-relaxed text-slate-600">
            We keep the details we read, never the document. Every trip you plan is checked against these
            automatically.
          </p>
          {travellers.map((person) => (
            <TravellerBlock
              key={person.id}
              travellerId={person.id}
              docs={props.docs}
              onStartCapture={props.onStartCapture}
              onDelete={props.onDelete}
              savedDocId={props.savedDocId}
            />
          ))}
          <div className="p-3">
            <button type="button" className="w-full rounded-xl border border-rose-200 px-3 py-2 text-[11px] font-semibold text-rose-700 hover:bg-rose-50">
              Delete every document detail
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function InboxDock(props: SurfaceProps & { open: boolean; onToggle: () => void }) {
  const queued = readinessChecks.filter((check) => check.severity === "blocker");
  return (
    <div
      className="absolute inset-x-0 bottom-0 z-40 border-t border-[#dce2df] bg-white shadow-[0_-8px_24px_rgba(23,36,51,.08)]"
      {...marker("One intake queue, triaged later, separate from placement")}
    >
      <button
        type="button"
        onClick={props.onToggle}
        className="flex w-full items-center gap-2 px-4 py-2 text-left"
        aria-expanded={props.open}
      >
        <Inbox size={14} className="text-brand" aria-hidden />
        <span className="text-[12px] font-semibold text-ink">Document inbox</span>
        <span className="chip bg-rose-50 text-rose-700">{queued.length} need review</span>
        <span className="ml-auto text-[11px] text-slate-500">Drop a file anywhere</span>
        <ChevronDown size={14} className={`text-slate-400 transition ${props.open ? "" : "rotate-180"}`} aria-hidden />
      </button>
      {props.open ? (
        <div className="max-h-[19rem] overflow-y-auto border-t border-slate-100">
          {props.capture ? (
            <div className="border-b border-slate-100 p-3">
              <CaptureCard
                compact
                capture={props.capture}
                onToggleRemember={props.onToggleRemember}
                onSave={props.onSaveCapture}
                onCancel={props.onCancelCapture}
              />
            </div>
          ) : (
            <div className="grid gap-2 p-3 lg:grid-cols-2">
              <button
                type="button"
                onClick={() => props.onStartCapture("child", "Passport", "aarav-passport.jpg")}
                className="flex items-center gap-2 rounded-2xl border border-dashed border-slate-300 px-3 py-4 text-left hover:border-brand hover:bg-brand/5"
              >
                <Plus size={16} className="text-brand" aria-hidden />
                <span>
                  <span className="block text-[12px] font-semibold text-ink">Drop anything here</span>
                  <span className="block text-[11px] text-slate-500">
                    Boarding passes, hotel confirmations, passports, visas. We sort out what it is.
                  </span>
                </span>
              </button>
              <ul className="rounded-2xl ring-1 ring-slate-200">
                {queued.map((check) => (
                  <CheckRow
                    key={check.id}
                    check={check}
                    onFix={
                      check.travellerId === "child"
                        ? () => props.onStartCapture("child", "Passport", "aarav-passport.jpg")
                        : undefined
                    }
                  />
                ))}
              </ul>
            </div>
          )}
          <div className="border-t border-slate-100">
            {travellers.map((person) => (
              <TravellerBlock
                key={person.id}
                travellerId={person.id}
                docs={props.docs}
                onStartCapture={props.onStartCapture}
                onDelete={props.onDelete}
                savedDocId={props.savedDocId}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------- workspace */

export function DocumentsWorkspace({ option }: { option: DocumentsOption }) {
  const [docs, setDocs] = useState<TravellerDocument[]>(travellerDocuments);
  const [capture, setCapture] = useState<CaptureState | null>(null);
  const [savedDocId, setSavedDocId] = useState<string | null>(null);
  const [vaultOpen, setVaultOpen] = useState(false);
  const [inboxOpen, setInboxOpen] = useState(true);
  const [exportOpen, setExportOpen] = useState(false);
  const [includeDocs, setIncludeDocs] = useState(false);
  const [reveal, setReveal] = useState(false);

  useEffect(() => {
    setDocs(travellerDocuments);
    setCapture(null);
    setSavedDocId(null);
    setVaultOpen(false);
    setInboxOpen(true);
    setExportOpen(false);
    setIncludeDocs(false);
    setReveal(false);
  }, [option]);

  useEffect(() => {
    if (!capture || capture.stage === "review") return undefined;
    const next: Record<CaptureStage, CaptureStage | null> = {
      reading: "extracting",
      extracting: "review",
      review: null,
      saved: null,
    };
    const target = next[capture.stage];
    if (!target) return undefined;
    const timer = window.setTimeout(() => {
      setCapture((current) => (current ? { ...current, stage: target } : current));
    }, capture.stage === "reading" ? 700 : 1100);
    return () => window.clearTimeout(timer);
  }, [capture]);

  const startCapture = useCallback(
    (travellerId: string, label: string, fileName: string) => {
      if (option === "vault") setVaultOpen(true);
      if (option === "inbox") setInboxOpen(true);
      setSavedDocId(null);
      setCapture({ travellerId, label, fileName, stage: "reading", fields: pendingExtraction, remember: true });
    },
    [option],
  );

  const saveCapture = useCallback(() => {
    if (!capture) return;
    const id = `doc-${capture.travellerId}-${capture.label.toLowerCase()}`;
    setDocs((current) => [
      ...current,
      {
        id,
        travellerId: capture.travellerId,
        kind: "passport",
        title: capture.label,
        issuer: "India",
        expiry: "2030-01-09",
        expiryLabel: "09 Jan 2030",
        capturedOn: "just now",
        fields: capture.fields,
      },
    ]);
    setSavedDocId(id);
    setCapture((current) => (current ? { ...current, stage: "saved" } : current));
    window.setTimeout(() => setCapture(null), 2200);
  }, [capture]);

  const surfaceProps: SurfaceProps = {
    docs,
    capture,
    savedDocId,
    onStartCapture: startCapture,
    onDelete: (id) => setDocs((current) => current.filter((doc) => doc.id !== id)),
    onToggleRemember: () => setCapture((current) => (current ? { ...current, remember: !current.remember } : current)),
    onSaveCapture: saveCapture,
    onCancelCapture: () => setCapture(null),
  };

  const columns =
    option === "readiness"
      ? "lg:grid-cols-[minmax(15rem,22%)_minmax(0,1fr)_minmax(19rem,27%)]"
      : "lg:grid-cols-[minmax(16rem,24%)_minmax(0,1fr)_minmax(15rem,21%)]";

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[#eef1ef]">
      <header className="relative z-30 flex h-12 shrink-0 items-center gap-2 border-b border-[#dce2df] bg-[#fbfcfb]/95 px-3 backdrop-blur">
        <button
          type="button"
          className="inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-[#d6ddda] bg-white px-2.5 text-xs font-semibold text-ink shadow-sm"
        >
          {tripLabel}
          <ChevronDown size={13} aria-hidden />
        </button>
        {option === "vault" ? (
          <button
            type="button"
            onClick={() => setVaultOpen(true)}
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-rose-50 px-2.5 text-xs font-semibold text-rose-700 ring-1 ring-rose-200"
            {...marker("Trip shows only the gap, never the document manager")}
          >
            <AlertTriangle size={13} aria-hidden /> {blockerCount} documents to fix
          </button>
        ) : (
          <span className="hidden truncate text-[11px] font-medium text-accent lg:inline">
            Saved · 2 of 7 bookings confirmed
          </span>
        )}
        <nav className="ml-auto flex shrink-0 items-center gap-1" aria-label="Workspace controls">
          {[List, MapIcon, PanelRight, MessageCircle].map((Icon, index) => (
            <span
              key={index}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100"
            >
              <Icon size={14} aria-hidden />
            </span>
          ))}
          <span className="mx-1 h-5 w-px bg-slate-200" aria-hidden />
          <button
            type="button"
            onClick={() => setExportOpen(true)}
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-brand/10 px-3 text-xs font-semibold text-brand"
          >
            <Download size={13} aria-hidden /> Export
          </button>
          <button
            type="button"
            onClick={() => option === "vault" && setVaultOpen(true)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100"
            aria-label="Account"
          >
            <CircleUserRound size={15} aria-hidden />
          </button>
        </nav>
      </header>

      <div className={`grid min-h-0 flex-1 grid-cols-1 ${columns}`}>
        <ItineraryPane />
        <MapPane />
        {option === "readiness" ? <ReadinessRail {...surfaceProps} /> : <DetailsRail />}
      </div>

      {option === "inbox" ? <InboxDock {...surfaceProps} open={inboxOpen} onToggle={() => setInboxOpen((v) => !v)} /> : null}
      {option === "vault" && vaultOpen ? <VaultSheet {...surfaceProps} onClose={() => setVaultOpen(false)} /> : null}
      {exportOpen ? (
        <ExportSheet
          include={includeDocs}
          reveal={reveal}
          onToggleInclude={() => setIncludeDocs((value) => !value)}
          onToggleReveal={() => setReveal((value) => !value)}
          onClose={() => setExportOpen(false)}
        />
      ) : null}

      <div className="pointer-events-none absolute bottom-3 left-3 z-30 flex items-center gap-1.5 rounded-full bg-ink/85 px-3 py-1.5 text-[10px] font-semibold text-white">
        <Sparkles size={11} aria-hidden />
        {option === "readiness"
          ? "Everything about documents lives in this trip"
          : option === "vault"
            ? "Documents belong to you, the trip only shows gaps"
            : "Drop first, sort later"}
      </div>
    </div>
  );
}
