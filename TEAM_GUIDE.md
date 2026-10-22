# JobShield team guide

This guide is the project map. Read sections 1–4 first; the rest helps with the mentor demo.

## 1. Open and run the app

First, each teammate creates a folder named `JobShield` wherever they keep projects. For example, they can create it under Documents or on another drive; the location can differ on every computer. If they are joining through GitHub, follow [GitHub teamwork](#8-github-teamwork) to clone the files into this folder. If files are shared another way, copy/extract the project files into it. Then in VS Code choose **File → Open Folder** and select `JobShield`. Open **Terminal → New Terminal** after opening it.

Check that the terminal is in the project root:

```powershell
Get-Location
Get-ChildItem app.py, src
```

`Get-ChildItem` should show `app.py` and the `src` folder. The printed path can be different on every computer; no command below requires the literal path to be the same.

Python 3.11+ and Git are needed. In PowerShell:

```powershell
py --version
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
streamlit run app.py
```

Open the `localhost` link Streamlit prints. Keep this terminal open while using the app. Paste a complete JD and click **Analyze posting**. Results show extracted details, exact matching text, current risk category, and what checks did or did not run. The local history database is `data/jobshield.sqlite3`.

If PowerShell blocks activation, the per-terminal command is:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

## 2. Turn on the agentic version

Install the framework dependencies inside the active `.venv`:

```powershell
py -m pip install -r requirements-agentic.txt
```

Copy `.env.example` to `.env`; add your own Google model API key. For public company search, add a Brave Search API key. Never paste keys in chat or commit `.env`.

Use **two VS Code terminals**:

1. Terminal A: start the ADK verifier: `py -m verification_agent.server`
2. Terminal B: set `A2A_AGENT_ENABLED=true` in `.env`, then run `streamlit run app.py`

The CrewAI Flow starts from the Streamlit request. It starts an MCP server as a child process when the ADK verifier needs tools. The verifier has two tools: RDAP domain registration lookup and Brave public web search. If keys, network, company name, or the verifier are missing, the result says unavailable/needs verification. An RDAP date or a company search hit alone is not proof that this specific job is authentic.

To enable historical similarity, the dataset is already included at `data/fake_job_postings.csv`. Install `requirements-search.txt` and build a local FAISS index. The embedding model downloads the first time. Similarity stays optional if setup or model download is unavailable.

## 3. Understand the actual agent flow

```text
Student pastes JD in Streamlit
  → guardrail checks text size/characters
  → CrewAI Flow stores shared Pydantic state (run ID, JD, fields, evidence, events)
  → Parser: Python patterns first; CrewAI extraction can improve field understanding
  → Red flags: deterministic Python rules; CrewAI may suggest extra contextual flags
  → Similarity: embed JD → FAISS retrieves labeled training examples (if index exists)
  → Flow router: if company is named and A2A is enabled, call ADK verifier
      → ADK uses MCP RDAP + public web-search tools
  → deterministic policy combines severity and verification state
  → optional CrewAI writer explains the already-selected verdict
  → Pydantic result → Streamlit display + SQLite audit tables + JSONL trace
```

The raw JD is the only evidence source for text signals and parsed fields. The labeled CSV is used only by the similarity search and offline evaluation; it does not train a classifier. Public sources are used only by the ADK/MCP verification stage. Each result should name which source produced the evidence. A missing search result is uncertainty, never proof of fraud.

**What is an agent here?** It is an LLM given one narrow job, input, tools/schema, and limits. A Python function is not automatically an agent. The rules, embedding calculation, SQLite operations, score/category policy, and validation are normal deterministic code. This split makes the output easier to audit.

**CrewAI and CrewAI Flow:** CrewAI agents do bounded language tasks (parser, contextual red-flag reviewer, similarity summary, explanation). CrewAI Flow owns the sequence, Pydantic shared state, and conditional route. The configured policy—not the explanation LLM—chooses the category. See the [CrewAI Flow guide](https://docs.crewai.com/en/concepts/flows).

**ADK and A2A:** Google ADK runs the company verifier as a separate service; the CrewAI app calls its agent card and sends a JSON message over A2A. This demonstrates interoperability between the two mandated frameworks. See [ADK A2A quickstart](https://google.github.io/adk-docs/a2a/quickstart-exposing/) and [A2A protocol](https://a2a-protocol.org/latest/).

**MCP:** The ADK verifier discovers/calls the MCP server's `lookup_domain_rdap` and `search_company_public_sources` tools. MCP is the tool interface; A2A is agent-to-agent communication. They solve different connections. See [ADK MCP tools](https://google.github.io/adk-docs/tools-custom/mcp-tools/).

**RAG vs similarity:** Similarity search retrieves nearest labeled postings and their labels. RAG would retrieve text passages and put them into an LLM prompt as context. The current MVP needs similarity for the requested historical comparison; it does not need a separate RAG layer. RAG may later retrieve a vetted scam-safety policy or official help pages, with source citations.

**SQLite vs FAISS:** SQLite stores each analysis, parsed JSON, evidence, verdict, source checks, runtime/token counts, and workflow events. FAISS stores/searches numeric posting vectors; metadata JSON maps vector positions to dataset IDs, labels, and excerpts. FAISS is not a normal relational database and does not replace SQLite.

**Failures/conflicts:** A tool timeout or absent company match leaves company check unavailable/ambiguous and the verdict at Needs Verification unless strong JD evidence independently warrants High Risk. LLM-added findings must quote the JD, are tagged `LLM_CONTEXT_`, and cannot alone trigger High Risk; the deterministic policy controls the category. One weak signal or a similar fraudulent example never proves fraud. If signals conflict, retain all findings and let the conservative policy avoid Low Risk. The UI shows the evidence and verification status.

## 4. Mentor rubric: what is covered

| Requirement | Project implementation | What to show |
|---|---|---|
| Shared context/state | Pydantic `ReviewState` inside CrewAI Flow; each step writes its output for later steps | Flow log and the final structured result |
| Two MCP tools | RDAP domain lookup + Brave web search | ADK toolset and MCP server code |
| Structured output | Pydantic schemas for fields, evidence, checks, decision, full result | The analysis output and schemas |
| Agent design | Sequential specialist work, conditional verification, deterministic verdict policy | Flow diagram and explain why each role exists |
| Callbacks/logging | CrewAI task/step callbacks, ADK before/after callbacks, JSONL + SQLite events | Workflow log; `data/agent_events.jsonl` |
| CrewAI + ADK mandatory | CrewAI handles main flow/review roles; ADK hosts verifier | `src/flow.py`, `verification_agent/` |
| A2A | CrewAI-side A2A client calls the independently running ADK agent | Run verifier and app in separate terminals |
| Guardrails | Input size checks, exact quote/field validation, Pydantic validation; posting treated as untrusted instructions | Demonstrate injection text ignored and unsupported quote dropped |
| Observability | Local event trace always; optional OpenInference/Langfuse if credentials configured | Run ID and stage events; Langfuse dashboard is optional |
| Evaluation/runtime/cost | Held-out evaluation script reports precision/recall/F1, FP/FN, duration and recorded token use | Compare `rules`, `system`, `single-llm` modes; estimate API cost from your provider's current token prices |
| Cloud deployment | Two Dockerfiles target web app and verifier as separate services | Deploy both, set secrets and verifier URL; actual deploy needs a cloud account |

Do not claim model token costs are measured when model callbacks returned no usage. `scripts/evaluate.py` reports recorded token counts where available; calculate cost as input tokens × provider input rate + output tokens × output rate, using the current model's published price. Report cold-start model download separately from warm request runtime.

## 5. Dataset, splits, and fair evaluation

The EMSCAD Fake Job Posting dataset is included in this private GitHub repository at `data/fake_job_postings.csv`, so teammates get it when they clone. The Kaggle copy lists CC0; a public [Hugging Face mirror](https://huggingface.co/datasets/victor/real-or-fake-fake-jobposting-prediction) also lists CC0. EMSCAD has 17,880 postings from 2012–2014, including 866 fraudulent examples, so it is old and imbalanced and may not represent current Indian internships. Cite the [original EMSCAD research paper](https://doi.org/10.3390/fi9010006) in your presentation, and do not call this data ground truth for all present-day jobs.

After cloning the project, install the search dependencies and build each teammate's local FAISS index:

```powershell
py -m pip install -r requirements-search.txt
py scripts/build_similarity_index.py
```

The script creates a stratified 70% train / 15% validation / 15% test split. Only train rows enter FAISS. Validation is for choosing policy thresholds. Run final metrics once on the held-out test set:

```powershell
py scripts/evaluate.py --mode rules
py scripts/evaluate.py --mode single-llm --limit 100
py scripts/evaluate.py --mode system --limit 100
```

`single-llm` is one LLM with no tools/retrieval; `system` runs the available complete pipeline. LLM modes cost API usage and can take time. Run on all test rows only after checking time/cost; `--limit 100` is a quick sample, not a final result. Compare the same sampled rows by setting the same seed (already fixed in the script). `Needs Verification` is counted as **not declaring fraud** for binary metrics; report the uncertainty/abstention count separately. For the report, define fraud as positive: precision measures how many High Risk calls are actually labeled fraudulent; recall measures how many labeled fraudulent rows were caught; F1 balances precision and recall. False positives are legitimate rows called High Risk; false negatives are fraudulent rows not called High Risk. Also discuss class imbalance and dataset age.

Similarity gives evidence/examples, not a classifier trained on those examples. If using it in the complete system, verify the index metadata contains train-only rows before reporting evaluation. Avoid leakage: never put test rows or near-duplicates into the index.

## 6. Local tables and project files

- `analysis_runs`: run ID, timestamp, pasted JD, parsed JSON, evidence JSON, risk category, summary, policy version.
- `analysis_details`: run ID, company-check JSON, similar-posting JSON, workflow-event list, duration, token-use JSON.
- `workflow_events`: timestamp, run ID, component, status, short detail.
- `data/agent_events.jsonl`: append-only local stage log; do not commit it.

Key code: `app.py` (screen), `src/flow.py` (coordinator/state/conditional route), `src/agent_team.py` (CrewAI roles), `src/parser.py` (field extraction), `src/red_flags.py` (rules), `src/policy.py` (deterministic category), `src/similarity.py` (FAISS retrieval), `src/storage.py` (SQLite), `src/mcp_server.py` (MCP tools), `verification_agent/` (ADK/A2A service).

## 7. Three-person division and roadmap

**Three owners:**

1. **Workflow/agents:** CrewAI roles, Flow/shared state, Pydantic schemas, guardrails, event callbacks.
2. **Data/evaluation:** dataset license/download, split and FAISS, leakage checks, SQLite, evaluation numbers and cost/runtime report.
3. **Verification/demo:** ADK verifier, MCP tools, A2A startup, Streamlit result UX, Docker/cloud deployment guide.

All three should review the integration together. Assign one person to merge/review; agree on schemas before parallel changes.

**Week plan to next week's mentor review:**

- **Day 1:** everyone opens the same repo; one person runs rule-based app; create private GitHub repo and push starter.
- **Day 2:** validate parser/rules on sample JDs; agree Pydantic fields and policy examples.
- **Day 3:** install agent dependencies, configure private API keys, run CrewAI Flow and show intermediate outputs/callback logs.
- **Day 4:** start ADK in a second terminal; demo A2A and both MCP tools with one normal domain and one unavailable/ambiguous case.
- **Day 5:** make sure each teammate has the local dataset; build train-only FAISS on their computer; inspect nearest examples and explain why they are not proof.
- **Day 6:** run same held-out sample in rules, single-LLM, and system modes; record precision/recall/F1, false positives/negatives, runtime, token use, and limitations.
- **Day 7:** prepare clean demo, architecture/data-flow explanation, screenshots, backup local demo, and rehearsal Q&A. Deploy if cloud account and secrets are ready.

## 8. GitHub teamwork

One teammate creates a **private** GitHub repository and shares its URL. Teammates who are joining create their own `JobShield` folder, open PowerShell in that empty folder, and clone the project into it. Replace the URL with the group's real GitHub URL:

```powershell
git clone https://github.com/YOUR-ORG/YOUR-REPO.git .
```

The `.` means “put the repository files in this folder.” After cloning, check `Get-Location` and `Get-ChildItem app.py, src`; the second command should find the app and source folder. The folder's drive and parent location do not need to match anyone else's.

The teammate who owns this current project folder publishes it to the new repository with the **first push**. Run these commands from the existing project folder that contains `app.py`; the folder's local path does not matter:

```powershell
git init
git add README.md TEAM_GUIDE.md .gitignore .dockerignore Dockerfile.web Dockerfile.verifier requirements*.txt app.py src verification_agent scripts
git commit -m "Build JobShield agentic review workflow"
git branch -M main
git remote add origin https://github.com/YOUR-ORG/YOUR-REPO.git
git push -u origin main
```

Invite teammates in GitHub **Settings → Collaborators**. They clone the repo, make a branch per feature, commit small changes, open a PR, and review before merging. Each person installs their own `.venv`; do not share `.venv`, `.env`, dataset, DB, or API keys. `.gitignore` excludes them.

## 9. Cloud deployment

`Dockerfile.web` and `Dockerfile.verifier` build separate containers. Deploy the verifier first as an HTTP service, then the web container. Configure `GOOGLE_API_KEY`, `BRAVE_SEARCH_API_KEY`, `A2A_AGENT_ENABLED=true`, and `A2A_AGENT_URL` using the cloud provider's secret manager/environment settings. The web app must be able to reach the verifier URL. SQLite on an ephemeral container disk is not durable; for a public deployment, switch audit storage to managed PostgreSQL or a mounted persistent volume. For a course demo, a private deployment with demo-only sample postings is safer. No service is deployed by these files; deployment requires your cloud account and secrets.

## 10. Likely mentor questions

1. **Why agents and not one classifier?** The project demonstrates specialist language tasks, tool use, routing, and traceable intermediate outputs. The verdict calculation remains deterministic so evidence and policy are auditable.
2. **Is this trained on the Kaggle dataset?** No new deep-learning classifier is trained. Train split rows are embedded and indexed; validation tunes policy; test estimates performance.
3. **Does similarity prove fraud?** No. It returns labeled examples with vector similarity; shared wording can be common or copied, so it is weak supporting evidence only.
4. **Where does each evidence item come from?** JD quotes from pasted text; historical IDs/labels from train-only dataset; company observations/URLs from RDAP or public search tools. The result carries source types.
5. **What if the company cannot be found?** The check is ambiguous/unavailable and risk remains Needs Verification unless independent JD evidence triggers High Risk.
6. **How do the frameworks communicate?** CrewAI Flow calls Google ADK's separately served verifier using A2A messages. The ADK agent calls the two MCP tools. A2A is agent communication; MCP is tool access.
7. **What is shared state?** A Pydantic `ReviewState` carries the same run ID and the parser, findings, similarity, company check, and event list through Flow steps.
8. **What protects against hallucinations/prompt injection?** The pasted JD is marked untrusted, parsed fields/quotes must be present in the JD, tool results are Pydantic-validated, and category is computed in Python.
9. **Why SQLite and FAISS?** SQLite stores structured audit records; FAISS searches vectors efficiently. One stores run data, the other retrieves similar text.
10. **How do you know it works?** Compare deterministic rules, one LLM, and full system on the same untouched test rows; report precision/recall/F1, FP/FN, runtime/token use, and dataset limitations. Do not claim general real-world accuracy from one old dataset.
