import { Archive, FlaskConical, ListChecks } from "lucide-react";

type LabSection = "catalog" | "active" | "completed";

export function LabNavigation({ current = "active" }: { current?: LabSection }) {
  const links = [
    { id: "catalog", label: "All labs", href: "./catalog.html", icon: FlaskConical },
    { id: "active", label: "In progress", href: "./catalog.html#active-labs", icon: ListChecks },
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