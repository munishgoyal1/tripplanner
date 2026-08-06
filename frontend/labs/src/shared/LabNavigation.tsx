import { Archive, ArrowLeft, FlaskConical, ListChecks, PauseCircle, ScanSearch, Trash2 } from "lucide-react";
import { allLabs } from "./labRecords";

type LabSection = "catalog" | "active" | "implemented-review" | "parked" | "discarded" | "completed";

type LabNavigationProps =
  | { current?: LabSection; detail?: false; labId?: never }
  | { current?: never; detail: true; labId: string };

export function LabNavigation({ current = "active", detail = false, labId }: LabNavigationProps) {
  if (detail) {
    const lab = allLabs.find((candidate) => candidate.id === labId);
    if (!lab) throw new Error(`Unknown Lab: ${labId}`);

    return (
      <nav className="flex w-full items-center justify-between gap-3" aria-label="Lab navigation">
        <a href="./catalog.html" className="inline-flex h-8 items-center gap-1.5 rounded-sm bg-white px-2.5 text-xs font-semibold text-slate-600 shadow-card ring-1 ring-slate-200 transition hover:text-brand hover:ring-brand/30">
          <ArrowLeft size={13} aria-hidden /> Back to All Open Labs
        </a>
        <span className="inline-flex h-8 items-center rounded-sm bg-ink px-2.5 text-xs font-bold text-white">
          Lab #{lab.labNumber}
        </span>
      </nav>
    );
  }

  const links = [
    { id: "catalog", label: "All Open Labs", href: "./catalog.html", icon: FlaskConical },
    { id: "active", label: "In progress", href: "./catalog.html?view=active", icon: ListChecks },
    { id: "implemented-review", label: "Implemented review", href: "./catalog.html?view=implemented-review", icon: ScanSearch },
    { id: "parked", label: "Parked", href: "./catalog.html?view=parked", icon: PauseCircle },
    { id: "discarded", label: "Discarded", href: "./catalog.html?view=discarded", icon: Trash2 },
    { id: "completed", label: "Completed", href: "./completed-labs.html", icon: Archive },
  ] as const;

  return (
    <nav className="flex flex-wrap items-center gap-1 rounded-md bg-white p-1 shadow-card ring-1 ring-slate-200" aria-label="UX Labs navigation">
      {links.map(({ id, label, href, icon: Icon }) => (
        <a
          key={id}
          href={href}
          aria-current={current === id ? "page" : undefined}
          className={`inline-flex h-8 items-center gap-1.5 rounded-sm px-2.5 text-xs font-semibold transition ${current === id ? "bg-ink text-white" : "text-slate-500 hover:bg-slate-50 hover:text-ink"}`}
        >
          <Icon size={13} aria-hidden />
          {label}
        </a>
      ))}
    </nav>
  );
}