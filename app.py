"""Streamlit interface for the JobShield posting risk analyzer."""
import streamlit as st

from src.pipeline import analyze_posting

st.set_page_config(page_title="JobShield | Job Posting Review", page_icon="🛡️", layout="wide")

st.markdown(
    """
    <style>
      .block-container {max-width: 1080px; padding-top: 2.2rem; padding-bottom: 3rem;}
      .hero {padding: 1.35rem 1.5rem; border: 1px solid rgba(128,128,128,.28); border-radius: 14px; margin: .5rem 0 1.2rem 0;}
      .hero h1 {margin: 0 0 .35rem 0; font-size: 2.2rem;}
      .hero p {margin: 0; color: #9aa4b2; font-size: 1.05rem;}
      .section-label {font-size: .84rem; text-transform: uppercase; letter-spacing: .08em; color: #8b95a3; font-weight: 650;}
      div[data-testid="stForm"] {border: 1px solid rgba(128,128,128,.28); border-radius: 14px; padding: 1.1rem 1.2rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="hero"><h1>🛡️ JobShield</h1><p>Evidence-based risk review for job and internship postings</p></div>',
    unsafe_allow_html=True,
)

st.markdown("### How it works")
step1, step2, step3 = st.columns(3)
step1.markdown("**1 · Paste**\n\nAdd the complete job description below.")
step2.markdown("**2 · Review**\n\nSee the exact text that matched a risk rule.")
step3.markdown("**3 · Verify**\n\nUse the result as guidance, then confirm through an official company channel.")

with st.form("analysis_form"):
    jd = st.text_area(
        "Job description",
        height=220,
        placeholder="Paste the complete job or internship posting here, including company, role, salary, contact details, and any links.",
        help="The current MVP checks the text you paste. It does not fetch the posting's links.",
    )
    submitted = st.form_submit_button("Analyze posting", type="primary", use_container_width=True)

st.caption("This project has two modes: rule-based checks work immediately; CrewAI reasoning and ADK company verification require the agent dependencies, a model API key, and the verifier service.")

if submitted:
    if len(jd.strip()) < 30:
        st.warning("Please paste a more complete description (at least 30 characters).")
    else:
        with st.spinner("Reviewing the posting text…"):
            try:
                result = analyze_posting(jd.strip())
            except ValueError as error:
                st.warning(str(error))
                st.stop()

        st.divider()
        st.markdown('<p class="section-label">Assessment</p>', unsafe_allow_html=True)
        category = result.decision.category
        badge = {"Low Risk": "🟢", "Needs Verification": "🟡", "High Risk": "🔴"}[category]
        st.subheader(f"{badge} {category}")
        st.write(result.decision.summary)
        st.caption("This is a screening result, not proof that a posting or company is fraudulent.")

        details, findings = st.columns([1, 1.4], gap="large")
        with details:
            st.markdown("#### Details found in the posting")
            values = result.posting.model_dump()
            display_names = {
                "company_name": "Company", "role": "Role", "salary_text": "Salary",
                "location": "Location", "experience": "Experience",
                "employment_type": "Employment type", "contact_email": "Contact email", "links": "Links",
                "requirements": "Requirements",
            }
            for key, label in display_names.items():
                value = values[key]
                if isinstance(value, list):
                    value = ", ".join(value) if value else "Not provided"
                st.markdown(f"**{label}:** {value or 'Not provided'}")
            st.caption("Only common fields that the parser recognizes appear above. Unrecognized text is preserved below.")

        with findings:
            st.markdown("#### Text-based findings")
            if result.evidence:
                for item in result.evidence:
                    with st.container(border=True):
                        st.markdown(f"**{item.title}** · {item.severity.title()} signal")
                        st.markdown(f"> {item.quote}")
                        st.write(item.explanation)
            else:
                st.write("No phrases covered by the current rules were found. This does not confirm that the posting is legitimate.")

        st.markdown("#### Nearest historical examples")
        if result.similar_postings:
            st.caption(result.similarity_review.summary if result.similarity_review else "Nearest labeled postings from the local FAISS index. Similarity is supporting context, not proof.")
            st.info(
                "These are the closest records the search found, even if their job titles differ. "
                "Cosine similarity is a text-match score, not the chance that your posting is genuine. "
                "Each dataset label applies only to that historical record."
            )
            if result.similarity_review:
                st.caption(result.similarity_review.limitation)
            examples = [item.model_dump() if hasattr(item, "model_dump") else item for item in result.similar_postings]
            st.dataframe(
                [
                    {"Record": item["posting_id"], "Dataset label": item["label"], "Cosine similarity": item["similarity"], "Title": item.get("title", ""), "Excerpt": item.get("excerpt", "")}
                    for item in examples
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.write("No historical index is available. Add the labeled CSV and build the FAISS index to enable this check.")

        st.markdown("#### Company check")
        check = result.company_check
        st.write(f"Status: **{check.status.replace('_', ' ').title()}**")
        for finding in check.findings:
            st.write(f"- {finding}")
        for source in check.sources:
            st.markdown(f"- [Source]({source})")

        st.divider()
        with st.expander(f"View the full job description you submitted ({len(jd)} characters)"):
            st.text(jd)

        st.markdown("#### What to do next")
        st.write("Check the role on the company's official careers website. Contact the company using details from that website, and never pay a fee or share passwords, PINs, or one-time codes to apply.")
        st.caption(f"Analysis reference: {result.run_id} · saved locally on this computer")
        st.caption(
            f"Elapsed time: {result.duration_seconds:.2f} seconds · "
            f"Recorded model usage: {result.token_usage.get('prompt_tokens', 0):,} input + "
            f"{result.token_usage.get('completion_tokens', 0):,} output tokens"
        )
        with st.expander("Workflow log"):
            for event in result.workflow_events:
                st.write(f"- {event}")
