import { Download, Eye, Mail, Printer, X } from "lucide-react";
import { useRef, useState } from "react";
import { trackEvent } from "../analytics";
import { downloadTripPdf, emailTripExport, tripExportUrl } from "../api";

export default function ExportModal({ onClose }: { onClose: () => void }) {
  const [includePhotos, setIncludePhotos] = useState(true);
  const [includeCircuit, setIncludeCircuit] = useState(true);
  const [template, setTemplate] = useState<"minimal" | "detailed" | "family">("detailed");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [mailtoHref, setMailtoHref] = useState("");
  const emailRequestRef = useRef<{ key: string; requestId: string } | null>(null);

  const options = {
    include_photos: includePhotos,
    include_map_circuit: includeCircuit,
    template,
  };

  const openPrintView = () => {
    trackEvent("itinerary_exported", { method: "print" });
    window.open(tripExportUrl(options, true), "_blank", "noopener,noreferrer");
  };

  const openPreview = () => {
    trackEvent("itinerary_exported", { method: "preview" });
    window.open(tripExportUrl(options, false), "_blank", "noopener,noreferrer");
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
      trackEvent("itinerary_exported", { method: "pdf" });
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
        trackEvent("itinerary_exported", { method: "email" });
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
          <h2 className="text-lg font-semibold text-ink">Export itinerary</h2>
          <button type="button" onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full text-slate-400 hover:bg-slate-50 hover:text-ink" aria-label="Close export dialog">
            <X size={17} aria-hidden />
          </button>
        </div>

        <p className="mb-4 text-sm text-slate-600">
          Export a print-friendly day-wise itinerary. Use Print to save a PDF for the trip.
        </p>

        <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">Template</span>
            <select value={template} onChange={(event) => setTemplate(event.target.value as typeof template)} className="input">
              <option value="minimal">Minimal</option>
              <option value="detailed">Detailed</option>
              <option value="family">Family</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={includePhotos} onChange={(event) => setIncludePhotos(event.target.checked)} />
            Include place photos
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={includeCircuit} onChange={(event) => setIncludeCircuit(event.target.checked)} />
            Include day-wise map circuit and route stats
          </label>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={openPreview} className="btn-ghost">
            <Eye size={15} aria-hidden /> Preview
          </button>
          <button type="button" onClick={openPrintView} className="btn-primary">
            <Printer size={15} aria-hidden /> Print / Save PDF
          </button>
          <button type="button" onClick={downloadPdf} disabled={busy} className="btn-ghost disabled:opacity-50">
            <Download size={15} aria-hidden /> {busy ? "Preparing..." : "Download PDF"}
          </button>
        </div>

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
          {status && <p className="mt-2 text-xs text-slate-600">{status}</p>}
          {mailtoHref && (
            <p className="mt-2 text-xs text-slate-600">
              If nothing opened, <a href={mailtoHref} className="text-brand underline underline-offset-2">open the mail draft directly</a>.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
