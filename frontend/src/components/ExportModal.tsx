import { Check, Download, Eye, Mail, X } from "lucide-react";
import { useRef, useState } from "react";
import { trackEvent } from "../analytics";
import type { ExportTemplate } from "../api";
import { downloadTripPdf, emailTripExport, tripExportUrl } from "../api";

interface FormatOption {
  id: ExportTemplate;
  label: string;
  description: string;
}

const FORMATS: FormatOption[] = [
  {
    id: "standard",
    label: "Standard",
    description: "The same day-by-day itinerary you see in the app, including times, visit length, hours, and notes.",
  },
  {
    id: "trip_book",
    label: "Trip Book",
    description: "A carry-along packet: contents and readiness, then the full days, then documents and place context.",
  },
];

export default function ExportModal({ onClose }: { onClose: () => void }) {
  const [format, setFormat] = useState<ExportTemplate>("standard");
  const [includePhotos, setIncludePhotos] = useState(false);
  const [includeBudgets, setIncludeBudgets] = useState(false);
  const [email, setEmail] = useState("");
  const [pdfBusy, setPdfBusy] = useState(false);
  const [emailBusy, setEmailBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [mailtoHref, setMailtoHref] = useState("");
  const emailRequestRef = useRef<{ key: string; requestId: string } | null>(null);

  const options = {
    include_photos: includePhotos,
    include_map_circuit: true,
    include_budgets: includeBudgets,
    template: format,
  };

  const openPreview = () => {
    trackEvent("itinerary_exported", { method: "preview", format });
    window.open(tripExportUrl(options, false), "_blank", "noopener,noreferrer");
  };

  const downloadPdf = async () => {
    setPdfBusy(true);
    setStatus("");
    try {
      const result = await downloadTripPdf(options);
      if (!result.ok) {
        if (result.error === "pdf_renderer_not_installed") {
          setStatus("Opening the preview so you can print or save a PDF from the browser.");
          openPreview();
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
      setPdfBusy(false);
    }
  };

  const sendEmail = async () => {
    if (!email.trim()) {
      setStatus("Enter an email address first.");
      return;
    }
    setEmailBusy(true);
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
      setEmailBusy(false);
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
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={includeBudgets} onChange={(event) => setIncludeBudgets(event.target.checked)} />
            Show budgets
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={includePhotos} onChange={(event) => setIncludePhotos(event.target.checked)} />
            Include 1 photo per stop
          </label>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={openPreview} className="btn-ghost">
            <Eye size={15} aria-hidden /> Preview
          </button>
          <button type="button" onClick={downloadPdf} disabled={pdfBusy} className="btn-primary disabled:opacity-50">
            <Download size={15} aria-hidden /> {pdfBusy ? "Preparing..." : "Download PDF"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Preview matches the PDF. Use your browser's print dialog from Preview if you need a paper copy.
        </p>

        <div className="mt-5 border-t border-slate-200 pt-4">
          <p className="mb-2 text-sm font-medium text-ink">Send to email</p>
          <div className="flex gap-2">
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" className="input" />
            <button type="button" onClick={sendEmail} disabled={emailBusy} className="btn-primary whitespace-nowrap disabled:opacity-50">
              <Mail size={15} aria-hidden /> {emailBusy ? "Sending..." : "Send"}
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Sends the PDF and a link to open this trip. If server email is not configured, your mail app opens instead.
          </p>
        </div>
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
