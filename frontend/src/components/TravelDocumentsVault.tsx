import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  FileText,
  Loader2,
  Lock,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import {
  clearTravelDocuments,
  deleteTravelDocument,
  extractTravelDocument,
  fetchDocumentReadiness,
  fetchTravelDocuments,
  saveTravelDocument,
  type DocumentKind,
  type DocumentReadiness,
  type ProposedField,
  type ReadinessCheck,
  type TravelDocument,
} from "../api";

const TYPE_ORDER: DocumentKind[] = [
  "passport",
  "visa",
  "insurance",
  "vaccination",
  "licence",
  "idp",
  "loyalty",
];

const TYPE_LABELS: Record<DocumentKind, string> = {
  passport: "Passport",
  visa: "Visa",
  insurance: "Travel insurance",
  vaccination: "Vaccination certificate",
  licence: "Driving licence",
  idp: "International Driving Permit",
  loyalty: "Loyalty programme",
};

const FIELD_LABELS: Record<string, string> = {
  holder_name: "Name",
  issuing_country: "Issuing country",
  nationality: "Nationality",
  number_last4: "Document number",
  date_of_birth: "Date of birth",
  expiry: "Expiry",
  destination_country: "Valid for",
  entry_type: "Entries",
  valid_from: "Valid from",
  valid_to: "Valid to",
  max_stay_days: "Max stay per entry",
  provider: "Provider",
  policy_reference: "Policy number",
  medical_cover_amount: "Medical cover",
  currency: "Currency",
  assistance_phone: "Assistance line",
  vaccine: "Vaccine",
  administered_on: "Given on",
  certificate_reference: "Certificate",
  categories: "Categories",
  linked_licence: "Linked licence",
  program: "Programme",
  membership_reference: "Membership",
  tier: "Tier",
};

type Stage = "idle" | "reading" | "extracting" | "review" | "saving" | "saved";

interface Traveller {
  key: string;
  name: string;
  relationship: string;
}

function confidenceTone(confidence: number): string {
  if (confidence >= 0.97) return "text-emerald-700 bg-emerald-50 ring-emerald-200";
  if (confidence >= 0.92) return "text-amber-700 bg-amber-50 ring-amber-200";
  return "text-rose-700 bg-rose-50 ring-rose-200";
}

