import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline import analyze_posting

test_cases = [
    {
        "name": "Google India (Authentic Tech Internship)",
        "company": "Google India",
        "text": """Company: Google India
Role: Software Engineering Intern - Summer 2026
Location: Bangalore / Hyderabad
Salary: Industry standard competitive monthly stipend
Requirements: Enrolled in Computer Science degree, proficiency in Python, C++, or Java.
Application: Selection involves technical coding rounds and algorithmic problem solving. Google never charges any application, training, or onboarding fees at any stage. Apply exclusively at https://careers.google.com/jobs/results/"""
    },
    {
        "name": "Amazon India (Phishing Impersonation & Upfront Fee)",
        "company": "Amazon India",
        "text": """Amazon India is hiring Customer Support Associates for Work From Home!
Salary: Rs. 45,000 per month. Freshers can apply with 100% placement guaranteed without interview.
Selected candidates must pay a refundable registration fee of Rs. 999 for ID card and software kit.
Contact HR Priya on WhatsApp: +91 9876543210 or email hr.amazon.recruitment@gmail.com immediately. Only today!"""
    },
    {
        "name": "AuraPay Fintech (Early Stage Startup)",
        "company": "AuraPay Fintech Solutions",
        "text": """AuraPay Fintech Solutions is hiring a Backend Developer Intern in Bengaluru.
Stipend: Rs. 25,000 per month.
Requirements: Python, FastAPI, Docker, PostgreSQL. Work directly with founding engineers building our MVP.
Urgent hiring, apply with your GitHub portfolio to careers@aurapayfintech.io or visit https://aurapayfintech.io."""
    },
    {
        "name": "Apex Global Media (Telegram Task Scam)",
        "company": "Apex Global Media Works",
        "text": """Apex Global Media Works is hiring Online YouTube Reviewers.
Earn Rs. 3,500 daily by watching and liking short videos from home! No experience required.
To access VIP payout tasks, pay Rs. 1,499 training fee.
Join our official Telegram group t.me/ApexGlobalJobs immediately to start earning today!"""
    },
    {
        "name": "Infosys BPM (Credential Theft & OTP Phishing)",
        "company": "Infosys BPM",
        "text": """Congratulations! You have been shortlisted for Infosys BPM Process Trainee role.
Package: 4.8 LPA. Selection based on academic score, confirmed selection without interview.
To issue your joining letter, submit Aadhaar card, bank account details, and send the OTP received on mobile.
Also deposit Rs. 2,000 security deposit to confirm your seat. Send details to infosys.onboarding@outlook.com."""
    }
]

def main():
    print("=" * 70)
    print("JOBSHIELD FUNCTIONALITY EVALUATION WITH DIFFERENT COMPANIES")
    print("=" * 70 + "\n")

    results_summary = []

    for tc in test_cases:
        res = analyze_posting(tc["text"])
        summary = {
            "test_case": tc["name"],
            "parsed_company": res.posting.company_name,
            "parsed_role": res.posting.role,
            "salary": res.posting.salary_text,
            "verdict": res.decision.category,
            "evidence_count": len(res.evidence),
            "evidence": [(e.severity, e.title) for e in res.evidence],
            "domain": res.company_check.domain,
            "domain_status": res.company_check.status,
            "similar_count": len(res.similar_postings),
            "duration_s": res.duration_seconds
        }
        results_summary.append(summary)

        print(f"🏢 Case: {tc['name']}")
        print(f"   • Extracted Company: {res.posting.company_name or 'Not specified'}")
        print(f"   • Extracted Role:    {res.posting.role or 'Not specified'}")
        print(f"   • Extracted Contact: {res.posting.contact_email or 'None'} | Phone/WhatsApp: {res.posting.contact_phone or 'None'}")
        print(f"   • Domain Check:      {res.company_check.domain or 'None'} (Status: {res.company_check.status})", flush=True)
        print(f"   • Verification Notes:", flush=True)
        for f in res.company_check.findings[:3]:
            print(f"       - {f}", flush=True)
        if res.company_check.sources:
            print(f"   • Web & Registry Sources:", flush=True)
            for s in res.company_check.sources[:2]:
                print(f"       * {s}", flush=True)
        print(f"   • 🛡️ Risk Verdict:   {res.decision.category}", flush=True)
        print(f"   • Evidence Items:    {len(res.evidence)}", flush=True)
        for e in res.evidence:
            print(f"       [{e.severity.upper()}] {e.title} -> \"{e.quote[:65]}...\"", flush=True)
        print(f"   • Historical Matches: {len(res.similar_postings)} records retrieved from FAISS index", flush=True)
        if res.similar_postings:
            top = res.similar_postings[0]
            sim = top.similarity if hasattr(top, 'similarity') else top.get('similarity')
            lbl = top.label if hasattr(top, 'label') else top.get('label')
            pid = top.posting_id if hasattr(top, 'posting_id') else top.get('posting_id')
            print(f"       Top Match: {pid} (Cosine Similarity: {sim:.2%}, Historical Label: {lbl})", flush=True)
        print(f"   • Response Time:     {res.duration_seconds}s", flush=True)
        print("-" * 70, flush=True)

if __name__ == "__main__":
    main()
