"""MCP tools for public company search and domain registration checks."""
import os
import re
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("jobshield-public-checks")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)


@mcp.tool()
def lookup_domain_rdap(domain: str) -> dict:
    """Look up basic public registration events for an email or website domain."""
    clean_domain = domain.strip().lower().rstrip(".")
    if not DOMAIN_RE.fullmatch(clean_domain):
        return {"status": "invalid_domain", "domain": clean_domain}

    source_url = f"https://rdap.org/domain/{clean_domain}"
    try:
        response = httpx.get(source_url, timeout=8, follow_redirects=True)
        if response.status_code == 404:
            return {"status": "not_found", "domain": clean_domain, "source_url": source_url}
        response.raise_for_status()
        data = response.json()
        events = [
            {"action": event.get("eventAction"), "date": event.get("eventDate")}
            for event in data.get("events", [])
            if event.get("eventAction") in {"registration", "expiration"}
        ]
        return {
            "status": "found",
            "domain": clean_domain,
            "events": events,
            "source_url": source_url,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except (httpx.HTTPError, ValueError) as error:
        return {"status": "unavailable", "domain": clean_domain, "source_url": source_url, "error": type(error).__name__}


@mcp.tool()
def search_company_public_sources(company_name: str, extra_terms: str = "") -> dict:
    """Search public web results for a company. Requires BRAVE_SEARCH_API_KEY."""
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return {"status": "not_configured", "results": []}

    query = " ".join(part.strip() for part in (company_name, extra_terms) if part.strip())
    try:
        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            params={"q": query, "count": 5},
            timeout=10,
        )
        response.raise_for_status()
        hits = response.json().get("web", {}).get("results", [])
        results = [
            {"title": hit.get("title", ""), "url": hit.get("url", ""), "description": hit.get("description", "")}
            for hit in hits[:5]
        ]
        return {
            "status": "ok" if results else "no_results",
            "query": query,
            "results": results,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except httpx.HTTPError as error:
        return {"status": "unavailable", "query": query, "results": [], "error": type(error).__name__}


if __name__ == "__main__":
    mcp.run(transport="stdio")
