# 🏦 Credit Desk — private credit underwriting app

A Streamlit app that runs the 10-step *Private Credit Underwriting Pack* in order. Each step
has its own tab, a named-reviewer **review gate**, and an optional **✦ Run with Claude** panel
that sends that step's prompt with the desk's data (and the data-room documents) to Claude.

| Step | What the app does |
|---|---|
| 01 Deal setup (sidebar) | Deal type, data source, borrower/sector/size/rate/close, named signer. |
| 02 Data room | Upload PDFs/CSV/XLSX/TXT, or paste figures. Document register (`D01`, `D02`…), MISSING list against what a committee asks for. |
| 03 Model | Revenue/EBITDA projection, FCF, debt schedule (floor, spread, amortisation, PIK), DSCR / FCCR / interest cover / leverage by year. Every input carries a source. |
| 04 Stress | Covenant headroom for base + each scenario, EBITDA-decline and rate-shock breach points, the scenario that breaks first. |
| 05 Signals | PIK reliance, AR vs revenue, add-back share, 24-month maturity wall, liquidity runway, rated red/amber/note. |
| 06 Recovery | Going-concern EV or asset-liquidation value, waterfall by lien (pari passu within a rank), LGD at base and stress. |
| 07 Reconcile | Model vs ledger/bank figures with tolerance; untied figures are flagged. |
| 08 Agreement | Term checklist (EBITDA add-backs, MFN, RP, J.Crew/Serta/Chewy…) with section citations, ranked by risk. |
| 09 IC memo | Memo drafted from steps 03–08 with sources; editable; named human signature required. |
| 10 Auditor | Checks every figure's source. GO only when the BLOCK list is empty — the human still signs. |

### Source convention (enforced by step 10)

- `D03 p.12` — a document in the data-room register with status *Received*
- `LEDGER: <figure>` — passes only if that row is **TIED** in step 07
- `PULLED: <source>` — only when the deal's data source includes a connector (C or D)
- `ASSUMPTION: <rationale>` — allowed for forward assumptions only, and needs a rationale

### Run it

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The app opens on a fictional demo deal; use **New blank deal** to start your own, and
**Export / Import deal (JSON)** to save work. Uploaded files are not included in the export.

Claude features are optional: enter an API key in the sidebar (or set `ANTHROPIC_API_KEY`).
Without one, each panel's **Show prompt text** gives the filled-in prompt to paste into Claude.

Tests: `python -m pytest tests`
