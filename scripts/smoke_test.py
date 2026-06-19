"""One-shot smoke test for all configured external APIs.

Run: python scripts/smoke_test.py
Prints PASS / SKIP / FAIL for each provider without exposing secrets.
"""

from __future__ import annotations

from tripplanner.config import get_settings


def _line(label: str, status: str, detail: str = "") -> None:
    print(f"  [{status:4}] {label:20} {detail}")


def test_aoai() -> None:
    print("\n=== Azure OpenAI ===")
    s = get_settings()
    if not (s.azure_openai_endpoint and s.azure_openai_api_key):
        _line("AOAI chat", "SKIP", "AZURE_OPENAI_* not set")
        return
    try:
        from langchain_openai import AzureChatOpenAI
        llm = AzureChatOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key,
            azure_deployment=s.azure_openai_deployment,
            api_version=s.azure_openai_api_version,
            temperature=0,
            max_tokens=20,
        )
        out = llm.invoke("Reply with exactly the word: PONG")
        text = (out.content or "").strip()
        _line("AOAI chat", "PASS", f"response={text[:40]!r}")
    except Exception as e:
        _line("AOAI chat", "FAIL", f"{type(e).__name__}: {str(e)[:120]}")


def test_tavily() -> None:
    print("\n=== Tavily Web Search ===")
    from tripplanner.tools.web_search import is_configured, web_search
    if not is_configured():
        _line("Tavily search", "SKIP", "TAVILY_API_KEY not set")
        return
    try:
        out = web_search.invoke({"query": "best month to visit Goa", "max_results": 2})
        ok = ("not configured" not in out.lower()) and ("error" not in out.lower()[:80])
        _line("Tavily search", "PASS" if ok else "FAIL", f"{len(out)} chars returned")
    except Exception as e:
        _line("Tavily search", "FAIL", f"{type(e).__name__}: {str(e)[:120]}")


def test_google_places() -> None:
    print("\n=== Google Places ===")
    from tripplanner.tools.google_places import (
        is_configured,
        search_places_with_reviews,
    )
    if not is_configured():
        _line("Places search", "SKIP", "GOOGLE_PLACES_API_KEY not set")
        return
    try:
        out = search_places_with_reviews.invoke(
            {"query": "Taj Mahal Palace hotel", "city": "Mumbai", "max_results": 2}
        )
        ok = ("not configured" not in out.lower()) and ("error" not in out.lower()[:80])
        _line("Places search", "PASS" if ok else "FAIL", f"{len(out)} chars returned")
    except Exception as e:
        _line("Places search", "FAIL", f"{type(e).__name__}: {str(e)[:120]}")


def test_duffel() -> None:
    print("\n=== Duffel Flights ===")
    from tripplanner.tools.duffel_flights import is_configured, search_flights_duffel
    if not is_configured():
        _line("Duffel flights", "SKIP", "DUFFEL_API_KEY not set — sign up at https://app.duffel.com/sign-up")
        return
    try:
        out = search_flights_duffel.invoke({
            "origin": "LHR",
            "destination": "JFK",
            "departure_date": "2026-09-15",
            "adults": 1,
            "max_results": 3,
        })
        ok = ("not configured" not in out.lower()) and ("Option 1" in out or "No Duffel offers" in out)
        _line("Duffel flights", "PASS" if ok else "FAIL", f"{len(out)} chars returned")
    except Exception as e:
        _line("Duffel flights", "FAIL", f"{type(e).__name__}: {str(e)[:120]}")


def test_amadeus_deprecated() -> None:
    print("\n=== Amadeus (deprecated, fallback only) ===")
    from tripplanner.tools import amadeus_client
    if not amadeus_client.is_configured():
        _line("Amadeus", "SKIP", "AMADEUS_* not set (kept for future enterprise migration)")
        return
    _line("Amadeus", "INFO", "configured — fallback available")


if __name__ == "__main__":
    print("Smoke testing configured external APIs…")
    test_aoai()
    test_tavily()
    test_google_places()
    test_duffel()
    test_amadeus_deprecated()
    print("\nDone.")

