export function verifyDestinationPhotos(overview, environment) {
  if (!Array.isArray(overview.photos) || !Array.isArray(overview.key_attractions)) {
    throw new Error("destination overview returned an invalid photo contract");
  }
  const photos = [
    ...overview.photos,
    ...overview.key_attractions.map((item) => item.photo).filter((photo) => photo != null),
  ];
  if (!photos.length) {
    if (environment === "canary") return 0;
    throw new Error("destination overview returned no photo");
  }
  for (const photo of photos) {
    let url;
    try {
      if (typeof photo !== "string") throw new Error();
      url = new URL(photo);
    } catch {
      throw new Error("destination overview returned an invalid photo URL");
    }
    const googlePhoto =
      (url.hostname.endsWith(".googleusercontent.com") && url.pathname.length > 1) ||
      (url.hostname === "maps.googleapis.com" && url.pathname === "/maps/api/place/photo") ||
      (url.hostname === "places.googleapis.com" && /^\/v1\/places\/.+\/photos\/.+\/media$/.test(url.pathname));
    if (url.protocol !== "https:" || url.username || url.password || !googlePhoto) {
      throw new Error("destination overview returned an unsupported photo URL");
    }
  }
  return new Set(photos).size;
}
