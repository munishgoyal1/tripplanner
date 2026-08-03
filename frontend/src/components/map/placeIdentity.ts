export function hotelIdentityKey(name: string): string {
  return name
    .split(",", 1)[0]
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}