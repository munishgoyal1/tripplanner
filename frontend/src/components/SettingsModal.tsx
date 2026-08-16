import { useEffect, useState } from "react";
import {
  fetchPreferences,
  savePreferences,
  regenerateProfileSummary,
  fetchProfileSuggestions,
  resolveProfileSuggestion,
  type Preferences,
  type ProfileSuggestion,
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

interface ShelfTag {
  value: string;
  label: string;
  detail: string;
  /** Tags sharing a group are mutually exclusive (pick one); tags without one combine freely (pick any). */
  exclusiveGroup?: string;
}

interface ShelfGroup {
  key: "trip_style" | "planning_mode" | "budget_level" | "dietary";
  label: string;
  hint: string;
  mode: "single" | "multi";
  tags: readonly ShelfTag[];
}

const SHELF_GROUPS: readonly ShelfGroup[] = [
  {
    key: "trip_style",
    label: "Trip rhythm",
    hint: "How full should a day feel?",
    mode: "single",
    tags: [
      { value: "relaxed", label: "Relaxed", detail: "Fewer stops and generous free time" },
      { value: "balanced", label: "Balanced", detail: "A full day with room to breathe" },
      { value: "packed", label: "See it all", detail: "More anchors, fewer empty windows" },
    ],
  },
  {
    key: "budget_level",
    label: "Where you stay",
    hint: "What makes a base work?",
    mode: "single",
    tags: [
      { value: "comfortable", label: "Central and walkable", detail: "Trade a little space for a better base" },
      { value: "luxury", label: "Quiet retreat", detail: "A calmer stay away from the busiest streets" },
      { value: "budget", label: "Best value", detail: "Keep the total practical cost in view" },
    ],
  },
  {
    key: "dietary",
    label: "Food and flavour",
    hint: "What should the itinerary notice? Choose as many as apply.",
    mode: "multi",
    tags: [
      { value: "local favourites", label: "Local favourites", detail: "Neighbourhood places worth the detour" },
      { value: "food-centric", label: "Food is part of the trip", detail: "Build the day around memorable meals" },
      { value: "street food", label: "Street food and markets", detail: "Casual, everyday eating over formal dinners" },
      { value: "vegetarian", label: "Vegetarian", detail: "Vegetarian-first choices and clear menus", exclusiveGroup: "diet" },
      { value: "vegan", label: "Vegan", detail: "Fully plant-based choices", exclusiveGroup: "diet" },
      { value: "halal", label: "Halal", detail: "Halal-certified or halal-friendly options", exclusiveGroup: "diet" },
    ],
  },
];

/** Toggles one tag: an exclusiveGroup tag replaces its group peers (an intersection choice); an ungrouped tag just adds or removes itself (a union choice). */
function toggleTag(current: readonly string[], tag: ShelfTag, tags: readonly ShelfTag[]): string[] {
  if (current.includes(tag.value)) return current.filter((v) => v !== tag.value);
  if (!tag.exclusiveGroup) return [...current, tag.value];
  const peers = new Set(tags.filter((t) => t.exclusiveGroup === tag.exclusiveGroup).map((t) => t.value));
  return [...current.filter((v) => !peers.has(v)), tag.value];
}

interface Props {
  onClose: () => void;
  embedded?: boolean;
  /** "identity" shows sign-in-adjacent account fields; "travel" shows travel preferences. Each is mounted once, so the same fields are never shown twice. */
  section: "identity" | "travel";
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

function PreferenceShelf({
  prefs,
  choose,
}: {
  prefs: Preferences;
  choose: (key: keyof Preferences, value: Preferences[keyof Preferences]) => void;
}) {
  return (
    <section className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4" aria-labelledby="preference-shelf-heading">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-brand">Your travel profile</p>
          <h3 id="preference-shelf-heading" className="mt-1 text-base font-semibold text-ink">A better trip starts here</h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">Choose what feels like you. These defaults shape every new trip and can be changed for one trip later.</p>
        </div>
        <span className="shrink-0 rounded-full bg-white px-2 py-1 text-[10px] font-semibold text-emerald-700 ring-1 ring-emerald-200">Saved privately</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {SHELF_GROUPS.map((group) => (
          <div key={group.label} className="rounded-lg bg-white p-3 ring-1 ring-emerald-100">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div><h4 className="text-xs font-semibold text-ink">{group.label}</h4><p className="mt-0.5 text-[11px] text-slate-500">{group.hint}</p></div>
              <code className="text-[10px] text-slate-400">{group.key}</code>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {group.tags.map((tag) => {
                const selected = group.mode === "multi" ? prefs.dietary.includes(tag.value) : String(prefs[group.key]) === tag.value;
                const onClick = () =>
                  group.mode === "multi"
                    ? choose("dietary", toggleTag(prefs.dietary, tag, group.tags))
                    : choose(group.key, tag.value as Preferences[typeof group.key]);
                return <button key={tag.value} type="button" aria-pressed={selected} onClick={onClick} className={`rounded-full px-2.5 py-1.5 text-[11px] font-semibold transition ${selected ? "bg-brand text-white" : "bg-slate-50 text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100"}`}>{selected ? "✓ " : "+ "}{tag.label}</button>;
              })}
            </div>
          </div>
        ))}
      </div>
      <label className="mt-3 flex items-start gap-2 rounded-lg bg-white p-3 text-left ring-1 ring-emerald-100">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={prefs.planning_mode !== "interactive"}
          onChange={(event) => choose("planning_mode", event.target.checked ? "direct" : "interactive")}
        />
        <span>
          <span className="text-xs font-semibold text-ink">Let the agent decide with smart defaults</span>
          <span className="mt-0.5 block text-[11px] leading-relaxed text-slate-500">
            It uses your request, travel profile, and history without stopping to confirm defaults.
            Turn this off to let it ask one quick question when an answer would meaningfully help.
          </span>
        </span>
      </label>
      <aside className="mt-3 rounded-lg bg-ink p-3 text-white" aria-label="What Tripplanner understands">
        <p className="text-xs font-semibold">What Tripplanner understands</p>
        <p className="mt-1 text-[11px] leading-relaxed text-emerald-100">The words are human. Multiple food tags combine; the values stay precise and stable for the planner.</p>
        <div className="mt-2 grid gap-1 text-[10px] text-emerald-50 sm:grid-cols-2">
          <code>trip_pace: {prefs.trip_style || "balanced"}</code>
          <code>planning_style: {prefs.planning_mode === "direct" ? "surprise_me" : "show_options"}</code>
          <code>stay_style: {prefs.budget_level || "best_value"}</code>
          <code>food: {prefs.dietary.length ? prefs.dietary.join(" + ") : "none selected"}</code>
        </div>
      </aside>
    </section>
  );
}

export default function SettingsModal({ onClose, embedded = false, section }: Props) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saving, setSaving] = useState(false);
  const [extracted, setExtracted] = useState<string[] | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [summaryConflict, setSummaryConflict] = useState(false);
  const [suggestions, setSuggestions] = useState<ProfileSuggestion[]>([]);
  const [dirtyFields, setDirtyFields] = useState<Set<keyof Preferences>>(new Set());
  // Raw editable text for the comma-separated list fields. Kept separate from
  // the parsed arrays so a trailing comma isn't stripped mid-typing — parsed
  // into arrays only at save time.
  const [listText, setListText] = useState({ interests: "", dislikes: "" });

  function syncListText(p: Preferences) {
    setListText({
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

  useEffect(() => {
    fetchProfileSuggestions()
      .then(setSuggestions)
      .catch(() => setSuggestions([]));
  }, []);

  function resolveSuggestion(id: string, action: "save" | "dismiss") {
    setSuggestions((current) => current.filter((item) => item.id !== id));
    resolveProfileSuggestion(id, action)
      .then((remaining) => {
        setSuggestions(remaining);
        if (action === "save") {
          // A confirmed fact lands in the durable profile, so re-read it.
          fetchPreferences()
            .then((p) => {
              setPrefs(p);
              syncListText(p);
            })
            .catch(() => undefined);
        }
      })
      .catch(() => undefined);
  }

  const profileSuggestions = suggestions.filter((item) => item.kind !== "family_member");

  function set<K extends keyof Preferences>(key: K, value: Preferences[K]) {
    setDirtyFields((current) => new Set(current).add(key));
    setPrefs((p) => (p ? { ...p, [key]: value } : p));
  }

  function setList(key: "interests" | "dislikes", value: string) {
    setDirtyFields((current) => new Set(current).add(key));
    setListText((current) => ({ ...current, [key]: value }));
  }

  async function save() {
    if (!prefs) return;
    setSaving(true);
    try {
      const merged: Preferences = {
        ...prefs,
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
            {section === "travel" && <>
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
            {profileSuggestions.length > 0 && (
              <div className="rounded-xl bg-amber-50/70 p-3 ring-1 ring-amber-200">
                <p className="text-xs font-medium text-amber-800">
                  Noticed in chat · not saved yet
                </p>
                <p className="mt-0.5 text-[11px] text-amber-700/80">
                  Nothing here is part of your profile until you keep it.
                </p>
                <ul className="mt-2 space-y-2">
                  {profileSuggestions.map((item) => (
                    <li key={item.id} className="rounded-lg bg-white p-2.5 ring-1 ring-amber-100">
                      <p className="text-xs font-semibold text-ink">{item.summary}</p>
                      <div className="mt-1.5 flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => resolveSuggestion(item.id, "save")}
                          className="h-7 rounded-full bg-ink px-3 text-[11px] font-semibold text-white"
                        >
                          Keep
                        </button>
                        <button
                          type="button"
                          onClick={() => resolveSuggestion(item.id, "dismiss")}
                          className="h-7 rounded-full px-3 text-[11px] font-semibold text-slate-500 ring-1 ring-slate-200"
                        >
                          Discard
                        </button>
                        <span className="ml-auto text-[10px] uppercase tracking-wide text-amber-700">
                          {item.label}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <PreferenceShelf prefs={prefs} choose={set} />
            <details className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <summary className="cursor-pointer text-xs font-semibold text-slate-600">Advanced preferences</summary>
              <div className="mt-3 space-y-4">
            <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-100">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500">
                  What I've learned about you
                </span>                <div className="flex items-center gap-2">
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
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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
            <div className="grid grid-cols-2 gap-3">
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
            </div>
              </div>
            </details>
            </>}

            {section === "identity" && <>
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
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
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
            </>}

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
