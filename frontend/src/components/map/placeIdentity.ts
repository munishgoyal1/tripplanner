export function hotelIdentityKey(name: string): string {
  return name
    .split(",", 1)[0]
    .trim()
    .replace(/\brameshwaram\b/gi, "rameswaram")
    .replace(/\b(?:hotel|hotels|resort|resorts)\b/gi, " ")
    .replace(/[^a-z0-9]+/gi, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

export function hotelIdentityMatches(left: string, right: string): boolean {
  const leftTokens = new Set(hotelIdentityKey(left).split(" ").filter(Boolean));
  const rightTokens = new Set(hotelIdentityKey(right).split(" ").filter(Boolean));
  if (!leftTokens.size || !rightTokens.size) return false;
  const isSubset = (subset: Set<string>, superset: Set<string>) => (
    [...subset].every((token) => superset.has(token))
  );
  return isSubset(leftTokens, rightTokens) || isSubset(rightTokens, leftTokens);
}

export function hotelIdentityGroups(names: string[]): string[] {
  return names.reduce<string[]>((groups, name) => {
    if (!groups.some((representative) => hotelIdentityMatches(representative, name))) {
      groups.push(name);
    }
    return groups;
  }, []);
}