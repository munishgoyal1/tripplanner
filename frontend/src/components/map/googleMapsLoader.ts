declare global {
  interface Window {
    google?: any;
    __gmapsReady__?: () => void;
  }
}

let loaderPromise: Promise<any> | null = null;

export function loadGoogleMaps(key: string, placesEnabled: boolean): Promise<any> {
  if (window.google?.maps && (!placesEnabled || window.google.maps.places)) {
    return Promise.resolve(window.google);
  }
  if (placesEnabled && window.google?.maps?.importLibrary) {
    return window.google.maps.importLibrary("places").then(() => window.google);
  }
  if (loaderPromise) return loaderPromise;
  loaderPromise = new Promise((resolve, reject) => {
    window.__gmapsReady__ = () => resolve(window.google);
    const script = document.createElement("script");
    const libraries = placesEnabled ? "&libraries=places" : "";
    script.src =
      `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}` +
      `&callback=__gmapsReady__${libraries}&loading=async&v=weekly`;
    script.async = true;
    script.onerror = () => {
      loaderPromise = null;
      reject(new Error("Failed to load Google Maps"));
    };
    document.head.appendChild(script);
  });
  return loaderPromise;
}