function formatDate(value: string): string {
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

async function fileToBase64(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function SeverityDot({ severity }: { severity: ReadinessCheck["severity"] }) {
  const tone =
    severity === "blocker" ? "bg-rose-500" : severity === "warning" ? "bg-amber-500" : "bg-emerald-500";
  return <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${tone}`} aria-hidden />;
}

function CheckRow({ check }: { check: ReadinessCheck }) {
  return (
    <li className="flex gap-2 py-2">
      <SeverityDot severity={check.severity} />
      <div className="min-w-0">
        <p className="text-xs font-semibold text-slate-800">{check.title}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-slate-600">{check.detail}</p>
        <div className="mt-1 flex flex-wrap items-center gap-1">
          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">
            {check.rule}
          </span>
          <span className="text-[10px] text-slate-500">Computed here</span>
        </div>
        {check.action && <p className="mt-1 text-[11px] text-slate-500">{check.action}</p>}
      </div>
    </li>
  );
}

function DocumentRow({
  document,
  onDelete,
}: {
  document: TravelDocument;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const expiry = String(document.fields.expiry ?? document.fields.valid_to ?? "");
  const soon = expiry !== "" && new Date(`${expiry}T00:00:00`) < new Date(Date.now() + 15552000000);
  const entries = Object.entries(document.fields);

  return (
    <li className="rounded-lg border border-slate-200 bg-white p-2.5">
      <div className="flex items-start gap-2">
        <FileText size={15} className="mt-0.5 shrink-0 text-slate-400" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-slate-800">
            {TYPE_LABELS[document.type] ?? document.type}
          </p>
          <p className="truncate text-[11px] text-slate-500">
            {String(document.fields.issuing_country ?? document.fields.provider ?? "")}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {expiry && (
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] font-medium ring-1 ${
                  soon ? "bg-rose-50 text-rose-700 ring-rose-200" : "bg-slate-50 text-slate-600 ring-slate-200"
                }`}
              >
                Expires {formatDate(expiry)}
              </span>
            )}
            <span className="inline-flex items-center gap-1 rounded bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-500 ring-1 ring-slate-200">
              <Lock size={9} aria-hidden /> Fields only
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium text-slate-500 hover:bg-slate-50"
        >
          {open ? "Hide" : "View"}
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="shrink-0 rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
          aria-label={`Delete ${TYPE_LABELS[document.type] ?? document.type}`}
        >
          <Trash2 size={13} aria-hidden />
        </button>
      </div>
      {open && (
        <div className="mt-2 border-t border-slate-100 pt-2">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            {entries.map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="text-[11px] text-slate-500">{FIELD_LABELS[key] ?? key}</dt>
                <dd className="text-[11px] font-medium text-slate-800">
                  {String(value)}
                  {key === "number_last4" && (
                    <span className="ml-1 text-[10px] font-normal text-slate-400">last 4</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-[10px] leading-relaxed text-slate-400">
            Captured {new Date(document.provenance.captured_at).toLocaleDateString()}. The original
            was read once and discarded — these fields are all that exist.
          </p>
        </div>
      )}
    </li>
  );
}

function CaptureCard({
  traveller,
  onCancel,
  onSaved,
}: {
  traveller: Traveller;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [type, setType] = useState<DocumentKind>("passport");
  const [stage, setStage] = useState<Stage>("idle");
  const [fields, setFields] = useState<ProposedField[]>([]);
  const [sourceKind, setSourceKind] = useState<"image" | "text">("image");
  const [pasted, setPasted] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);

  const run = useCallback(
    async (input: { contentBase64?: string; text?: string }) => {
      setError("");
      setStage("extracting");
      try {
        const result = await extractTravelDocument(type, input);
        setFields(result.fields);
        setSourceKind(result.source_kind);
        setStage("review");
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "The document could not be read.");
        setStage("idle");
      }
    },
    [type],
  );

  async function onFile(file: File | undefined) {
    if (!file) return;
    setStage("reading");
    setError("");
    try {
      const contentBase64 = await fileToBase64(file);
      await run({ contentBase64 });
    } catch {
      setError("That file could not be read.");
      setStage("idle");
    }
  }

  async function save() {
    setStage("saving");
    try {
      const payload: Record<string, string | number> = {};
      for (const field of fields) payload[field.key] = field.value;
      const lowest = fields.reduce((min, field) => Math.min(min, field.confidence), 1);
      await saveTravelDocument({
        type,
        traveller_key: traveller.key,
        traveller_name: traveller.name,
        fields: payload,
        provenance: { source_kind: sourceKind, confidence: lowest, confirmed_by_user: true },
      });
      setStage("saved");
      window.setTimeout(onSaved, 900);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save these details.");
      setStage("review");
    }
  }

  if (stage === "reading" || stage === "extracting") {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
        <p className="flex items-center gap-2 text-xs font-semibold text-slate-700">
          <Loader2 size={14} className="animate-spin" aria-hidden />
          {stage === "reading" ? "Reading the file" : "Pulling out the fields"}
        </p>
        <p className="mt-1 text-[11px] text-slate-500">Nothing has been stored yet.</p>
      </div>
    );
  }

  if (stage === "saved") {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-700">
        <Check size={14} aria-hidden /> {TYPE_LABELS[type]} saved
      </div>
    );
  }

  if (stage === "review" || stage === "saving") {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-3">
        <p className="text-xs font-semibold text-slate-800">Check what we read</p>
        <div className="mt-2 space-y-2">
          {fields.map((field, index) => (
            <label key={field.key} className="block">
              <span className="flex items-center justify-between text-[11px] text-slate-500">
                {field.label}
                <span
                  className={`rounded px-1 py-0.5 text-[10px] font-medium ring-1 ${confidenceTone(field.confidence)}`}
                >
                  {Math.round(field.confidence * 100)}%
                </span>
              </span>
              <input
                value={String(field.value)}
                onChange={(event) => {
                  const next = [...fields];
                  next[index] = { ...field, value: event.target.value };
                  setFields(next);
                }}
                className="mt-0.5 w-full rounded border border-slate-200 px-2 py-1 text-xs text-slate-800 focus:border-brand focus:outline-none"
              />
            </label>
          ))}
        </div>
        <p className="mt-2 flex gap-1.5 text-[10px] leading-relaxed text-slate-500">
          <Lock size={11} className="mt-0.5 shrink-0" aria-hidden />
          The file is deleted when you save. Only the fields above are kept, and the number keeps
          its last four digits.
        </p>
        {error && <p className="mt-2 text-[11px] text-rose-600">{error}</p>}
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => void save()}
            disabled={stage === "saving"}
            className="btn-primary h-8 flex-1 rounded-md text-xs disabled:opacity-60"
          >
            {stage === "saving" ? "Saving…" : "Save details"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="h-8 rounded-md px-3 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            Discard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-800">
          Add a document for {traveller.name.split(" ")[0]}
        </p>
        <button
          type="button"
          onClick={onCancel}
          className="rounded p-0.5 text-slate-400 hover:bg-slate-100"
          aria-label="Cancel"
        >
          <X size={13} aria-hidden />
        </button>
      </div>
      <label className="mt-2 block text-[11px] text-slate-500">
        Document type
        <select
          value={type}
          onChange={(event) => setType(event.target.value as DocumentKind)}
          className="mt-0.5 w-full rounded border border-slate-200 px-2 py-1 text-xs text-slate-800"
        >
          {TYPE_ORDER.map((kind) => (
            <option key={kind} value={kind}>
              {TYPE_LABELS[kind]}
            </option>
          ))}
        </select>
      </label>
      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/heic"
        className="hidden"
        onChange={(event) => void onFile(event.target.files?.[0])}
      />
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        className="mt-2 w-full rounded-md border border-dashed border-slate-300 py-2 text-xs font-medium text-slate-600 hover:border-brand hover:text-brand"
      >
        Take or choose a photo
      </button>
      <label className="mt-2 block text-[11px] text-slate-500">
        …or paste the text
        <textarea
          value={pasted}
          onChange={(event) => setPasted(event.target.value)}
          rows={3}
          className="mt-0.5 w-full rounded border border-slate-200 px-2 py-1 text-xs text-slate-800"
        />
      </label>
      <button
        type="button"
        disabled={!pasted.trim()}
        onClick={() => void run({ text: pasted })}
        className="mt-1.5 rounded-md px-2 py-1 text-xs font-semibold text-brand disabled:text-slate-300"
      >
        Read the pasted text
      </button>
      {error && <p className="mt-2 text-[11px] text-rose-600">{error}</p>}
    </div>
  );
}

