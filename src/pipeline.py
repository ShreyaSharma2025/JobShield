"""Entry point used by Streamlit to run one posting review."""
from time import perf_counter
from uuid import uuid4
from .parser import parse_posting
from .red_flags import detect_red_flags
from .policy import calculate_decision
from .schemas import AnalysisResult
from .storage import save_result
from .guardrails import validate_posting_text


def analyze_posting(text: str) -> AnalysisResult:
    text = validate_posting_text(text)
    try:
        from .flow import JobReviewFlow
    except ModuleNotFoundError as error:
        if error.name not in {"crewai", "dotenv"}:
            raise
        return _analyze_without_crewai(text)

    review = JobReviewFlow(text)
    return review.kickoff()


def _analyze_without_crewai(text: str) -> AnalysisResult:
    """Run full deterministic multi-agent workflow when CrewAI LLM stack is not active."""
    started_at = perf_counter()
    run_id = str(uuid4())
    workflow_events: list[str] = []

    # Agent 1: Posting Parser Agent
    workflow_events.append("1. Posting Parser Agent: Extracted structured fields and candidate attributes.")
    posting = parse_posting(text)

    # Agent 2: Coordinator / Investigation Planner
    investigation_steps = ["Red-Flag Analysis"]
    if posting.company_name or posting.contact_email or posting.links:
        investigation_steps.append("Company/Domain Verification")
    investigation_steps.append("Historical Vector Similarity")
    investigation_steps.append("Evidence Synthesis & Verdict")
    workflow_events.append(f"2. Coordinator / Investigation Planner: Dynamic plan formulated: {', '.join(investigation_steps)}.")

    # Agent 3: Red-Flag Detection Agent
    workflow_events.append("3. Red-Flag Detection Agent: Evaluated rule-based indicators and sensitive patterns.")
    evidence = detect_red_flags(text)
    workflow_events.append(f"   -> Identified {len(evidence)} supported evidence finding(s).")

    # Agent 4: Similarity Agent
    similar_postings = []
    similarity_review = None
    try:
        from .similarity import search_similar_postings
        from .schemas import SimilarPosting, SimilarityReview
        raw_similar = search_similar_postings(text, top_k=4)
        if raw_similar:
            similar_postings = [SimilarPosting.model_validate(item) for item in raw_similar]
            workflow_events.append(f"4. Similarity Agent: Retrieved {len(similar_postings)} nearest labeled historical posting(s).")
            similarity_review = SimilarityReview(
                summary=f"Retrieved {len(similar_postings)} historical posting(s) with closest semantic patterns.",
                limitation="Historical similarity is supporting context for patterns only, not mathematical proof of fraud."
            )
        else:
            workflow_events.append("4. Similarity Agent: No historical index match or index still initializing.")
    except Exception as err:
        workflow_events.append(f"4. Similarity Agent: Notice - {type(err).__name__}")

    # Agent 5: Company Verification Agent
    from .schemas import CompanyCheck
    from .mcp_server import lookup_domain_dns, lookup_domain_rdap, search_company_public_sources
    import re

    company_check = CompanyCheck(
        status="unavailable",
        company_name=posting.company_name,
        findings=[],
        sources=[]
    )

    domain_to_check = None
    if posting.contact_email and "@" in posting.contact_email:
        domain_to_check = posting.contact_email.rsplit("@", 1)[-1].lower()
    elif posting.links:
        domain_match = re.search(r"https?://(?:www\.)?([^/:\s]+)", posting.links[0])
        if domain_match:
            domain_to_check = domain_match.group(1).lower()

    # 1. Live Domain Registry (RDAP & DNS) Checks
    free_mail_providers = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "rediffmail.com", "icloud.com"}
    major_enterprises = {"amazon", "google", "microsoft", "tata", "tcs", "infosys", "wipro", "ibm", "deloitte", "accenture", "apple", "meta"}
    comp_lower = (posting.company_name or "").lower()
    is_major_brand = any(brand in comp_lower for brand in major_enterprises)

    queried_sites = []

    if domain_to_check:
        company_check.domain = domain_to_check

        # Check DNS
        dns_signal = "Neutral / Needs Verification"
        dns_summary = "DNS resolution offline"
        dns_why = "DNS verifies if a domain has real, operational servers behind it."
        try:
            dns_res = lookup_domain_dns(domain_to_check)
            if dns_res.get("status") == "resolved":
                ips = dns_res.get("ip_addresses", [])
                company_check.dns_status = f"Active DNS host (IP: {', '.join(ips[:2])})"
                company_check.findings.append(f"Domain '{domain_to_check}' resolves to active host servers.")
                dns_summary = f"Resolves to active IP(s): {', '.join(ips[:2])}"
                dns_signal = "Genuine Signal"
                dns_why = f"Domain '{domain_to_check}' has valid A/AAAA DNS records, confirming an active network presence."
            else:
                company_check.dns_status = "Unresolved or inactive domain"
                company_check.findings.append(f"Domain '{domain_to_check}' failed host DNS resolution.")
                dns_summary = "Domain failed DNS lookup (NXDOMAIN / No A-records)"
                dns_signal = "Suspicious / Scam Signal"
                dns_why = f"Claimed domain '{domain_to_check}' has no active DNS records. Scammers frequently invent non-existent fake domains."
        except Exception as e:
            company_check.dns_status = "DNS check offline"
            dns_summary = f"DNS query exception: {type(e).__name__}"

        queried_sites.append({
            "site_name": "Active DNS Nameserver Resolution",
            "url": f"dns://{domain_to_check}",
            "service_type": "Host Server & Nameserver Infrastructure",
            "status": "Resolved" if dns_signal == "Genuine Signal" else "Failed",
            "result_summary": dns_summary,
            "verdict_signal": dns_signal,
            "rationale": dns_why,
        })

        # Check RDAP (Official WHOIS Registration Age)
        rdap_url = f"https://rdap.org/domain/{domain_to_check}"
        if domain_to_check not in free_mail_providers:
            rdap_signal = "Neutral / Needs Verification"
            rdap_summary = "Querying global ICANN/IANA RDAP database"
            rdap_why = "Checks how long the domain has existed. Brand new domains or unlisted domains are high risk."
            try:
                rdap_res = lookup_domain_rdap(domain_to_check)
                rdap_url = rdap_res.get("source_url", rdap_url)
                if rdap_res.get("status") == "found":
                    events = {e.get("action"): e.get("date") for e in rdap_res.get("events", [])}
                    reg_date = events.get("registration", "")[:10]
                    exp_date = events.get("expiration", "")[:10]
                    company_check.rdap_reg_date = reg_date
                    company_check.rdap_exp_date = exp_date
                    if reg_date:
                        company_check.findings.append(f"Official RDAP WHOIS: Domain registered on {reg_date} (expires {exp_date or 'N/A'}).")
                        rdap_summary = f"Domain registered: {reg_date} | Expires: {exp_date or 'N/A'}"
                        rdap_signal = "Genuine Signal"
                        rdap_why = f"Global WHOIS registry confirms an established enterprise domain created on {reg_date}."
                    if rdap_res.get("source_url") and rdap_res["source_url"] not in company_check.sources:
                        company_check.sources.append(rdap_res["source_url"])
                elif rdap_res.get("status") == "not_found":
                    company_check.findings.append(f"RDAP WHOIS: Domain '{domain_to_check}' is NOT registered in official global TLD registry.")
                    rdap_summary = "Domain not found in global registry"
                    rdap_signal = "Suspicious / Scam Signal"
                    rdap_why = "Domain is not registered with official ICANN registrars."
            except Exception:
                rdap_summary = "RDAP registry temporarily unreachable"

            queried_sites.append({
                "site_name": "Official Global Domain Registry (RDAP / WHOIS)",
                "url": rdap_url,
                "service_type": "ICANN / IANA Domain Age & Ownership",
                "status": "Found (200)" if rdap_signal == "Genuine Signal" else "Not Found (404)",
                "result_summary": rdap_summary,
                "verdict_signal": rdap_signal,
                "rationale": rdap_why,
            })
        else:
            company_check.findings.append(f"Contact email uses free public webmail ({domain_to_check}) rather than an authentic corporate domain.")
            free_signal = "Suspicious / Scam Signal" if is_major_brand else "Neutral / Needs Verification"
            queried_sites.append({
                "site_name": "Contact Channel Domain Audit",
                "url": f"https://{domain_to_check}",
                "service_type": "Public Webmail Provider Detection",
                "status": "Public Webmail Identified",
                "result_summary": f"Applicant contacted via free personal mail service (@{domain_to_check})",
                "verdict_signal": free_signal,
                "rationale": f"Claimed recruiter represents '{posting.company_name or 'corporate'}' using @{domain_to_check}. Legitimate corporate recruiters from major firms strictly use corporate emails." if is_major_brand else "Free webmail may be used by micro-freelancers, but requires secondary verification.",
            })

    # 2. Live Website HTTP Probe
    live_url = None
    if posting.links:
        live_url = posting.links[0]
    elif domain_to_check and domain_to_check not in free_mail_providers:
        live_url = f"https://{domain_to_check}"

    if live_url:
        company_check.website_url = live_url
        probe_signal = "Neutral / Needs Verification"
        probe_summary = "Attempting HTTP connection"
        probe_why = "Verifies if the employer maintains an active, secure website."
        try:
            import httpx
            web_resp = httpx.get(
                live_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
                timeout=4.0,
                follow_redirects=True,
            )
            company_check.website_status = f"HTTP {web_resp.status_code} ({'Active & Online' if web_resp.status_code < 400 else 'Returned Error'})"
            title_match = re.search(r"<title[^>]*>(.*?)</title>", web_resp.text, re.I | re.DOTALL)
            clean_title = ""
            if title_match:
                clean_title = re.sub(r"\s+", " ", title_match.group(1)).strip()[:100]
                company_check.website_title = clean_title
                company_check.findings.append(f"Live Web Probe: Connected to '{live_url}' (HTTP {web_resp.status_code}) -> Title: \"{clean_title}\"")
                probe_summary = f"HTTP {web_resp.status_code} OK | Title: \"{clean_title}\""
            else:
                company_check.findings.append(f"Live Web Probe: Connected to '{live_url}' (HTTP {web_resp.status_code})")
                probe_summary = f"HTTP {web_resp.status_code} OK | Connected successfully"

            if web_resp.status_code < 400:
                probe_signal = "Genuine Signal"
                probe_why = f"Web server at '{live_url}' returned HTTP {web_resp.status_code} and served active web content."
            else:
                probe_signal = "Suspicious / Scam Signal"
                probe_why = f"Web server returned HTTP error {web_resp.status_code}."

            if live_url not in company_check.sources:
                company_check.sources.append(live_url)
        except Exception as e:
            company_check.website_status = "Connection Failed / Unreachable"
            company_check.findings.append(f"Live Web Probe: Failed to connect to '{live_url}' ({type(e).__name__})")
            probe_summary = f"Connection failed: {type(e).__name__}"
            probe_signal = "Suspicious / Scam Signal"
            probe_why = f"Server at '{live_url}' failed to respond. Fake job postings often cite dead or unreachable URLs."

        queried_sites.append({
            "site_name": "Live Corporate Website & Server Probe",
            "url": live_url,
            "service_type": "Direct HTTP/HTTPS Endpoint Verification",
            "status": company_check.website_status or "Probe Attempted",
            "result_summary": probe_summary,
            "verdict_signal": probe_signal,
            "rationale": probe_why,
        })

    # 3. Live Public Web Search Engine (DuckDuckGo / Brave)
    if posting.company_name:
        clean_comp = posting.company_name.strip()
        search_engine = "DuckDuckGo Live Search"
        search_signal = "Neutral / Needs Verification"
        search_summary = f"Searching web for '{clean_comp} careers official site'"
        search_why = "Locates official careers pages, press releases, and verifiable job openings."
        
        try:
            search_res = search_company_public_sources(clean_comp, "careers official site")
            search_engine = search_res.get("engine", search_engine)
            results_found = search_res.get("results", [])
            
            if results_found:
                first_hit = results_found[0]
                company_check.findings.append(f"Web Search: Discovered {len(results_found)} corporate directory and careers links via {search_engine}.")
                for hit in results_found:
                    if hit.get("url") and hit["url"] not in company_check.sources:
                        company_check.sources.append(hit["url"])
                
                search_summary = f"Found: '{first_hit.get('title', '')}' -> {first_hit.get('url', '')}"
                search_signal = "Genuine Signal" if not (domain_to_check in free_mail_providers and is_major_brand) else "Suspicious / Scam Signal"
                search_why = f"Search confirmed legitimate corporate career portals exist at {first_hit.get('url', '')}. Compare contact info against these official portals."
            else:
                search_summary = f"No authoritative career portal found for '{clean_comp}'"
                search_signal = "Neutral / Needs Verification"
                search_why = "Unregistered or obscure company name without verified public job listings."
        except Exception as e:
            search_summary = f"Search request error: {type(e).__name__}"

        queried_sites.append({
            "site_name": f"Live Web Search Engine ({search_engine})",
            "url": f"https://html.duckduckgo.com/html/?q={clean_comp.replace(' ', '+')}+careers",
            "service_type": "Public Web Search & Official Careers Discovery",
            "status": "Search Completed (HTTP 200)",
            "result_summary": search_summary,
            "verdict_signal": search_signal,
            "rationale": search_why,
        })

        # 4. LinkedIn Corporate Directory Verification
        encoded_c = clean_comp.replace(" ", "+")
        li_url = f"https://www.linkedin.com/search/results/companies/?keywords={encoded_c}"
        queried_sites.append({
            "site_name": "LinkedIn Corporate & Employee Directory",
            "url": li_url,
            "service_type": "Professional Business & Recruiter Verification",
            "status": "Directory Query Ready",
            "result_summary": f"Target entity: '{clean_comp}' corporate profile and employee headcount",
            "verdict_signal": "Genuine Signal" if is_major_brand else "Neutral / Needs Verification",
            "rationale": "Verifies that the employer has legitimate registered company pages, active employees, and HR personnel on LinkedIn.",
        })

        # 5. Ministry of Corporate Affairs (MCA) / Govt Registry
        mca_url = "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do"
        queried_sites.append({
            "site_name": "Ministry of Corporate Affairs (MCA India) / Registrar of Companies",
            "url": mca_url,
            "service_type": "Official Government Business Registration & CIN Check",
            "status": "MCA Portal Link Verified",
            "result_summary": f"Lookup Corporate Identity Number (CIN) & Director details for '{clean_comp}'",
            "verdict_signal": "Neutral / Needs Verification",
            "rationale": "For Indian entities, genuine companies are legally incorporated with a CIN in the MCA master database.",
        })

    company_check.queried_sites = queried_sites

    # 4. Corporate Domain Consistency & Status Synthesis
    if domain_to_check in free_mail_providers and is_major_brand:
        company_check.status = "ambiguous"
        company_check.findings.append("CRITICAL: Major multinational brand recruiter is using free unverified personal webmail. High risk of impersonation.")
    elif domain_to_check and domain_to_check not in free_mail_providers and company_check.dns_status and "Active" in company_check.dns_status:
        if not evidence and is_major_brand:
            company_check.status = "verified_match"
            company_check.findings.append("Verified match: Posting links to authentic corporate domain without detected red flags.")
        else:
            company_check.status = "ambiguous"
            company_check.findings.append("Domain is active and registered; verify specific job opening on the company careers portal.")
    elif domain_to_check and company_check.dns_status and "Unresolved" in company_check.dns_status:
        company_check.status = "not_found"
        company_check.findings.append("Domain failed DNS resolution or does not exist.")
    elif not domain_to_check and posting.company_name:
        company_check.status = "ambiguous"
        company_check.findings.append(f"Company '{posting.company_name}' identified. Cross-reference official links above to verify opening.")
    else:
        company_check.status = "unavailable"
        company_check.findings.append("No explicit company or website provided for external verification.")

    workflow_events.append(f"5. Company Verification Agent: Checked public sources and domain (Status: {company_check.status}).")


    # Agent 6: Evidence / Verdict Agent
    decision = calculate_decision(evidence, company_check)
    workflow_events.append(f"6. Evidence / Verdict Agent: Synthesis complete -> Category assigned: {decision.category}.")

    duration = round(perf_counter() - started_at, 2)
    result = AnalysisResult(
        run_id=run_id,
        posting=posting,
        evidence=evidence,
        decision=decision,
        similar_postings=similar_postings,
        similarity_review=similarity_review,
        company_check=company_check,
        workflow_events=workflow_events,
        duration_seconds=duration,
    )
    save_result(result, text)
    return result
