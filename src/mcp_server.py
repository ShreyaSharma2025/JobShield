"""MCP tools for public company search and domain registration checks."""
import os
import re
from datetime import datetime, timezone

import httpx
try:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("jobshield-public-checks")
except Exception:
    class DummyMCP:
        def tool(self):
            return lambda fn: fn
        def run(self, **kwargs):
            pass
    mcp = DummyMCP()

DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)

# Increased timeouts for reliability on slower networks
HTTP_TIMEOUT = 5.0
DNS_TIMEOUT = 5.0


@mcp.tool()
def lookup_domain_rdap(domain: str) -> dict:
    """Look up basic public registration events for an email or website domain."""
    clean_domain = domain.strip().lower().rstrip(".")
    if not DOMAIN_RE.fullmatch(clean_domain):
        return {"status": "invalid_domain", "domain": clean_domain}

    parts = clean_domain.split(".")
    if len(parts) > 2 and parts[-2] not in {"co", "com", "org", "gov", "ac", "edu", "net"}:
        query_domain = ".".join(parts[-2:])
    elif len(parts) > 3:
        query_domain = ".".join(parts[-3:])
    else:
        query_domain = clean_domain

    source_url = f"https://rdap.org/domain/{query_domain}"
    try:
        response = httpx.get(source_url, timeout=HTTP_TIMEOUT, follow_redirects=True)
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
def lookup_domain_dns(domain: str) -> dict:
    """Check DNS resolution to verify if a domain has active A/AAAA host records."""
    import socket
    clean_domain = domain.strip().lower().rstrip(".")
    if not DOMAIN_RE.fullmatch(clean_domain):
        return {"status": "invalid_domain", "domain": clean_domain}
    try:
        socket.setdefaulttimeout(DNS_TIMEOUT)
        addr_info = socket.getaddrinfo(clean_domain, 80, proto=socket.IPPROTO_TCP)
        ips = sorted(list({entry[4][0] for entry in addr_info}))
        return {
            "status": "resolved" if ips else "no_records",
            "domain": clean_domain,
            "ip_addresses": ips[:4],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except socket.gaierror:
        return {"status": "unresolved_domain", "domain": clean_domain, "ip_addresses": []}
    except Exception as error:
        return {"status": "error", "domain": clean_domain, "error": type(error).__name__}


def _parse_ddg_html(html_text: str, query: str) -> list[dict]:
    """Parse DuckDuckGo HTML results with multiple fallback strategies."""
    import urllib.parse
    results = []

    # Strategy 1: Original DDG selectors
    matches = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.DOTALL)
    snippets = re.findall(r'<a[^>]+class="result__snippet"[^>]+>(.*?)</a>', html_text, re.DOTALL)

    # Strategy 2: Alternative DDG selectors (newer layout)
    if not matches:
        matches = re.findall(r'<a[^>]+class="[^"]*result-link[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.DOTALL)
    if not matches:
        matches = re.findall(r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</a>', html_text, re.DOTALL)

    # Strategy 3: Generic link extraction from result blocks
    if not matches:
        result_blocks = re.findall(r'<div[^>]+class="[^"]*result[^"]*"[^>]*>(.*?)</div>\s*(?=<div|$)', html_text, re.DOTALL | re.I)
        for block in result_blocks[:5]:
            link_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if link_match:
                matches.append((link_match.group(1), link_match.group(2)))

    if not snippets:
        snippets = re.findall(r'<(?:span|div)[^>]+class="[^"]*snippet[^"]*"[^>]*>(.*?)</(?:span|div)>', html_text, re.DOTALL)

    for idx, (raw_url, raw_title) in enumerate(matches[:5]):
        clean_title = re.sub(r'<[^>]+>', '', raw_title).strip()
        clean_snippet = re.sub(r'<[^>]+>', '', snippets[idx]).strip() if idx < len(snippets) else ""

        actual_url = raw_url
        if "uddg=" in raw_url:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
            if "uddg" in parsed:
                actual_url = parsed["uddg"][0]
        elif raw_url.startswith("//"):
            actual_url = "https:" + raw_url

        if actual_url.startswith("http"):
            results.append({
                "title": clean_title,
                "url": actual_url,
                "description": clean_snippet or f"Live search result for '{query}'",
            })

    return results


def _search_google_scrape(query: str) -> list[dict]:
    """Fallback: scrape Google search results for company verification."""
    results = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        encoded_q = query.replace(" ", "+")
        resp = httpx.get(
            f"https://www.google.com/search?q={encoded_q}&num=5",
            headers=headers,
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            # Extract links from Google search results
            link_matches = re.findall(r'<a[^>]+href="/url\?q=([^&"]+)[^"]*"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
            if not link_matches:
                link_matches = re.findall(r'<a[^>]+href="(https?://(?!google|www\.google)[^"]+)"[^>]*>(.*?)</a>', resp.text, re.DOTALL)

            for url, title_html in link_matches[:5]:
                import urllib.parse
                clean_url = urllib.parse.unquote(url)
                clean_title = re.sub(r'<[^>]+>', '', title_html).strip()
                if clean_url.startswith("http") and "google" not in clean_url:
                    results.append({
                        "title": clean_title or f"Result for '{query}'",
                        "url": clean_url,
                        "description": f"Google search result for '{query}'",
                    })
    except Exception:
        pass
    return results


@mcp.tool()
def search_company_public_sources(company_name: str, extra_terms: str = "") -> dict:
    """Search public web results for a company. Uses Brave API if configured or free public search fallback."""
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    query = " ".join(part.strip() for part in (company_name, extra_terms) if part.strip())

    if api_key:
        try:
            response = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
                params={"q": query, "count": 5},
                timeout=HTTP_TIMEOUT,
            )
            response.raise_for_status()
            hits = response.json().get("web", {}).get("results", [])
            results = [
                {"title": hit.get("title", ""), "url": hit.get("url", ""), "description": hit.get("description", "")}
                for hit in hits[:5]
            ]
            if results:
                return {
                    "status": "ok",
                    "engine": "Brave Search API",
                    "query": query,
                    "results": results,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception:
            pass

    # Automatic Live Web Search via DuckDuckGo HTML Engine
    clean_name = re.sub(r"[^\w\s-]", "", company_name).strip()
    results = []
    engine_name = "Public Corporate Registry Fallback"
    
    if clean_name:
        # Attempt 1: DuckDuckGo
        try:
            ddg_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            ddg_resp = httpx.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers=ddg_headers,
                timeout=HTTP_TIMEOUT,
            )
            if ddg_resp.status_code == 200:
                results = _parse_ddg_html(ddg_resp.text, query)
                if results:
                    engine_name = "DuckDuckGo Live Web Search"
        except Exception:
            pass

        # Attempt 2: Google scrape fallback if DDG returned nothing
        if not results:
            try:
                results = _search_google_scrape(query)
                if results:
                    engine_name = "Google Web Search"
            except Exception:
                pass

    # If live search returned no items, use verified corporate directory links
    if not results and clean_name:
        encoded_query = "+".join(clean_name.split())
        results.append({
            "title": f"LinkedIn Corporate Directory: {company_name}",
            "url": f"https://www.linkedin.com/search/results/companies/?keywords={encoded_query}",
            "description": f"Verify registered company page, official employee profiles, and active hiring on LinkedIn.",
        })
        results.append({
            "title": f"Official Careers & Job Openings: {company_name}",
            "url": f"https://www.google.com/search?q={encoded_query}+careers+official+site",
            "description": f"Cross-reference active job openings and career notices directly on the authentic company website.",
        })
        results.append({
            "title": "Ministry of Corporate Affairs (MCA) India Registry Check",
            "url": "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do",
            "description": "Verify registered business legal identity (CIN), registration date, and official directors on the MCA portal.",
        })

    return {
        "status": "ok" if results else "no_results",
        "engine": engine_name,
        "query": query,
        "results": results,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }



if __name__ == "__main__":
    mcp.run(transport="stdio")
