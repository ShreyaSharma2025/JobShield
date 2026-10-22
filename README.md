# JobShield

JobShield reviews a pasted job or internship description and shows **evidence-backed risk signals**. It does not decide that a company is a scam from one clue. The result is `Low Risk`, `Needs Verification`, or `High Risk`.

## Run it on Windows

Open this folder in VS Code. In **Terminal → New Terminal**, run:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
streamlit run app.py
```

Open the localhost link printed in the terminal (normally `http://localhost:8501`). This starts the rule-based MVP. To use CrewAI and Google ADK, follow [TEAM_GUIDE.md](TEAM_GUIDE.md).

## What runs where

`app.py` is the Streamlit screen. `src/flow.py` is the CrewAI Flow coordinator and shared Pydantic state. The Flow calls the CrewAI roles in `src/agent_team.py`, deterministic rules and policy in `src/`, and optionally a separate Google ADK company verifier over A2A. That verifier is in `verification_agent/`; it calls two MCP tools from `src/mcp_server.py` (public web search and RDAP domain lookup). SQLite stores the run, evidence, findings, and workflow events in `data/jobshield.sqlite3`.

The API-key-free mode is intentionally limited: it runs local parsing and rules. Model-backed agents, public search, A2A verification, FAISS similarity, and Langfuse require their respective optional setup. The UI reports unavailable checks rather than pretending they ran.

## Project docs

See [TEAM_GUIDE.md](TEAM_GUIDE.md) for setup, agent explanations, mentor rubric mapping, group sharing, evaluation plan, and deployment steps.

## Safety and data

The labeled EMSCAD dataset is included in this private repository for the course project. Each analysis and its local SQLite history stay on the computer running the app. `.env`, databases, and logs are excluded from Git. Never commit API keys or private student data. A missing or unavailable company result means **inconclusive**, not fraudulent.
