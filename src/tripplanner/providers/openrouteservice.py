"""OpenRouteService coordinate-based directions fallback."""

from __future__ import annotations

from typing import Any

import httpx


class OpenRouteServiceError(RuntimeError):
    pass


_PROFILES = {
    "DRIVE": "driving-car",
    "WALK": "foot-walking",
    "BICYCLE": "cycling-regular",
}


class OpenRouteServiceProvider:
    name = "openrouteservice"

    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def compute_route(self, coordinates: list[tuple[float, float]], mode: str) -> dict[str, Any]:
        profile = _PROFILES.get(mode.upper())
        if not profile:
            raise OpenRouteServiceError(f"OpenRouteService does not support mode {mode}")
        if len(coordinates) < 2:
            raise OpenRouteServiceError("At least two coordinates are required")
        try:
            payload = {
                "coordinates": [
                    [longitude, latitude] for latitude, longitude in coordinates
                ]
            }
            response = httpx.post(
                f"{self._base_url}/v2/directions/{profile}/json",
                headers={"Authorization": self._api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise OpenRouteServiceError(
                f"OpenRouteService returned HTTP {exc.response.status_code}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenRouteServiceError(
                f"OpenRouteService request failed: {type(exc).__name__}"
            ) from exc
        routes = payload.get("routes") or []
        if not routes:
            raise OpenRouteServiceError("OpenRouteService returned no route")
        return routes[0]
