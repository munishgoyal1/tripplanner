import { Calendar, Check, Download, Eye, Mail, Printer, X } from "lucide-react";
import { useRef, useState } from "react";
import { trackEvent } from "../analytics";
import type { ExportTemplate } from "../api";
import { downloadTripPdf, emailTripExport, tripExportUrl, tripIcsUrl } from "../api";

interface FormatOption {
  id: ExportTemplate | "calendar";
  label: string;
  description: string;
  supportsMap: boolean;
}

const FORMATS: FormatOption[] = [
  {
    id: "standard",
    label: "Standard",
    description: "The familiar day-by-day list: time, place, address, note.",
    supportsMap: false,
  },
  {
    id: "detailed",
    label: "Detailed+",
    description: "Adds day-by-day map circuits plus a weather and budget summary.",
    supportsMap: true,
  },
  {
    id: "trip_book",
    label: "Trip Book",
    description: "The full pack: a trip overview map, day circuits, essentials, and your saved travel documents.",
    supportsMap: true,
  },
  {
    id: "trip_card",
    label: "Trip Card",
    description: "One page per trip: a condensed day-by-day cheat sheet for a quick glance.",
    supportsMap: false,
  },
  {
    id: "calendar",
    label: "Calendar+",
    description: "Each timed stop as a real event in your phone's calendar app, with reminders.",
    supportsMap: false,
  },
];

export default function ExportModal({ onClose }: { onClose: () => void }) {
  const [format, setFormat] = useState<FormatOption["id"]>("standard");
  const [includePhotos, setIncludePhotos] = useState(false);
  const [includeCircuit, setIncludeCircuit] = useState(true);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [mailtoHref, setMailtoHref] = useState("");
  const emailRequestRef = useRef<{ key: string; requestId: string } | null>(null);

  const active = FORMATS.find((item) => item.id === format)!;
  const isCalendar = format === "calendar";
  const options = {
    include_photos: includePhotos,
    include_map_circuit: includeCircuit,
    template: (isCalendar ? "standard" : format) as ExportTemplate,
  };

  const openPrintView = () => {
    trackEvent("itinerary_exported", { method: "print", format });
    window.open(tripExportUrl(options, true), "_blank", "noopener,noreferrer");
  };

  const openPreview = () => {
    trackEvent("itinerary_exported", { method: "preview", format });
    window.open(tripExportUrl(options, false), "_blank", "noopener,noreferrer");
  };

  const downloadCalendar = () => {
    trackEvent("itinerary_exported", { method: "calendar", format });
    window.open(tripIcsUrl(), "_blank", "noopener,noreferrer");
  };

  const downloadPdf = async () => {
    setBusy(true);
    setStatus("");
    try {
      const result = await downloadTripPdf(options);
      if (!result.ok) {
        if (result.error === "pdf_renderer_not_installed") {
          setStatus("Direct PDF download is not available yet on this server. Opening the print view instead.");
          openPrintView();
          return;
        }
        setStatus(result.message || "Could not generate the PDF.");
        return;
      }
      const href = URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = result.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
      trackEvent("itinerary_exported", { method: "pdf", format });
    } finally {
      setBusy(false);
    }
  };

  const sendEmail = async () => {
    if (!email.trim()) {
      setStatus("Enter an email address first.");
      return;
    }
    setBusy(true);
    setStatus("");
    setMailtoHref("");
    try {
      const requestKey = JSON.stringify({ email: email.trim().toLowerCase(), ...options });
      if (emailRequestRef.current?.key !== requestKey) {
        emailRequestRef.current = { key: requestKey, requestId: crypto.randomUUID() };
      }
      const result = await emailTripExport(
        email.trim(),
        options,
        emailRequestRef.current.requestId,
      );
      if (result.ok) {
        emailRequestRef.current = null;
        setStatus(result.message || "Export sent.");
        trackEvent("itinerary_exported", { method: "email", format });
        return;
      }
      if (result.mailto) {
        setMailtoHref(result.mailto);
        window.location.href = result.mailto;
        setStatus(
          result.error === "email_not_configured"
            ? "Direct email sending is not configured on this server. Tried opening your mail app instead."
            : "Opened your mail client fallback.",
        );
      } else {
        setStatus(result.message || "Could not send email.");
      }
    } catch {
      setStatus("Could not send email. Retry to safely check the same delivery attempt.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink">Download itinerary</h2>
          <button type="button" onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full text-slate-400 hover:bg-slate-50 hover:text-ink" aria-label="Close export dialog">
            <X size={17} aria-hidden />
          </button>
        </div>

        <div className="space-y-1.5">
          {FORMATS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setFormat(item.id)}
              className={`flex w-full items-start gap-2 rounded-xl border p-2.5 text-left transition ${
                format === item.id ? "border-brand bg-brand-50/60" : "border-slate-200 hover:bg-slate-50"
              }`}
            >
              <span className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border ${format === item.id ? "border-brand bg-brand text-white" : "border-slate-300"}`}>
                {format === item.id && <Check size={11} aria-hidden />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-ink">{item.label}</span>
                <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">{item.description}</span>
              </span>
            </button>
          ))}
        </div>

        <div className="mt-3 space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
          {!isCalendar && (
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={includePhotos} onChange={(event) => setIncludePhotos(event.target.checked)} />
              Include one photo per attraction/city (default off)
            </label>
          )}
          {!isCalendar && active.supportsMap && (
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={includeCircuit} onChange={(event) => setIncludeCircuit(event.target.checked)} />
              Include day-wise map circuit and route stats
            </label>
          )}
          {isCalendar && (
            <p className="text-xs text-slate-500">Adds one event per timed stop, with its address, to your calendar app.</p>
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {isCalendar ? (
            <button type="button" onClick={downloadCalendar} className="btn-primary">
              <Calendar size={15} aria-hidden /> Download .ics
            </button>
          ) : (
            <>
              <button type="button" onClick={openPreview} className="btn-ghost">
                <Eye size={15} aria-hidden /> Preview
              </button>
              <button type="button" onClick={openPrintView} className="btn-ghost">
                <Printer size={15} aria-hidden /> Print / Save PDF
              </button>
              <button type="button" onClick={downloadPdf} disabled={busy} className="btn-primary disabled:opacity-50">
                <Download size={15} aria-hidden /> {busy ? "Preparing..." : "Download PDF"}
              </button>
            </>
          )}
        </div>

        {!isCalendar && (
          <div className="mt-5 border-t border-slate-200 pt-4">
            <p className="mb-2 text-sm font-medium text-ink">Send to email</p>
            <div className="flex gap-2">
              <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" className="input" />
              <button type="button" onClick={sendEmail} disabled={busy} className="btn-primary whitespace-nowrap disabled:opacity-50">
                <Mail size={15} aria-hidden /> {busy ? "Sending..." : "Send"}
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              If server email is not configured, your mail app will open with a prefilled draft.
            </p>
          </div>
        )}
        {status && <p className="mt-2 text-xs text-slate-600">{status}</p>}
        {mailtoHref && (
          <p className="mt-2 text-xs text-slate-600">
            If nothing opened, <a href={mailtoHref} className="text-brand underline underline-offset-2">open the mail draft directly</a>.
          </p>
        )}
      </div>
    </div>
  );
}
