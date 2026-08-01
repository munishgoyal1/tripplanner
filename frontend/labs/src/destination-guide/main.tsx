import React, { useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  BedDouble,
  Check,
  ChevronRight,
  Compass,
  MapPin,
  Search,
  Sparkles,
  Star,
  Utensils,
} from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabScope } from "../shared/LabScope";
import "../shared/experiment-layout.css";

type VariantId = "contextual" | "chapters" | "directory";
type PlaceKind = "hotel" | "attraction" | "restaurant";
type Category = "highlights" | PlaceKind;

interface Place {
  id: string;
  name: string;
  city: "Jaipur" | "Jodhpur" | "Udaipur";
  kind: PlaceKind;
  rating: number;
  reviews: string;
  area: string;
  note: string;
  image: string;
  planned?: boolean;
}

const variants = [
  {
    id: "contextual" as const,
    label: "A · Contextual explorer",
    summary: "Mixed trip highlights at top level; same-type, same-city alternatives when focused.",
  },
  {
    id: "chapters" as const,
    label: "B · City chapters",
    summary: "Browse one destination at a time through compact Hotels, Attractions, and Food sections.",
  },
  {
    id: "directory" as const,
    label: "C · Filtered directory",
    summary: "Search and combine city/category filters across a denser all-place index.",
  },
];

