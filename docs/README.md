# JobShield Architecture & Verification Documents

This folder contains the authoritative architecture diagrams, multi-agent sequence flowcharts, benchmark reports, and risk scoring code mappings for JobShield.

---

### Visual Diagrams
* **[`JobShield_Columnar_Flowchart.png`](./JobShield_Columnar_Flowchart.png)**: Complete 5-column swimlane flowchart with explicit Node numbers (`Node 0` to `Node 9`) and starting code line numbers (`L39`, `L45`, `L70`, `L77`, `L88`, `L96`, `L119`, `L415`, `L436`, `L842`).
* **[`JobShield_Agent_Sequence_Flowchart.png`](./JobShield_Agent_Sequence_Flowchart.png)**: Sequential execution flowchart showing the downward multi-agent investigation lifecycle matching the system architectural sketch.

---

### Technical PDF Reports
* **[`JobShield_Code_Mapping_and_Risk_Scoring_Guide.pdf`](./JobShield_Code_Mapping_and_Risk_Scoring_Guide.pdf)**: Complete mathematical risk scoring guide detailing point weightages (+30 strong, +15 moderate, +5 weak, +15 unverified, -10 verified) and exact line portion demarcations in `src/policy.py`.
* **[`JobShield_10_Test_Cases_Benchmark_Report.pdf`](./JobShield_10_Test_Cases_Benchmark_Report.pdf)**: 10-Case real-world academic evaluation covering genuine corporate jobs, upfront fee scams, Telegram task traps, and ambiguous startups.
* **[`JobShield_Sequential_Execution_Dossier.pdf`](./JobShield_Sequential_Execution_Dossier.pdf)**: Exhaustive technical dossier outlining CrewAI state passing, FastMCP tool integration, and guardrail defenses.
