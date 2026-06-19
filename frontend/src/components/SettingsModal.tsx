import { useEffect, useState } from "react";
import {
  fetchPreferences,
  savePreferences,
  regenerateProfileSummary,
  type Preferences,
} from "../api";

interface Props {
  onClose: () => void;
}

const TRIP_STYLES = ["", "relaxed", "balanced", "packed", "luxury", "budget", "adventure"];
const BUDGET_LEVELS = ["", "shoestring", "budget", "moderate", "comfortable", "luxury"];
const FLIGHT_CLASSES = ["", "economy", "premium_economy", "business", "first"];

function commaList(v: string[]): string {
  return v.join(", ");
}
function parseList(s: string): string[] {
  return s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

export default function SettingsModal({ onClose }: Props) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saving, setSaving] = useState(false);
  const [extracted, setExtracted] = useState<string[] | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    fetchPreferences()
      .then(setPrefs)
      .catch(() => setPrefs(null));
  }, []);

  function set<K extends keyof Preferences>(key: K, value: Preferences[K]) {
    setPrefs((p) => (p ? { ...p, [key]: value } : p));
  }

  async function save() {
    if (!prefs) return;
    setSaving(true);
    try {
      const result = await savePreferences(prefs);
      if (result.about_me_extracted && result.about_me_extracted.length > 0) {
        // Re-load so the form reflects the structured fields the LLM filled
        // in, and surface a confirmation instead of closing immediately.
        setExtracted(result.about_me_extracted);
        setPrefs(await fetchPreferences());
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
      const summary = await regenerateProfileSummary();
      setPrefs((p) => (p ? { ...p, profile_summary: summary } : p));
    } finally {
      setRegenerating(false);
    }
  }

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
          <button onClick={onClose} className="text-slate-400 hover:text-ink">
            ✕
          </button>
        </div>

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
                onChange={(e) => set("profile_summary", e.target.value)}
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
            <Field label="Dietary (comma-separated)">
              <input
                className="input"
                value={commaList(prefs.dietary)}
                onChange={(e) => set("dietary", parseList(e.target.value))}
              />
            </Field>
            <Field label="Interests (comma-separated)">
              <input
                className="input"
                value={commaList(prefs.interests)}
                onChange={(e) => set("interests", parseList(e.target.value))}
              />
            </Field>
            <Field label="Dislikes (comma-separated)">
              <input
                className="input"
                value={commaList(prefs.dislikes)}
                onChange={(e) => set("dislikes", parseList(e.target.value))}
              />
            </Field>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={onClose}
                className="rounded-xl px-4 py-2 text-sm text-slate-500 hover:bg-slate-100"
              >
                Cancel
              </button>
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
