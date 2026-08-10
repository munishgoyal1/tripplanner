import { useEffect, useState } from "react";
import {
  fetchPreferences,
  savePreferences,
  regenerateProfileSummary,
  type Preferences,
} from "../api";
import {
  displayCurrencyLabel,
  normalizeDisplayLanguage,
  normalizeDisplayRegion,
  supportedDisplayCurrencies,
  supportedDisplayLanguages,
  supportedDisplayRegions,
  writeDisplayPreferences,
} from "../lib/displayPreferences";

interface Props {
  onClose: () => void;
  embedded?: boolean;
}

const TRIP_STYLES = ["", "relaxed", "balanced", "packed", "luxury", "budget", "adventure"];
const BUDGET_LEVELS = ["", "shoestring", "budget", "moderate", "comfortable", "luxury"];
const FLIGHT_CLASSES = ["", "economy", "premium_economy", "business", "first"];
const DISPLAY_CURRENCIES = supportedDisplayCurrencies();
const DISPLAY_REGIONS = supportedDisplayRegions();
const DISPLAY_LANGUAGES = supportedDisplayLanguages();

function commaList(v: string[]): string {
  return v.join(", ");
}
function parseList(s: string): string[] {
  return s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

export default function SettingsModal({ onClose, embedded = false }: Props) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saving, setSaving] = useState(false);
  const [extracted, setExtracted] = useState<string[] | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [summaryConflict, setSummaryConflict] = useState(false);
  const [dirtyFields, setDirtyFields] = useState<Set<keyof Preferences>>(new Set());
  // Raw editable text for the comma-separated list fields. Kept separate from
  // the parsed arrays so a trailing comma isn't stripped mid-typing — parsed
  // into arrays only at save time.
  const [listText, setListText] = useState({ dietary: "", interests: "", dislikes: "" });

  function syncListText(p: Preferences) {
    setListText({
      dietary: commaList(p.dietary),
      interests: commaList(p.interests),
      dislikes: commaList(p.dislikes),
    });
  }

  useEffect(() => {
    fetchPreferences()
      .then((p) => {
        setPrefs(p);
        setDirtyFields(new Set());
        syncListText(p);
      })
      .catch(() => setPrefs(null));
  }, []);

  function set<K extends keyof Preferences>(key: K, value: Preferences[K]) {
    setDirtyFields((current) => new Set(current).add(key));
    setPrefs((p) => (p ? { ...p, [key]: value } : p));
  }

  function setList(key: "dietary" | "interests" | "dislikes", value: string) {
    setDirtyFields((current) => new Set(current).add(key));
    setListText((current) => ({ ...current, [key]: value }));
  }

  async function save() {
    if (!prefs) return;
    setSaving(true);
    try {
      const merged: Preferences = {
        ...prefs,
        dietary: parseList(listText.dietary),
        interests: parseList(listText.interests),
        dislikes: parseList(listText.dislikes),
      };
      setPrefs(merged);
      const updates: Partial<Preferences> = {};
      for (const key of dirtyFields) {
        Object.assign(updates, { [key]: merged[key] });
      }
      if (dirtyFields.has("profile_summary")) {
        updates.profile_summary_updated_at = prefs.profile_summary_updated_at ?? null;
      }
      const result = await savePreferences(updates);
      if (result.summary_conflict) {
        const fresh = await fetchPreferences();
        setPrefs(fresh);
        setDirtyFields(new Set());
        syncListText(fresh);
        setExtracted(null);
        setSummaryConflict(true);
        return;
      }
      writeDisplayPreferences({
        region: normalizeDisplayRegion(merged.display_region || merged.home_country || ""),
        language: normalizeDisplayLanguage(merged.display_language || "en"),
        currency: merged.display_currency || "USD",
      });
      if (result.about_me_extracted && result.about_me_extracted.length > 0) {
        // Re-load so the form reflects the structured fields the LLM filled
        // in, and surface a confirmation instead of closing immediately.
        setExtracted(result.about_me_extracted);
        const fresh = await fetchPreferences();
        setPrefs(fresh);
        setDirtyFields(new Set());
        syncListText(fresh);
      } else {
        onClose();
      }
    } finally {
      setSaving(false);
    }
  }

  async function regenerate() {
    if (!prefs) return;
    setRegenerating(true);
    try {
      const result = await regenerateProfileSummary();
      setPrefs((p) => (p ? { ...p, ...result } : p));
      setDirtyFields((current) => {
        const next = new Set(current);
        next.delete("profile_summary");
        return next;
      });
    } finally {
      setRegenerating(false);
    }
  }

  const content = (
    <>
        {!prefs ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : (
          <div className="space-y-4 text-sm">
            <Field label="About me (free text — the agent learns from this)">
              <textarea
                className="input min-h-[96px] resize-y"
                placeholder={
                  "Tell me about yourself and your travel style in plain words. " +
                  "e.g. I'm Munish from Bengaluru. I travel with my wife Priya and " +
                  "our 6-year-old son Aarav (vegetarian). We love beaches, hiking " +
                  "and good coffee, but hate crowded tourist traps and late nights."
                }
                value={prefs.about_me}
                onChange={(e) => set("about_me", e.target.value)}
              />
            </Field>
            {extracted && (
              <div className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                ✓ Saved. I picked up and filled in:{" "}
                <span className="font-medium">{extracted.join(", ")}</span>. These
                were added without removing anything you'd already set.
              </div>
            )}
            {summaryConflict && (
              <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Your profile summary changed while settings were open. The latest version is
                shown below; review it and save again.
              </div>
            )}
            <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-100">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500">
                  What I've learned about you
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={regenerate}
                    disabled={regenerating}
                    className="text-xs font-medium text-brand hover:underline disabled:opacity-40"
                  >
                    {regenerating ? "Thinking…" : "Regenerate"}
                  </button>
                  <button
                    type="button"
                    onClick={() => set("profile_summary", "")}
                    className="text-xs text-slate-400 hover:text-ink"
                  >
                    Reset
                  </button>
                </div>
              </div>
              <textarea
                className="input min-h-[80px] resize-y bg-white"
                placeholder={
                  "I keep a running summary of you here from our chats. It " +
                  "updates itself in the background — edit or reset it any time."
                }
                value={prefs.profile_summary}
                onChange={(e) => {
                  setSummaryConflict(false);
                  set("profile_summary", e.target.value);
                }}
              />
              <p className="mt-1 text-[11px] text-slate-400">
                This is my summary of you (distinct from “About me”, which is
                yours). I refresh it after our conversations; your edits stick.
              </p>
            </div>
            <Field label="Display name">
              <input
                className="input"
                value={prefs.display_name}
                onChange={(e) => set("display_name", e.target.value)}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Home city">
                <input
                  className="input"
                  value={prefs.home_city}
                  onChange={(e) => set("home_city", e.target.value)}
                />
              </Field>
              <Field label="Home country">
                <input
                  className="input"
                  value={prefs.home_country}
                  onChange={(e) => set("home_country", e.target.value)}
                />
              </Field>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="mb-2 text-xs font-semibold uppercase text-brand">Region and display</p>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Country or region">
                  <select className="input" value={normalizeDisplayRegion(prefs.display_region || prefs.home_country || "")} onChange={(e) => set("display_region", e.target.value)}>
                    <option value="">Detect from browser</option>
                    {DISPLAY_REGIONS.map((region) => <option key={region.code} value={region.code}>{region.label}</option>)}
                  </select>
                </Field>
                <Field label="Language">
                  <select className="input" value={normalizeDisplayLanguage(prefs.display_language || "en")} onChange={(e) => set("display_language", e.target.value)}>
                    {DISPLAY_LANGUAGES.map((language) => <option key={language.code} value={language.code}>{language.label}</option>)}
                  </select>
                </Field>
                <Field label="Display currency">
                  <select className="input" value={prefs.display_currency || "USD"} onChange={(e) => set("display_currency", e.target.value as Preferences["display_currency"])}>
                    {DISPLAY_CURRENCIES.map((currency) => <option key={currency} value={currency}>{displayCurrencyLabel(currency)}</option>)}
                  </select>
                </Field>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-500">Country and language set the example trip, dates, and units. Currency is independent, so you can stay in one country and price everything in another currency. Interface text is English for now, and none of this changes passport, visa, or provider rules.</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Trip style">
                <select
                  className="input"
                  value={prefs.trip_style}
                  onChange={(e) => set("trip_style", e.target.value)}
                >
                  {TRIP_STYLES.map((s) => (
                    <option key={s} value={s}>
                      {s || "—"}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Budget level">
                <select
                  className="input"
                  value={prefs.budget_level}
                  onChange={(e) => set("budget_level", e.target.value)}
                >
                  {BUDGET_LEVELS.map((s) => (
                    <option key={s} value={s}>
                      {s || "—"}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Flight class">
                <select
                  className="input"
                  value={prefs.flight_class}
                  onChange={(e) => set("flight_class", e.target.value)}
                >
                  {FLIGHT_CLASSES.map((s) => (
                    <option key={s} value={s}>
                      {s || "—"}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Min hotel stars">
                <input
                  type="number"
                  min={1}
                  max={5}
                  className="input"
                  value={prefs.hotel_star_rating_min}
                  onChange={(e) =>
                    set("hotel_star_rating_min", Number(e.target.value) || 3)
                  }
                />
              </Field>
            </div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={prefs.prefer_direct_flights}
                onChange={(e) => set("prefer_direct_flights", e.target.checked)}
              />
              <span>Prefer direct flights</span>
            </label>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="mb-2 text-xs font-medium text-slate-500">
                Planning style
              </p>
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={prefs.planning_mode !== "interactive"}
                  onChange={(e) =>
                    set("planning_mode", e.target.checked ? "direct" : "interactive")
                  }
                />
                <span>
                  <span className="font-medium text-ink">Use smart defaults after kickoff</span>
                  <br />
                  <span className="text-slate-500 text-[11px]">
                    The agent first shows one prefilled review of saved preferences and
                    trip choices, then builds without extra questions. Uncheck to include
                    unresolved critical details in that same review.
                  </span>
                </span>
              </label>
            </div>
            <Field label="Dietary (comma-separated)">
              <input
                className="input"
                value={listText.dietary}
                onChange={(e) => setList("dietary", e.target.value)}
              />
            </Field>
            <Field label="Interests (comma-separated)">
              <input
                className="input"
                value={listText.interests}
                onChange={(e) => setList("interests", e.target.value)}
              />
            </Field>
            <Field label="Dislikes (comma-separated)">
              <input
                className="input"
                value={listText.dislikes}
                onChange={(e) => setList("dislikes", e.target.value)}
              />
            </Field>

            <div className="flex justify-end gap-2 pt-2">
              {!embedded && <button onClick={onClose} className="rounded-xl px-4 py-2 text-sm text-slate-500 hover:bg-slate-100">Cancel</button>}
              <button
                onClick={save}
                disabled={saving}
                className="rounded-xl bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        )}
    </>
  );

  if (embedded) return content;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink">Travel preferences</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-ink">✕</button>
        </div>
        {content}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
      {children}
    </label>
  );
}