export default function TravelDocumentsVault() {
  const [documents, setDocuments] = useState<TravelDocument[]>([]);
  const [readiness, setReadiness] = useState<DocumentReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [capturingFor, setCapturingFor] = useState<Traveller | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    try {
      const [docs, checks] = await Promise.all([
        fetchTravelDocuments(),
        fetchDocumentReadiness().catch(() => null),
      ]);
      setDocuments(docs.documents);
      setReadiness(checks);
      setError("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load your document details.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const travellers = useMemo<Traveller[]>(() => {
    const fromTrip = readiness?.travellers ?? [];
    const seen = new Map<string, Traveller>();
    for (const person of fromTrip) seen.set(person.key, person);
    for (const document of documents) {
      if (seen.has(document.traveller_key)) continue;
      seen.set(document.traveller_key, {
        key: document.traveller_key,
        name: document.traveller_name || "You",
        relationship: "",
      });
    }
    if (!seen.size) seen.set("self", { key: "self", name: "You", relationship: "" });
    return [...seen.values()];
  }, [documents, readiness]);

  const attention = (readiness?.checks ?? []).filter((check) => check.severity !== "ok");

  async function remove(id: string) {
    await deleteTravelDocument(id);
    window.dispatchEvent(new Event("tripplanner:documents-changed"));
    await reload();
  }

  async function removeAll() {
    if (!window.confirm("Delete every document detail on this account?")) return;
    await clearTravelDocuments();
    window.dispatchEvent(new Event("tripplanner:documents-changed"));
    await reload();
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <p className="rounded-lg bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-slate-600">
        We keep the details we read, never the document. Every trip you plan is checked against
        these automatically.
      </p>

      {loading && <p className="mt-4 text-xs text-slate-500">Loading…</p>}
      {error && <p className="mt-4 text-xs text-rose-600">{error}</p>}

      {attention.length > 0 && (
        <section className="mt-4">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
            <AlertTriangle size={13} className="text-rose-500" aria-hidden />
            This trip needs attention
          </h3>
          <ul className="mt-1 divide-y divide-slate-100">
            {attention.map((check) => (
              <CheckRow key={check.id} check={check} />
            ))}
          </ul>
        </section>
      )}

      {attention.length === 0 && readiness?.crosses_border === false && readiness.origin_country && (
        <p className="mt-4 rounded-md bg-slate-50 px-2.5 py-2 text-[11px] text-slate-600">
          This trip stays inside {readiness.origin_country}, so no passport, visa, or driving
          permit checks apply to it.
        </p>
      )}

      {travellers.map((traveller) => {
        const owned = documents
          .filter((document) => document.traveller_key === traveller.key)
          .sort((a, b) => TYPE_ORDER.indexOf(a.type) - TYPE_ORDER.indexOf(b.type));
        const hasPassport = owned.some((document) => document.type === "passport");
        return (
          <section key={traveller.key} className="mt-5">
            <div className="flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-600">
                {initials(traveller.name)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold text-slate-800">{traveller.name}</p>
                {traveller.relationship && (
                  <p className="truncate text-[11px] text-slate-500">{traveller.relationship}</p>
                )}
              </div>
              {!hasPassport && (
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 ring-1 ring-slate-200">
                  Nothing on file
                </span>
              )}
            </div>
            <ul className="mt-2 space-y-1.5">
              {owned.map((document) => (
                <DocumentRow
                  key={document.id}
                  document={document}
                  onDelete={() => void remove(document.id)}
                />
              ))}
            </ul>
            {capturingFor?.key === traveller.key ? (
              <div className="mt-2">
                <CaptureCard
                  traveller={traveller}
                  onCancel={() => setCapturingFor(null)}
                  onSaved={() => {
                    setCapturingFor(null);
                    window.dispatchEvent(new Event("tripplanner:documents-changed"));
                    void reload();
                  }}
                />
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setCapturingFor(traveller)}
                className="mt-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-brand hover:bg-brand/5"
              >
                <Plus size={13} aria-hidden /> Add a document for {traveller.name.split(" ")[0]}
              </button>
            )}
          </section>
        );
      })}

      {documents.length > 0 && (
        <button
          type="button"
          onClick={() => void removeAll()}
          className="mt-6 w-full rounded-md border border-rose-200 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-50"
        >
          Delete every document detail
        </button>
      )}
      <p className="mt-3 pb-4 text-[10px] leading-relaxed text-slate-400">
        None of this is ever included in a share link, and full identity numbers are never stored.
      </p>
    </div>
  );
}
