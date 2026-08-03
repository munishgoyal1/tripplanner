export function hotelIdentityKey(name: string): string {
  return name
    .split(",", 1)[0]
    .trim()
    .replace(/\brameshwaram\b/gi, "rameswaram")
    .replace(/\b(?:hotel|hotels|resort|resorts)\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}