const places: Place[] = [
  { id: "rambagh", name: "Rambagh Palace", city: "Jaipur", kind: "hotel", rating: 4.7, reviews: "6.8k", area: "Bhawani Singh Road", note: "Landmark palace stay with formal gardens and heritage rooms.", image: "https://images.unsplash.com/photo-1564501049412-61c2a3083791?auto=format&fit=crop&w=600&q=80", planned: true },
  { id: "oberoi-rajvilas", name: "The Oberoi Rajvilas", city: "Jaipur", kind: "hotel", rating: 4.8, reviews: "3.9k", area: "Goner Road", note: "Quiet resort-style alternative outside the old-city bustle.", image: "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?auto=format&fit=crop&w=600&q=80" },
  { id: "samode-haveli", name: "Samode Haveli", city: "Jaipur", kind: "hotel", rating: 4.6, reviews: "2.7k", area: "Gangapole", note: "Intimate haveli stay within reach of the Pink City sights.", image: "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=600&q=80" },
  { id: "amber", name: "Amber Fort", city: "Jaipur", kind: "attraction", rating: 4.6, reviews: "158k", area: "Amer", note: "Hilltop palace complex with courtyards, mirrorwork, and broad views.", image: "https://images.unsplash.com/photo-1599661046289-e31897846e41?auto=format&fit=crop&w=600&q=80", planned: true },
  { id: "city-palace", name: "City Palace", city: "Jaipur", kind: "attraction", rating: 4.4, reviews: "53k", area: "Old City", note: "Royal courtyards, textiles, arms, and living palace history.", image: "https://images.unsplash.com/photo-1592639296346-560c37a0f711?auto=format&fit=crop&w=600&q=80" },
  { id: "baradari", name: "Baradari", city: "Jaipur", kind: "restaurant", rating: 4.5, reviews: "2.1k", area: "City Palace", note: "Contemporary Rajasthani cooking in a restored palace courtyard.", image: "https://images.unsplash.com/photo-1552566626-52f8b828add9?auto=format&fit=crop&w=600&q=80" },
  { id: "umaid", name: "Umaid Bhawan Palace", city: "Jodhpur", kind: "hotel", rating: 4.8, reviews: "6.2k", area: "Cantt Area", note: "Grand palace hotel with museum access and expansive grounds.", image: "https://images.unsplash.com/photo-1571896349842-33c89424de2d?auto=format&fit=crop&w=600&q=80", planned: true },
  { id: "raas", name: "RAAS Jodhpur", city: "Jodhpur", kind: "hotel", rating: 4.6, reviews: "2.4k", area: "Old City", note: "Design-led haveli with direct views of Mehrangarh Fort.", image: "https://images.unsplash.com/photo-1445019980597-93fa8acb246c?auto=format&fit=crop&w=600&q=80" },
  { id: "mehrangarh", name: "Mehrangarh Fort", city: "Jodhpur", kind: "attraction", rating: 4.6, reviews: "137k", area: "Fort Road", note: "Monumental fort, museum galleries, and Blue City panoramas.", image: "https://images.unsplash.com/photo-1477587458883-47145ed94245?auto=format&fit=crop&w=600&q=80", planned: true },
  { id: "jaswant", name: "Jaswant Thada", city: "Jodhpur", kind: "attraction", rating: 4.4, reviews: "18k", area: "Lawaran", note: "Serene marble memorial beside the fort approach.", image: "https://images.unsplash.com/photo-1534759928642-1b9d5b42bb13?auto=format&fit=crop&w=600&q=80" },
  { id: "indique", name: "Indique", city: "Jodhpur", kind: "restaurant", rating: 4.4, reviews: "4.6k", area: "Gulab Sagar", note: "Rooftop regional dining framed by fort and clock-tower views.", image: "https://images.unsplash.com/photo-1515003197210-e0cd71810b5f?auto=format&fit=crop&w=600&q=80" },
  { id: "lake-palace", name: "Taj Lake Palace", city: "Udaipur", kind: "hotel", rating: 4.7, reviews: "8.9k", area: "Lake Pichola", note: "Iconic island palace reached by boat, with water on every side.", image: "https://images.unsplash.com/photo-1600255821058-c4f89958d700?auto=format&fit=crop&w=600&q=80", planned: true },
  { id: "leela", name: "The Leela Palace Udaipur", city: "Udaipur", kind: "hotel", rating: 4.7, reviews: "5.1k", area: "Lake Pichola", note: "Lakefront luxury with palace views and direct boat arrival.", image: "https://images.unsplash.com/photo-1613490493576-7fde63acd811?auto=format&fit=crop&w=600&q=80" },
  { id: "udaipur-palace", name: "City Palace Udaipur", city: "Udaipur", kind: "attraction", rating: 4.5, reviews: "96k", area: "Old City", note: "Layered palace complex overlooking Lake Pichola.", image: "https://images.unsplash.com/photo-1595658658481-d53d3f999875?auto=format&fit=crop&w=600&q=80", planned: true },
  { id: "bagore", name: "Bagore Ki Haveli", city: "Udaipur", kind: "attraction", rating: 4.4, reviews: "23k", area: "Gangaur Ghat", note: "Historic haveli known for its evening folk performance.", image: "https://images.unsplash.com/photo-1582972236019-ea4af5ffe587?auto=format&fit=crop&w=600&q=80" },
  { id: "ambrai", name: "Ambrai", city: "Udaipur", kind: "restaurant", rating: 4.3, reviews: "14k", area: "Hanuman Ghat", note: "Lakeside dinner with illuminated palace and waterfront views.", image: "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=600&q=80", planned: true },
  { id: "tribute", name: "Tribute", city: "Udaipur", kind: "restaurant", rating: 4.4, reviews: "7.2k", area: "Fateh Sagar", note: "Relaxed lakeside setting for Indian and Rajasthani dishes.", image: "https://images.unsplash.com/photo-1544148103-0773bf10d330?auto=format&fit=crop&w=600&q=80" },
  { id: "1135-ad", name: "1135 AD", city: "Jaipur", kind: "restaurant", rating: 4.2, reviews: "5.8k", area: "Amber Fort", note: "Ornate dining rooms and terrace views inside the fort complex.", image: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=600&q=80" },
];

const cities = ["All cities", "Jaipur", "Jodhpur", "Udaipur"] as const;
const categories: { id: Category; label: string; icon: typeof Compass }[] = [
  { id: "highlights", label: "Highlights", icon: Sparkles },
  { id: "hotel", label: "Hotels", icon: BedDouble },
  { id: "attraction", label: "Attractions", icon: Compass },
  { id: "restaurant", label: "Food", icon: Utensils },
];

function kindLabel(kind: PlaceKind, plural = false) {
  if (kind === "hotel") return plural ? "hotels" : "Hotel";
  if (kind === "restaurant") return plural ? "restaurants" : "Restaurant";
  return plural ? "attractions" : "Attraction";
}

function PlaceRow({ place, onFocus, compact = false }: { place: Place; onFocus: (place: Place) => void; compact?: boolean }) {
  return (
    <button type="button" onClick={() => onFocus(place)} className={`group grid w-full grid-cols-[4.5rem_minmax(0,1fr)_auto] gap-3 border-b border-slate-100 text-left last:border-b-0 ${compact ? "py-2" : "py-3"}`}>
      <img src={place.image} alt="" className={`${compact ? "h-14" : "h-[4.5rem]"} w-[4.5rem] rounded-md object-cover`} />
      <span className="min-w-0 self-center">
        <span className="flex items-center gap-1.5"><strong className="truncate text-sm text-ink">{place.name}</strong>{place.planned && <span className="rounded-sm bg-emerald-50 px-1.5 py-0.5 text-[9px] font-bold text-emerald-700">IN TRIP</span>}</span>
        <span className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500"><MapPin size={11} aria-hidden /> {place.city} · {place.area}</span>
        {!compact && <span className="mt-1 block truncate text-xs text-slate-500">{place.note}</span>}
      </span>
      <span className="flex self-center items-center gap-1 text-xs font-semibold text-amber-700"><Star size={12} fill="currentColor" aria-hidden />{place.rating}<ChevronRight size={13} className="ml-1 text-slate-300 group-hover:text-brand" aria-hidden /></span>
    </button>
  );
}

function FocusedPlace({ place, onBack }: { place: Place; onBack: () => void }) {
  return (
    <div>
      <button type="button" onClick={onBack} className="mb-3 inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-brand"><ArrowLeft size={13} aria-hidden /> Trip guide</button>
      <div className="relative overflow-hidden rounded-md">
        <img src={place.image} alt="" className="h-48 w-full object-cover" />
        <span className="absolute left-3 top-3 rounded-sm bg-white/95 px-2 py-1 text-[10px] font-bold text-slate-700 shadow-sm">{kindLabel(place.kind)}</span>
      </div>
      <div className="py-3">
        <div className="flex items-start justify-between gap-3"><div><h3 className="display text-xl font-semibold text-ink">{place.name}</h3><p className="mt-1 text-xs text-slate-500">{place.city} · {place.area}</p></div><span className="flex items-center gap-1 text-xs font-semibold text-amber-700"><Star size={12} fill="currentColor" aria-hidden /> {place.rating} ({place.reviews})</span></div>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">{place.note}</p>
        <button type="button" className={place.planned ? "btn-ghost mt-3" : "btn-primary mt-3"}>{place.planned ? <><Check size={13} aria-hidden /> In your trip</> : "+ Add to trip"}</button>
      </div>
    </div>
  );
}

function ScopeControls({ city, category, setCity, setCategory }: { city: string; category: Category; setCity: (city: string) => void; setCategory: (category: Category) => void }) {
  return <div data-lab-change="City and place-type browsing scopes" className="border-b border-slate-100 pb-3">
    <div className="flex gap-1 overflow-x-auto pb-1">{cities.map((item) => <button key={item} type="button" onClick={() => setCity(item)} aria-pressed={city === item} className={`h-7 shrink-0 rounded-md px-2.5 text-[11px] font-semibold ${city === item ? "bg-ink text-white" : "bg-slate-50 text-slate-500 hover:bg-slate-100"}`}>{item}</button>)}</div>
    <div className="mt-2 grid grid-cols-4 gap-1 rounded-md bg-slate-50 p-1">{categories.map(({ id, label, icon: Icon }) => <button key={id} type="button" onClick={() => setCategory(id)} aria-pressed={category === id} className={`flex h-8 items-center justify-center gap-1 rounded-[5px] text-[10px] font-semibold ${category === id ? "bg-white text-ink shadow-sm" : "text-slate-500"}`}><Icon size={12} aria-hidden />{label}</button>)}</div>
  </div>;
}

function ContextualExplorer() {
  const [city, setCity] = useState("All cities");
  const [category, setCategory] = useState<Category>("highlights");
  const [focused, setFocused] = useState<Place | null>(null);
  const [visible, setVisible] = useState(6);
  const filtered = places.filter((place) => (city === "All cities" || place.city === city) && (category === "highlights" || place.kind === category));
  const alternatives = focused ? places.filter((place) => place.id !== focused.id && place.city === focused.city && place.kind === focused.kind) : [];
  if (focused) return <div data-lab-change="Focused place and contextual alternatives"><FocusedPlace place={focused} onBack={() => setFocused(null)} /><div className="border-t border-slate-100 pt-3"><p className="text-[10px] font-bold uppercase text-slate-400">Compare nearby</p><h3 className="mt-0.5 text-sm font-semibold text-ink">Other {kindLabel(focused.kind, true)} in {focused.city}</h3><div className="mt-2">{alternatives.map((place) => <PlaceRow key={place.id} place={place} onFocus={setFocused} compact />)}</div></div></div>;
  return <div><ScopeControls city={city} category={category} setCity={(next) => { setCity(next); setVisible(6); }} setCategory={(next) => { setCategory(next); setVisible(6); }} /><div className="py-3"><p className="text-[10px] font-bold uppercase text-brand">{category === "highlights" ? "Curated across your route" : city === "All cities" ? "Across all three cities" : city}</p><h3 className="mt-0.5 text-base font-semibold text-ink">{category === "highlights" ? "Rajasthan trip highlights" : kindLabel(category, true).replace(/^./, (letter) => letter.toUpperCase())}</h3><p className="mt-1 text-xs text-slate-500">{filtered.length} grounded choices · showing {Math.min(visible, filtered.length)}</p></div><div>{filtered.slice(0, visible).map((place) => <PlaceRow key={place.id} place={place} onFocus={setFocused} />)}</div>{visible < filtered.length && <button type="button" onClick={() => setVisible((count) => count + 6)} className="mt-3 h-9 w-full rounded-md bg-slate-50 text-xs font-semibold text-slate-600 hover:bg-slate-100">Show {Math.min(6, filtered.length - visible)} more</button>}</div>;
}

function CityChapters() {
  const [city, setCity] = useState("Jaipur");
  const [focused, setFocused] = useState<Place | null>(null);
  if (focused) return <FocusedPlace place={focused} onBack={() => setFocused(null)} />;
  return <div data-lab-change="Destination chapters with category sections"><div className="flex gap-1 border-b border-slate-100 pb-3">{cities.slice(1).map((item) => <button key={item} type="button" onClick={() => setCity(item)} aria-pressed={city === item} className={`h-8 flex-1 rounded-md text-xs font-semibold ${city === item ? "bg-ink text-white" : "bg-slate-50 text-slate-500"}`}>{item}</button>)}</div>{categories.slice(1).map(({ id, label }) => { const matches = places.filter((place) => place.city === city && place.kind === id); return <section key={id} className="border-b border-slate-100 py-3 last:border-0"><div className="mb-1 flex items-center"><h3 className="text-xs font-bold uppercase text-slate-500">{label}</h3><button type="button" className="ml-auto text-[11px] font-semibold text-brand">See all {matches.length}</button></div>{matches.slice(0, 2).map((place) => <PlaceRow key={place.id} place={place} onFocus={setFocused} compact />)}</section>; })}</div>;
}

function FilteredDirectory() {
  const [query, setQuery] = useState("");
  const [city, setCity] = useState("All cities");
  const [category, setCategory] = useState<Category>("highlights");
  const [focused, setFocused] = useState<Place | null>(null);
  const filtered = useMemo(() => places.filter((place) => (city === "All cities" || place.city === city) && (category === "highlights" || place.kind === category) && `${place.name} ${place.area}`.toLowerCase().includes(query.toLowerCase())), [category, city, query]);
  if (focused) return <FocusedPlace place={focused} onBack={() => setFocused(null)} />;
  return <div data-lab-change="Searchable all-place directory"><label className="flex h-9 items-center gap-2 rounded-md bg-slate-50 px-3 ring-1 ring-inset ring-slate-200"><Search size={14} className="text-slate-400" aria-hidden /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search all trip places" className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label><div className="mt-3"><ScopeControls city={city} category={category} setCity={setCity} setCategory={setCategory} /></div><div className="flex items-center py-3"><p className="text-xs font-semibold text-ink">{filtered.length} places</p><span className="ml-auto text-[10px] text-slate-400">Rating · relevance</span></div>{filtered.map((place) => <PlaceRow key={place.id} place={place} onFocus={setFocused} compact />)}</div>;
}

function Preview({ variant }: { variant: VariantId }) {
  return <div className="grid min-h-[38rem] grid-cols-[minmax(0,1fr)_23rem] overflow-hidden rounded-md bg-slate-100 ring-1 ring-slate-200" style={{ minWidth: 780 }}><div className="relative overflow-hidden bg-[linear-gradient(135deg,#fff7ed,#f0fdfa)]"><img src="https://images.unsplash.com/photo-1599661046827-dacde6976549?auto=format&fit=crop&w=1200&q=75" alt="Rajasthan landscape" className="h-full w-full object-cover opacity-75" /><div className="absolute inset-x-5 top-5 bg-white/90 p-4 shadow-card backdrop-blur"><p className="text-[10px] font-bold uppercase text-brand">Rajasthan · 10 days · 3 cities</p><h2 className="display mt-1 text-2xl font-semibold text-ink">Jaipur to Udaipur</h2><p className="mt-1 text-xs text-slate-600">Your route remains visible while Details becomes a deeper place browser.</p></div></div><aside className="flex min-h-0 flex-col bg-white"><header className="h-10 shrink-0 border-b border-slate-100 px-4 py-3 text-xs font-bold uppercase text-slate-500">Destination guide</header><div className="min-h-0 flex-1 overflow-y-auto p-4">{variant === "contextual" ? <ContextualExplorer /> : variant === "chapters" ? <CityChapters /> : <FilteredDirectory />}</div></aside></div>;
}

function Lab() {
  const [active, setActive] = useState<VariantId>("contextual");
  const selected = variants.find((variant) => variant.id === active)!;
  return <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_22rem)] px-4 py-6 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><header className="border-b border-slate-200 pb-5"><a href="./catalog.html" className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-brand"><ArrowLeft size={14} aria-hidden /> Back to All Labs</a><div className="mt-4 flex items-center gap-2 text-brand"><Compass size={15} aria-hidden /><p className="text-xs font-bold uppercase">Active experiment · Place discovery</p></div><h1 className="display mt-1 text-3xl font-semibold text-ink">Destination guide depth and context</h1><p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">Explore more than the current ten-place shortlist without turning Details into an endless media feed. Compare how multi-city highlights, city/category browsing, and focused alternatives should work.</p></header><LabScope labId="destination-guide" /><div className="lab-variant-grid mt-5" role="tablist" aria-label="Destination guide variants">{variants.map((variant) => <button key={variant.id} type="button" role="tab" aria-selected={active === variant.id} onClick={() => setActive(variant.id)} className={`rounded-md p-3 text-left ring-1 ${active === variant.id ? "bg-white shadow-card ring-brand/30" : "bg-white/70 ring-slate-200 hover:bg-white"}`}><span className="text-sm font-semibold text-ink">{variant.label}</span><span className="mt-1 block text-xs leading-relaxed text-slate-500">{variant.summary}</span></button>)}</div><section className="mt-6"><div className="mb-3 flex flex-wrap items-end justify-between gap-3"><div><p className="text-[10px] font-bold uppercase text-slate-400">Interactive production-scale preview</p><h2 className="mt-0.5 text-lg font-semibold text-ink">{selected.label}</h2></div>{active === "contextual" && <p className="text-xs font-semibold text-emerald-700">Recommended · progressive results + contextual alternatives</p>}</div><div className="overflow-x-auto pb-2"><Preview key={active} variant={active} /></div></section><div className="mt-6"><DecisionCapture labId="destination-guide" labTitle="Destination guide depth and context" options={variants} activeOption={active} onChoose={(id) => setActive(id as VariantId)} /></div></div></main>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Lab /></React.StrictMode>);