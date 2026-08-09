import { Route } from "lucide-react";

export default function BrandIdentity({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5" aria-label="AI Tripplanner Beta">
      <span
        className={`grid shrink-0 place-items-center rounded-lg bg-brand text-white shadow-sm ${
          compact ? "h-7 w-7" : "h-9 w-9"
        }`}
        aria-hidden
      >
        <Route size={compact ? 17 : 21} strokeWidth={2.6} />
      </span>
      <span className={`display font-semibold leading-none text-ink ${compact ? "text-base" : "text-lg"}`}>
        AI Tripplanner
        <sup className="ml-1 align-super font-sans text-[8px] font-bold uppercase text-brand">Beta</sup>
      </span>
    </div>
  );
}