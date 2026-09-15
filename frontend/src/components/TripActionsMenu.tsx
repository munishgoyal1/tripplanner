import { CalendarPlus, ChevronDown, Download, FileDown, Link2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { trackEvent } from "../analytics";
import { shareActiveTrip, tripIcsUrl } from "../api";

interface Props {
  disabled?: boolean;
  onExport: () => void;
  compactTrigger?: boolean;
}

export default function TripActionsMenu({ disabled = false, onExport, compactTrigger = false }: Props) {
  const [open, setOpen] = useState(false);
  const [shareStatus, setShareStatus] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const share = async () => {
    setShareStatus("Creating link...");
    try {
      const url = await shareActiveTrip();
      trackEvent("trip_shared");
      try {
        await navigator.clipboard.writeText(url);
        setShareStatus("Link copied");
      } catch {
        setShareStatus(url);
      }
    } catch (error) {
      setShareStatus(String((error as Error).message || error));
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        className={compactTrigger
          ? "inline-flex h-7 items-center justify-center gap-0.5 rounded-full px-2 text-muted transition hover:bg-sand hover:text-ink disabled:opacity-40"
          : "btn-ghost disabled:opacity-40"}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="Trip actions"
        title="Export, share, or add this trip to your calendar"
      >
        <Download size={15} aria-hidden />
        {!compactTrigger && <span className="hidden 2xl:inline">Trip actions</span>}
        <ChevronDown size={13} aria-hidden />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-[80] mt-1 w-64 overflow-hidden rounded-xl border border-border bg-paper p-1.5 shadow-pop"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onExport();
            }}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink hover:bg-sand"
          >
            <FileDown size={16} className="text-muted" aria-hidden />
            <span>
              <strong className="block font-medium">Export itinerary</strong>
              <small className="text-muted">Preview, PDF, or email</small>
            </span>
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => void share()}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink hover:bg-sand"
          >
            <Link2 size={16} className="text-muted" aria-hidden />
            <span>
              <strong className="block font-medium">Share trip</strong>
              <small className="text-muted">Copy a read-only link</small>
            </span>
          </button>
          <a
            role="menuitem"
            href={tripIcsUrl()}
            download
            onClick={() => trackEvent("calendar_exported")}
            className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink hover:bg-sand"
          >
            <CalendarPlus size={16} className="text-muted" aria-hidden />
            <span>
              <strong className="block font-medium">Add to calendar</strong>
              <small className="text-muted">Download calendar file</small>
            </span>
          </a>
          {shareStatus && (
            <p
              role="status"
              className="mx-2 mt-1 truncate border-t border-border/60 px-1 pt-2 text-[11px] text-muted"
              title={shareStatus}
            >
              {shareStatus}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
