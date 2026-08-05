const AIRPORT_COLOR = "#0f172a";
const HOTEL_COLOR = "#334155";

export const SUGGEST_COLOR = "#94a3b8";

// Every redraw asks for the same handful of icons. Building and percent-encoding
// the SVG each time was pure repeat work on the critical path of a day switch.
const ICON_CACHE = new Map<string, string>();

function cachedIcon(key: string, build: () => string): string {
  const hit = ICON_CACHE.get(key);
  if (hit !== undefined) return hit;
  const url = build();
  ICON_CACHE.set(key, url);
  return url;
}

export function pinIcon(color: string, label: string, focused = false): string {
  return cachedIcon(`pin|${color}|${label}|${focused}`, () => {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
      fill="${color}" stroke="white" stroke-width="2"/>
    <circle cx="17" cy="16" r="11" fill="${focused ? "#0f172a" : "white"}" fill-opacity="0.97"
      stroke="white" stroke-width="${focused ? 2 : 0}"/>
  <text x="17" y="21" font-family="Inter,Arial,sans-serif" font-size="14"
        font-weight="700" text-anchor="middle" fill="${focused ? "white" : color}">${label}</text>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
  });
}

export function routeLegIcon(label: string, color: string): string {
  return cachedIcon(`leg|${label}|${color}`, () => {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="112" height="26" viewBox="0 0 112 26">
  <rect x="1" y="1" width="110" height="24" rx="12" fill="white" fill-opacity="0.94"
        stroke="${color}" stroke-opacity="0.35"/>
  <text x="56" y="17" font-family="Inter,Arial,sans-serif" font-size="10"
        font-weight="600" text-anchor="middle" fill="#475569">${label}</text>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
  });
}

export function airportIcon(focused = false): string {
  return cachedIcon(`airport|${focused}`, () => {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
        fill="${AIRPORT_COLOR}" stroke="white" stroke-width="2"/>
  <circle cx="17" cy="16" r="11" fill="${focused ? "#0f172a" : "white"}" fill-opacity="0.97"
      stroke="white" stroke-width="${focused ? 2 : 0}"/>
  <text x="17" y="21" font-family="Inter,Arial,sans-serif" font-size="13"
        font-weight="700" text-anchor="middle" fill="${focused ? "white" : AIRPORT_COLOR}">A</text>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
  });
}

export function terminalIcon(kind: string): string {
  if (kind === "airport") return airportIcon();
  return cachedIcon(`terminal|${kind}`, () => {
  const label = kind === "station" ? "T" : kind === "origin" ? "O" : "B";
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
        fill="${AIRPORT_COLOR}" stroke="white" stroke-width="2"/>
  <circle cx="17" cy="16" r="11" fill="white" fill-opacity="0.97"/>
  <text x="17" y="21" font-family="Inter,Arial,sans-serif" font-size="13"
        font-weight="700" text-anchor="middle" fill="${AIRPORT_COLOR}">${label}</text>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
  });
}

export function hotelIcon(focused = false, label = "H"): string {
  return cachedIcon(`hotel|${focused}|${label}`, () => {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
        fill="${HOTEL_COLOR}" stroke="white" stroke-width="2"/>
    <circle cx="17" cy="16" r="11" fill="${focused ? "#0f172a" : "white"}" fill-opacity="0.97"
      stroke="white" stroke-width="${focused ? 2 : 0}"/>
  <text x="17" y="21" font-family="Inter,Arial,sans-serif" font-size="${label.length > 1 ? 11 : 13}"
        font-weight="700" text-anchor="middle" fill="${focused ? "white" : HOTEL_COLOR}">${label}</text>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
  });
}

export function dotIcon(color: string, focused = false): string {
  return cachedIcon(`dot|${color}|${focused}`, () => {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 18 18">
  <circle cx="9" cy="9" r="6" fill="${color}" stroke="${focused ? "#0f172a" : "white"}" stroke-width="${focused ? 3 : 2}"/>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
  });
}