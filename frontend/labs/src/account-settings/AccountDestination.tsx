import { useState } from "react";
import {
  Accessibility,
  BarChart3,
  Check,
  ChevronLeft,
  Download,
  Gauge,
  History,
  Hotel,
  Languages,
  MapPin,
  ShieldCheck,
  Trash2,
  UsersRound,
  Utensils,
} from "lucide-react";

export type DestinationId = "menu" | "travel-profile" | "analytics" | "privacy";
export type AnalyticsPreference = "granted" | "denied";

function DestinationHeader({ icon: Icon, eyebrow, title, description, onBack }: {
  icon: typeof BarChart3;
  eyebrow: string;
  title: string;
  description: string;
  onBack: () => void;
}) {
  return <>
    <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-ink"><ChevronLeft size={13} aria-hidden /> Back to settings</button>
    <div className="mt-3 flex items-start gap-3">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-teal-50 text-teal-700"><Icon size={17} aria-hidden /></span>
      <div><p className="text-[9px] font-bold uppercase text-brand">{eyebrow}</p><h3 className="mt-0.5 text-sm font-semibold text-ink">{title}</h3><p className="mt-1 text-[11px] leading-relaxed text-slate-500">{description}</p></div>
    </div>
  </>;
}

function SettingRow({ icon: Icon, title, detail, children }: { icon: typeof Gauge; title: string; detail: string; children?: React.ReactNode }) {
  return <div className="flex items-start gap-2.5 border-t border-slate-100 py-2.5 first:border-0">
    <Icon size={14} className="mt-0.5 shrink-0 text-slate-400" aria-hidden />
    <div className="min-w-0 flex-1"><p className="text-[11px] font-semibold text-slate-700">{title}</p><p className="mt-0.5 text-[10px] leading-relaxed text-slate-400">{detail}</p>{children}</div>
  </div>;
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: () => void; label: string }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={onChange} className={`relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition ${checked ? "bg-teal-600" : "bg-slate-200"}`}><span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition ${checked ? "left-[18px]" : "left-0.5"}`} /></button>;
}

function TravelProfile({ onBack }: { onBack: () => void }) {
  const [pace, setPace] = useState("Balanced");
  const [stepFree, setStepFree] = useState(true);
  const [quietRooms, setQuietRooms] = useState(false);
  const [saved, setSaved] = useState(true);
  return <div data-lab-change="Complete Travel profile destination" className="p-4">
    <DestinationHeader icon={Gauge} eyebrow="Saved planning defaults" title="Travel profile" description="These preferences shape the first complete plan. You can override any of them for one trip in Assistant." onBack={onBack} />
    <div className="mt-3 rounded-md bg-slate-50 px-3 ring-1 ring-slate-200">
      <SettingRow icon={MapPin} title="Home base and usual departure" detail="New Delhi, India · DEL (Indira Gandhi International Airport) · surface transfers start from South Delhi" />
      <SettingRow icon={Gauge} title="Default trip pace" detail="Balanced days with one anchor experience and room for meals and transit.">
        <div className="mt-2 grid grid-cols-3 overflow-hidden rounded-md ring-1 ring-slate-200">{["Relaxed", "Balanced", "Full"].map((value) => <button key={value} type="button" aria-pressed={pace === value} onClick={() => { setPace(value); setSaved(false); }} className={`h-7 text-[10px] font-semibold ${pace === value ? "bg-ink text-white" : "bg-white text-slate-500 hover:bg-slate-100"}`}>{value}</button>)}</div>
      </SettingRow>
      <SettingRow icon={Hotel} title="Stay and transport style" detail="Boutique or heritage stays · 4-star comfort · direct flights preferred · taxi over self-drive" />
      <SettingRow icon={Utensils} title="Food preferences" detail="Vegetarian-friendly menus · local food is a priority · avoid very spicy meals" />
      <SettingRow icon={UsersRound} title="Usual travel party" detail="Munish + partner · child age 10 · preserve family rooms and adjacent seating" />
      <SettingRow icon={Languages} title="Language and currency" detail="English · prices in INR · metric distances · 24-hour times" />
      <SettingRow icon={Accessibility} title="Accessibility and comfort" detail="Applied to stays, transfers, walking load, and schedule buffers.">
        <div className="mt-2 grid grid-cols-2 gap-2">
          <label className="flex items-center justify-between rounded bg-white px-2 py-1.5 text-[10px] text-slate-600 ring-1 ring-slate-200">Step-free routes <Toggle checked={stepFree} onChange={() => { setStepFree(!stepFree); setSaved(false); }} label="Use step-free routes" /></label>
          <label className="flex items-center justify-between rounded bg-white px-2 py-1.5 text-[10px] text-slate-600 ring-1 ring-slate-200">Quiet rooms <Toggle checked={quietRooms} onChange={() => { setQuietRooms(!quietRooms); setSaved(false); }} label="Prefer quiet rooms" /></label>
        </div>
      </SettingRow>
    </div>
    <div className="mt-3 flex items-center justify-between gap-3"><p role="status" className={`text-[10px] ${saved ? "text-emerald-700" : "text-amber-700"}`}>{saved ? "Saved · Used for new trips" : "Unsaved profile changes"}</p><button type="button" onClick={() => setSaved(true)} disabled={saved} className="h-8 rounded-md bg-brand px-3 text-[10px] font-semibold text-white disabled:bg-slate-200 disabled:text-slate-400">Save travel profile</button></div>
  </div>;
}

function AnalyticsPreferences({ preference, onChange, onBack }: { preference: AnalyticsPreference; onChange: (preference: AnalyticsPreference) => void; onBack: () => void }) {
  return <div data-lab-change="Working Analytics preferences destination" className="p-4">
    <DestinationHeader icon={BarChart3} eyebrow="Measurement choice" title="Anonymous usage analytics" description="Choose whether anonymous interaction events help improve planning. Trip details, messages, identity, and shared links are never sent." onBack={onBack} />
    <div className="mt-4 grid grid-cols-2 gap-2" role="group" aria-label="Analytics preference">{(["denied", "granted"] as const).map((value) => <button key={value} type="button" onClick={() => onChange(value)} aria-pressed={preference === value} className={`flex h-10 items-center justify-center gap-1.5 rounded-md text-xs font-semibold ring-1 ${preference === value ? "bg-ink text-white ring-ink" : "bg-white text-slate-600 ring-slate-200 hover:ring-slate-300"}`}>{preference === value && <Check size={13} aria-hidden />}{value === "granted" ? "Allow analytics" : "No thanks"}</button>)}</div>
    <div className="mt-3 rounded-md bg-slate-50 p-3 text-[10px] leading-relaxed text-slate-500 ring-1 ring-slate-200"><strong className="text-slate-700">Included:</strong> feature opened, task completed, error category, and performance timing.<br /><strong className="text-slate-700">Never included:</strong> itinerary content, chat text, names, email, location history, or booking details.</div>
    <p role="status" className="mt-3 text-[10px] text-emerald-700">Preference set to {preference === "granted" ? "allowed" : "not allowed"}. Collection stays disabled when no measurement service is configured.</p>
  </div>;
}

function PrivacyAndData({ onBack }: { onBack: () => void }) {
  const [historyEnabled, setHistoryEnabled] = useState(true);
  const [exportStatus, setExportStatus] = useState("Ready to export");
  const [confirmHistoryDelete, setConfirmHistoryDelete] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  return <div data-lab-change="Complete Privacy and data destination" className="p-4">
    <DestinationHeader icon={ShieldCheck} eyebrow="Your data" title="Privacy and data" description="Review what is saved, control personalization history, export a portable copy, or permanently delete account data." onBack={onBack} />
    <div className="mt-3 grid grid-cols-3 gap-2">{[["8", "Saved trips"], ["24", "Conversations"], ["12", "Profile preferences"]].map(([value, label]) => <div key={label} className="rounded-md bg-slate-50 p-2 ring-1 ring-slate-200"><p className="text-sm font-semibold text-ink">{value}</p><p className="text-[9px] text-slate-400">{label}</p></div>)}</div>
    <div className="mt-3 rounded-md px-3 ring-1 ring-slate-200">
      <div className="flex items-start gap-2.5 py-2.5"><History size={14} className="mt-0.5 text-slate-400" aria-hidden /><div className="min-w-0 flex-1"><p className="text-[11px] font-semibold text-slate-700">Use trip history for personalization</p><p className="mt-0.5 text-[10px] leading-relaxed text-slate-400">Past destinations and corrections can improve future defaults. Saved trips and chats are kept until you delete them; turning this off does not delete either.</p></div><Toggle checked={historyEnabled} onChange={() => setHistoryEnabled(!historyEnabled)} label="Use trip history for personalization" /></div>
      <div className="flex items-center gap-2.5 border-t border-slate-100 py-2.5"><Download size={14} className="text-slate-400" aria-hidden /><div className="min-w-0 flex-1"><p className="text-[11px] font-semibold text-slate-700">Export your data</p><p className="text-[10px] text-slate-400">Trips, profile, and conversations · JSON archive</p></div><button type="button" onClick={() => setExportStatus("Export requested · download link will be emailed")} className="rounded-md bg-white px-2.5 py-1.5 text-[10px] font-semibold text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50">Request export</button></div>
    </div>
    <p role="status" className="mt-2 text-[10px] text-emerald-700">{exportStatus}</p>
    <div className="mt-3 rounded-md border border-slate-200 p-3">
      <div className="flex gap-2"><History size={14} className="mt-0.5 shrink-0 text-slate-500" aria-hidden /><div><p className="text-[11px] font-semibold text-slate-700">Clear trip and chat history</p><p className="mt-0.5 text-[10px] leading-relaxed text-slate-400">Removes 8 saved trips and 24 conversations. Your sign-in and Travel Profile remain available.</p></div></div>
      {confirmHistoryDelete ? <div className="mt-3 flex items-center justify-between rounded bg-slate-50 p-2 ring-1 ring-slate-200"><p className="text-[10px] font-semibold text-slate-700">Delete saved history permanently?</p><div className="flex gap-2"><button type="button" onClick={() => setConfirmHistoryDelete(false)} className="h-7 px-2 text-[10px] font-semibold text-slate-500">Cancel</button><button type="button" className="h-7 rounded bg-slate-700 px-2.5 text-[10px] font-semibold text-white">Clear history</button></div></div> : <button type="button" onClick={() => setConfirmHistoryDelete(true)} className="mt-3 h-7 rounded-md bg-white px-2.5 text-[10px] font-semibold text-slate-600 ring-1 ring-slate-200">Review history deletion</button>}
    </div>
    <div className="mt-3 rounded-md border border-rose-200 bg-rose-50/50 p-3">
      <div className="flex gap-2"><Trash2 size={14} className="mt-0.5 shrink-0 text-rose-600" aria-hidden /><div><p className="text-[11px] font-semibold text-rose-800">Delete account and all data</p><p className="mt-0.5 text-[10px] leading-relaxed text-rose-700/75">Permanently removes trips, conversations, preferences, guest links, and sign-in association after confirmation. This cannot be undone.</p></div></div>
      {confirmDelete ? <div className="mt-3 rounded bg-white p-2.5 ring-1 ring-rose-200"><p className="text-[10px] font-semibold text-rose-800">Confirm permanent deletion?</p><div className="mt-2 flex justify-end gap-2"><button type="button" onClick={() => setConfirmDelete(false)} className="h-7 px-2 text-[10px] font-semibold text-slate-500">Cancel</button><button type="button" className="h-7 rounded bg-rose-700 px-2.5 text-[10px] font-semibold text-white">Delete everything</button></div></div> : <button type="button" onClick={() => setConfirmDelete(true)} className="mt-3 h-7 rounded-md bg-white px-2.5 text-[10px] font-semibold text-rose-700 ring-1 ring-rose-200">Review deletion</button>}
    </div>
  </div>;
}

export function AccountDestination({ destination, preference, onPreferenceChange, onBack }: { destination: Exclude<DestinationId, "menu">; preference: AnalyticsPreference; onPreferenceChange: (preference: AnalyticsPreference) => void; onBack: () => void }) {
  if (destination === "travel-profile") return <TravelProfile onBack={onBack} />;
  if (destination === "privacy") return <PrivacyAndData onBack={onBack} />;
  return <AnalyticsPreferences preference={preference} onChange={onPreferenceChange} onBack={onBack} />;
}