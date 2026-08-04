import { BedDouble, Compass, Search, Sparkles, Utensils } from "lucide-react";

export type BrowseKind = "hotel" | "attraction" | "restaurant";
export type KindTab = "highlights" | BrowseKind;

const KIND_TABS: { id: KindTab; label: string; icon: typeof Compass }[] = [
  { id: "highlights", label: "Highlights", icon: Sparkles },
  { id: "hotel", label: "Hotels", icon: BedDouble },
  { id: "attraction", label: "Attractions", icon: Compass },
  { id: "restaurant", label: "Food", icon: Utensils },
];

interface Props {
  cities: string[];
  city: string;
  kind: KindTab;
  query: string;
  onCity: (city: string) => void;
  onKind: (kind: KindTab) => void;
  onQuery: (query: string) => void;
}

export default function GuideScopeBar({ cities, city, kind, query, onCity, onKind, onQuery }: Props) {
  return (
    <div>
      <label className="flex h-9 items-center gap-2 rounded-md bg-slate-50 px-3 ring-1 ring-inset ring-slate-200">
        <Search size={14} className="text-slate-400" aria-hidden />
        <input
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          placeholder="Search all trip places"
          className="min-w-0 flex-1 bg-transparent text-xs outline-none"
          aria-label="Search all trip places"
        />
      </label>

      {cities.length > 1 && (
        <div className="mt-2 flex gap-1 overflow-x-auto pb-1">
          {["all", ...cities].map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => onCity(item)}
              aria-pressed={city === item}
              className={`h-7 shrink-0 rounded-md px-2.5 text-[11px] font-semibold ${
                city === item ? "bg-ink text-white" : "bg-slate-50 text-slate-500 hover:bg-slate-100"
              }`}
            >
              {item === "all" ? "All cities" : item}
            </button>
          ))}
        </div>
      )}

      <div className="mt-2 grid grid-cols-4 gap-1 rounded-md bg-slate-50 p-1">
        {KIND_TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => onKind(id)}
            aria-pressed={kind === id}
            className={`flex h-8 items-center justify-center gap-1 rounded-[5px] text-[10px] font-semibold ${
              kind === id ? "bg-white text-ink shadow-sm" : "text-slate-500"
            }`}
          >
            <Icon size={12} aria-hidden />
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
