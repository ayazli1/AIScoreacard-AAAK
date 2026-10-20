"""Private Credit Underwriting Desk — runs the 10-prompt underwriting pack in order."""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from credit import ai, analysis, demo, memo
from credit.model import METRICS, ModelInputs, Scenario, breach_points, breaches, first_to_break, headroom_table, project
from credit.prompts import PROMPTS, copyable, system_prompt, user_prompt

st.set_page_config(page_title="Credit Desk", page_icon="🏦", layout="wide")

DEAL_TYPES = [
    "(A) Senior secured / unitranche direct loan",
    "(B) Second lien / mezzanine",
    "(C) Asset-based or specialty finance",
    "(D) Portfolio monitoring on an existing book (not a new deal)",
]
DATA_SOURCES = [
    "(A) Upload the data room",
    "(B) Paste raw figures or a term-sheet excerpt",
    "(C) Pull market and comp data from a connector",
    "(D) A mix",
]
TABLES = ["register", "inputs", "assumptions", "covenants", "scenarios", "signals",
          "assets", "valuation", "recon", "terms"]
STEPS = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10"]


# ------------------------------------------------------------------ state


def load_state(data: dict) -> None:
    ss = st.session_state
    ss.tables = {k: pd.DataFrame(data[k]) if not isinstance(data[k], pd.DataFrame) else data[k]
                 for k in TABLES}
    for k, v in data["deal"].items():
        ss[f"deal_{k}"] = v
    ss.gates = data.get("gates", {})
    ss.ai_out = data.get("ai_out", {})
    ss.memo_text = data.get("memo_text", "")
    ss.paste = data.get("paste", "")
    ss.current = {}
    ss.version = ss.get("version", 0) + 1


if "tables" not in st.session_state:
    st.session_state.docs = {}
    load_state(demo.demo())


def table(name: str, **kwargs) -> pd.DataFrame:
    """Editable table whose latest edits are kept for export and later steps."""
    df = st.data_editor(
        st.session_state.tables[name],
        key=f"ed_{name}_{st.session_state.version}",
        width="stretch",
        hide_index=True,
        **kwargs,
    )
    st.session_state.current[name] = df
    return df


def commit_tables() -> None:
    """Fold in-editor edits into the base tables before replacing them."""
    for k, df in st.session_state.current.items():
        st.session_state.tables[k] = df


def deal() -> dict:
    keys = ["deal_type", "data_source", "borrower", "sector", "size", "rate", "date", "signer"]
    return {k: st.session_state.get(f"deal_{k}") for k in keys}


def export_state() -> str:
    commit_tables()
    return json.dumps(
        {
            "deal": deal(),
            **{k: st.session_state.tables[k].to_dict(orient="records") for k in TABLES},
            "gates": st.session_state.gates,
            "ai_out": st.session_state.ai_out,
            "memo_text": st.session_state.memo_text,
            "paste": st.session_state.get("paste", ""),
        },
        indent=2,
        default=str,
    )


# ------------------------------------------------------------------ helpers


def fmt_df(df: pd.DataFrame, dp: int = 2) -> pd.DataFrame:
    return df.apply(lambda col: col.map(lambda v: memo.fmt(v, dp)) if col.dtype.kind in "fi" else col)


def gate(step: str) -> bool:
    """Review gate: a named reviewer confirms before the next step relies on this one."""
    g = st.session_state.gates.get(step)
    with st.container(border=True):
        st.markdown(f"**Review gate {step}** — {PROMPTS[step]['gate']}")
        if g:
            c1, c2 = st.columns([4, 1])
            c1.success(f"Confirmed by **{g['reviewer']}** at {g['at']}")
            if c2.button("Reopen", key=f"reopen_{step}"):
                st.session_state.gates.pop(step)
                st.rerun()
            return True
        c1, c2 = st.columns([4, 1])
        name = c1.text_input("Reviewer name", key=f"gate_name_{step}", label_visibility="collapsed",
                             placeholder="Reviewer name")
        if c2.button("Confirm", key=f"gate_btn_{step}", disabled=not name.strip()):
            st.session_state.gates[step] = {
                "reviewer": name.strip(),
                "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            }
            st.rerun()
    return False


def step_header(step: str) -> None:
    p = PROMPTS[step]
    st.subheader(f"{step} · {p['title']}")
    st.caption(f"**Output:** {p['output_format']}  \n**Constraint:** {p['constraints']}")
    prev = STEPS[STEPS.index(step) - 1]
    if step != "02" and prev not in st.session_state.gates:
        st.warning(f"Step {prev}'s review gate is still open. The pack runs in order — "
                   "results here rely on unreviewed inputs.")


def claude_docs() -> list[dict]:
    docs = [dict(id=i, **d) for i, d in st.session_state.docs.items()]
    paste = st.session_state.get("paste", "").strip()
    if paste:
        docs.append({"id": "PASTE", "name": "Pasted figures / term-sheet excerpt", "kind": "text", "data": paste})
    return docs


def ai_panel(step: str, payload: str, with_docs: bool = False) -> None:
    """Run this step's prompt with Claude, or copy it to run elsewhere."""
    with st.expander(f"✦ Run prompt {step} with Claude", expanded=False):
        docs = claude_docs() if with_docs else []
        if with_docs:
            st.caption(f"Sends {len(docs)} data-room document(s) plus the desk data below.")
        api_key = st.session_state.get("api_key") or None
        c1, c2 = st.columns([1, 1])
        run = c1.button("Run with Claude", key=f"run_{step}", type="primary")
        show = c2.toggle("Show prompt text", key=f"show_{step}")
        if show:
            st.code(copyable(step, deal(), payload), language="markdown")
        if run:
            try:
                text = st.write_stream(
                    ai.stream_step(api_key, system_prompt(step, deal()), user_prompt(step, deal(), payload), docs)
                )
                st.session_state.ai_out[step] = text
            except RuntimeError as e:
                st.error(str(e))
                if not api_key:
                    st.info("Add a Claude API key in the sidebar, or copy the prompt text into Claude.")
        elif step in st.session_state.ai_out:
            st.markdown(st.session_state.ai_out[step])
        if step in st.session_state.ai_out:
            st.caption("Claude's output is a draft for the reviewer — it does not clear the review gate.")


def csv(df: pd.DataFrame) -> str:
    return df.to_csv(index=False)


# ------------------------------------------------------------------ sidebar: 01


with st.sidebar:
    st.title("🏦 Credit Desk")
    st.caption("Private credit underwriting pack — 10 steps, run in order.")
    st.subheader("01 · Deal setup")
    st.radio("1 · Deal type", DEAL_TYPES, key="deal_deal_type", index=None)
    st.radio("2 · Where does the deal data live?", DATA_SOURCES, key="deal_data_source", index=None)
    st.markdown("**3 · Context**")
    st.text_input("Borrower", key="deal_borrower")
    st.text_input("Sector", key="deal_sector")
    st.text_input("Facility size", key="deal_size")
    st.text_input("Rate basis", key="deal_rate")
    st.text_input("Target close", key="deal_date")
    st.markdown("**4 · Output bar**")
    st.caption("Every figure ties to a data-room source or pulled figure; every assumption is labeled; "
               "a named human signs before committee.")
    st.text_input("Named signer for the credit decision", key="deal_signer")
    d = deal()
    ready = all(d[k] for k in ("deal_type", "data_source", "borrower", "signer"))
    if ready:
        st.success("Desk live. Load the data room the way you chose, then run step 02.")
        if "01" not in st.session_state.gates:
            st.session_state.gates["01"] = {
                "reviewer": d["signer"], "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    else:
        st.session_state.gates.pop("01", None)
        st.info("Answer deal type, data source, borrower and named signer to go live.")

    st.divider()
    st.text_input("Claude API key (optional)", type="password", key="api_key",
                  help="Used only for the ✦ Run with Claude panels. Falls back to ANTHROPIC_API_KEY.")
    st.divider()
    c1, c2 = st.columns(2)
    c1.button("Load demo", on_click=lambda: load_state(demo.demo()), width="stretch")
    c2.button("New blank deal", on_click=lambda: (st.session_state.docs.clear(), load_state(demo.blank())),
              width="stretch")
    imported = st.file_uploader("Import deal JSON", type="json", key="import_json")
    if imported and st.button("Load imported deal", width="stretch"):
        load_state(json.load(imported))
        st.rerun()


# ------------------------------------------------------------------ header

d = deal()
st.title(d["borrower"] or "New deal")
st.caption(" · ".join(x for x in (d["deal_type"], d["sector"], d["size"], d["rate"], d["date"]) if x))
cols = st.columns(10)
for c, s in zip(cols, STEPS):
    c.markdown(f"{'✅' if s in st.session_state.gates else '⬜'} **{s}**")

tabs = st.tabs([f"{s} {PROMPTS[s]['title'].split(' (')[0]}" for s in STEPS[1:]])

# ------------------------------------------------------------------ 02 data room

with tabs[0]:
    step_header("02")
    if d["data_source"] and d["data_source"].startswith(("(A)", "(D)")):
        files = st.file_uploader(
            "Upload data-room documents (PDF, CSV, XLSX, TXT, MD)",
            type=["pdf", "csv", "xlsx", "xls", "txt", "md"],
            accept_multiple_files=True,
        )
        known = {v["name"] for v in st.session_state.docs.values()}
        new = [f for f in files or [] if f.name not in known]
        if new:
            commit_tables()
            reg = st.session_state.tables["register"]
            n = max([int(i[1:]) for i in reg["id"] if str(i)[1:].isdigit()] + [0])
            rows = []
            for f in new:
                n += 1
                doc_id = f"D{n:02d}"
                raw = f.getvalue()
                if f.name.lower().endswith(".pdf"):
                    kind, data = "pdf", raw
                elif f.name.lower().endswith((".xlsx", ".xls")):
                    sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
                    kind = "text"
                    data = "\n\n".join(f"## Sheet: {name}\n{df.to_csv(index=False)}" for name, df in sheets.items())
                else:
                    kind, data = "text", raw.decode("utf-8", errors="replace")
                st.session_state.docs[doc_id] = {"name": f.name, "kind": kind, "data": data}
                rows.append({"id": doc_id, "document": f.name, "category": "Other", "pages": None,
                             "status": "Received", "uploaded": True})
            st.session_state.tables["register"] = pd.concat([reg, pd.DataFrame(rows)], ignore_index=True)
            st.session_state.version += 1
            st.rerun()
    if d["data_source"] and d["data_source"].startswith(("(B)", "(D)")):
        st.text_area("Paste raw figures or a term-sheet excerpt (sent to Claude as document PASTE)",
                     key="paste", height=120)

    st.markdown("**Document register** — assign each document a category and status. "
                "Cite figures as `D03 p.12`. Documents held outside the app can be added as rows.")
    register = table(
        "register",
        num_rows="dynamic",
        column_config={
            "id": st.column_config.TextColumn("ID", required=True),
            "category": st.column_config.SelectboxColumn(options=demo.DOC_CATEGORIES, required=True),
            "status": st.column_config.SelectboxColumn(options=demo.DOC_STATUS, required=True),
            "pages": st.column_config.NumberColumn(format="%d"),
            "uploaded": st.column_config.CheckboxColumn(disabled=True),
        },
    )
    received = register[register["status"] == "Received"]
    doc_ids = {str(i).upper() for i in received["id"]}
    missing = [c for c in demo.DOC_CATEGORIES[:-1] if c not in set(received["category"])]
    flagged = register[register["status"].isin(["Illegible", "Requested", "Missing"])]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**MISSING — committee will ask for:**")
        st.markdown("\n".join(f"- {m}" for m in missing) or "- Nothing missing.")
    with c2:
        st.markdown("**Flagged documents (not citable):**")
        st.markdown("\n".join(f"- {r['id']} {r['document']} — {r['status']}" for _, r in flagged.iterrows())
                    or "- None.")
    ai_panel("02", f"Document register:\n{csv(register)}\nMissing categories: {missing}", with_docs=True)
    gate("02")

# ------------------------------------------------------------------ 03 model

with tabs[1]:
    step_header("03")
    st.markdown("**Historicals and facility terms** (amounts in millions; rates in %)")
    inputs_df = table("inputs", num_rows="fixed", disabled=["key", "figure", "kind"],
                      column_order=["figure", "value", "source", "kind"])
    st.markdown("**Forward assumptions** — tag each row `ASSUMPTION: rationale` or cite the source.")
    assump_df = table("assumptions", num_rows="fixed", disabled=["key", "assumption"],
                      column_order=["assumption", *demo.YEARS, "source"])

    v = dict(zip(inputs_df["key"], inputs_df["value"].fillna(0.0)))
    src = dict(zip(inputs_df["key"], inputs_df["source"].fillna("")))
    a = {r["key"]: [float(r[y] or 0) for y in demo.YEARS] for _, r in assump_df.iterrows()}
    inp = ModelInputs(**{k: float(v[k]) for k in v}, **a)
    base = project(inp)

    view = base[["year", "revenue", "ebitda", "capex", "d_nwc", "cash_taxes", "cfads", "all_in_rate_pct",
                 "cash_interest", "pik_interest", "scheduled_amort", "closing_balance", "total_debt",
                 "fcf_after_debt_service", "ending_cash"]]
    st.markdown("**Projection and debt schedule**")
    st.dataframe(fmt_df(view.set_index("year").T.reset_index().rename(columns={"index": "line"})),
                 width="stretch", hide_index=True)
    st.markdown("**Credit ratios by period**")
    ratios = base[["year", "dscr", "fccr", "interest_coverage", "total_leverage", "net_leverage"]]
    st.dataframe(fmt_df(ratios.set_index("year").T.reset_index().rename(columns={"index": "ratio"})),
                 width="stretch", hide_index=True)
    chart = base.set_index("year")[["total_leverage", "dscr", "fccr"]].replace(float("inf"), None)
    st.line_chart(chart)
    ai_panel("03", f"Inputs:\n{csv(inputs_df)}\nAssumptions:\n{csv(assump_df)}\nModel output:\n{csv(base)}")
    gate("03")

# ------------------------------------------------------------------ 04 stress

with tabs[2]:
    step_header("04")
    st.markdown("**Proposed covenants** — each level must cite the term sheet.")
    cov_df = table("covenants", num_rows="fixed", disabled=["key", "covenant"],
                   column_order=["covenant", "active", "level", "source"])
    covenants = {r["key"]: float(r["level"]) for _, r in cov_df.iterrows() if r["active"] and r["level"]}
    st.markdown("**Stress set** — one key driver per scenario.")
    scen_df = table("scenarios", num_rows="dynamic")
    scenarios = [Scenario("Base", driver="Underwriting case")] + [
        Scenario(r["scenario"], float(r["rate shock bps"] or 0), float(r["revenue shock %"] or 0),
                 float(r["margin shock pp"] or 0), r["key driver"] or "")
        for _, r in scen_df.dropna(subset=["scenario"]).iterrows()
    ]
    if covenants:
        ht = headroom_table(inp, scenarios, covenants)
        st.markdown("**Covenant headroom (base + each stress)**")
        st.dataframe(
            fmt_df(ht).style.apply(
                lambda r: ["background-color: rgba(220,38,38,.18)" if r["first breach"] != "—" else ""] * len(r),
                axis=1),
            width="stretch", hide_index=True)
        bp = breach_points(inp, covenants)
        st.markdown("**Breach point per covenant** (uniform EBITDA decline, or parallel rate shock, that first trips it)")
        st.dataframe(fmt_df(bp, 1).replace("—", "No breach in range"), width="stretch", hide_index=True)
        ftb = first_to_break(inp, scenarios, covenants)
        if ftb:
            st.error(f"First to break: **{ftb[0]}** trips **{ftb[1]}** in {ftb[2]}.")
        else:
            st.success("No scenario breaches a covenant over the projection.")
        base_breach = any(breaches(base, covenants).values())
        base_ht = ht[ht["scenario"] == "Base"][["covenant", "level", "worst actual", "min headroom %", "first breach"]]
        min_headroom = float(base_ht["min headroom %"].min())
    else:
        st.info("Activate at least one covenant with a level.")
        ht = bp = base_ht = pd.DataFrame()
        ftb, base_breach, min_headroom = None, False, 100.0
    ai_panel("04", f"Covenants:\n{csv(cov_df)}\nScenarios:\n{csv(scen_df)}\nHeadroom:\n{csv(ht)}\n"
                   f"Breach points:\n{csv(bp)}\nFirst to break: {ftb}")
    gate("04")

# ------------------------------------------------------------------ 05 signals

with tabs[3]:
    step_header("05")
    st.markdown("**Signal figures** — PIK share comes from the facility terms in step 03.")
    sig_df = table("signals", num_rows="fixed", disabled=["key", "figure"], column_order=["figure", "value", "source"])
    f = dict(zip(sig_df["key"], sig_df["value"].fillna(0.0)))
    f["pik_share_pct"] = inp.pik_pct
    f["cash"] = inp.cash
    s_src = dict(zip(sig_df["key"], sig_df["source"].fillna("")))
    s_src["pik_share_pct"] = src["pik_pct"]
    s_src["cash"] = src["cash"]
    signals = analysis.credit_signals(f, s_src)
    colors = {"red": "🔴", "amber": "🟠", "note": "🔵", "clear": "🟢"}
    for _, r in signals.iterrows():
        with st.container(border=True):
            st.markdown(f"{colors[r['severity']]} **{r['signal']}** — {r['figure']}  \n{r['implication']}  \n"
                        f"<small>Source: {r['source']}</small>", unsafe_allow_html=True)
    ai_panel("05", f"Signal figures:\n{csv(sig_df)}\nComputed signals:\n{csv(signals)}\nModel:\n{csv(base)}",
             with_docs=True)
    gate("05")

# ------------------------------------------------------------------ 06 recovery

with tabs[4]:
    step_header("06")
    c1, c2 = st.columns(2)
    method = c1.radio("Recovery value basis", ["Going-concern EV (EBITDA × multiple)", "Asset liquidation"],
                      key="rec_method", horizontal=True)
    default_year = c2.selectbox("Assumed default year (sets our claim incl. accrued PIK)", list(base["year"]),
                                index=min(1, len(base) - 1), key="rec_year")
    st.markdown("**Asset values** (book values tie to the data room; recovery rates are assumptions)")
    assets = table("assets", num_rows="dynamic")
    st.markdown("**Valuation and priority claims**")
    val_df = table("valuation", num_rows="fixed", disabled=["item"])
    val = dict(zip(val_df["item"], val_df["value"].fillna(0.0)))
    assets_n = assets.fillna({"book value": 0.0, "base recovery %": 0.0, "stress recovery %": 0.0})
    values = {
        "Base": val["Distressed EBITDA — base"] * val["EV multiple — base (x)"]
        if method.startswith("Going") else analysis.distressed_value(assets_n, "base recovery %"),
        "Stress": val["Distressed EBITDA — stress"] * val["EV multiple — stress (x)"]
        if method.startswith("Going") else analysis.distressed_value(assets_n, "stress recovery %"),
    }
    row = base[base["year"] == default_year].iloc[0] if len(base) else None
    our_claim = float(row["closing_balance"]) if row is not None else inp.facility
    lien = "First lien / unitranche" if not (d["deal_type"] or "").startswith("(B)") else "Second lien / mezz"
    claims = pd.DataFrame([
        {"claim": "Admin / priority", "rank": 0, "amount": val["Admin / priority claims"]},
        {"claim": "Revolver (super senior)", "rank": 1, "amount": val["Revolver drawn at default"]},
        {"claim": f"Our facility — {lien}", "rank": 2 if lien.startswith("First") else 3, "amount": our_claim},
        {"claim": "Other debt", "rank": 4, "amount": inp.other_debt},
    ])
    claims = claims[claims["amount"] > 0]
    recov = {}
    cols = st.columns(2)
    for c, (case, value) in zip(cols, values.items()):
        wf = analysis.recovery_waterfall(value, claims)
        ours = wf[wf["claim"].str.startswith("Our facility")]
        recov[case] = float(ours["recovery %"].iloc[0]) if len(ours) else 0.0
        with c:
            st.metric(f"{case}: value {value:,.1f}", f"LGD {100 - recov[case]:.0f}%",
                      f"recovery {recov[case]:.0f}%", delta_color="off")
            st.dataframe(fmt_df(wf, 1), width="stretch", hide_index=True)
    ai_panel("06", f"Method: {method}; default year {default_year}\nAssets:\n{csv(assets)}\n"
                   f"Valuation:\n{csv(val_df)}\nClaims:\n{csv(claims)}\nRecovery: {recov}", with_docs=True)
    gate("06")

# ------------------------------------------------------------------ 07 reconciliation

with tabs[5]:
    step_header("07")
    st.markdown("**Reconciliation** — model value vs ledger/bank figure. Inputs cited as `LEDGER: <figure>` "
                "pass the audit only when the row here is TIED.")
    recon_in = table("recon", num_rows="dynamic")
    recon = analysis.reconcile(recon_in.fillna({"tolerance %": 0.0, "model value": 0.0}).astype({"model value": float}))
    st.dataframe(
        fmt_df(recon[["figure", "model value", "ledger value", "ledger source", "delta", "status", "note"]]).style.apply(
            lambda r: ["color: #dc2626" if str(r["status"]).startswith("UNTIED") else ""] * len(r), axis=1),
        width="stretch", hide_index=True)
    untied = recon[recon["status"] != "TIED"]["figure"].astype(str).tolist()
    tied = {str(x).strip().lower() for x in recon[recon["status"] == "TIED"]["figure"]}
    if untied:
        st.error("Untied figures: " + ", ".join(untied))
    else:
        st.success("All reconciled figures tie.")
    ai_panel("07", f"Reconciliation:\n{csv(recon)}\nModel inputs:\n{csv(inputs_df)}", with_docs=True)
    gate("07")

# ------------------------------------------------------------------ 08 credit agreement

with tabs[6]:
    step_header("08")
    terms = table(
        "terms",
        num_rows="dynamic",
        column_config={
            "assessment": st.column_config.SelectboxColumn(options=demo.ASSESSMENTS, required=True),
            "risk (1-5)": st.column_config.NumberColumn(min_value=1, max_value=5, step=1),
            "summary": st.column_config.TextColumn(width="large"),
        },
    )
    terms = terms.fillna({"section": "", "risk (1-5)": 3, "assessment": "Not reviewed"})
    ranked = terms[terms["assessment"].isin(["Loose", "Aggressive"])].sort_values("risk (1-5)", ascending=False)
    st.markdown("**Lender-unfriendly terms, ranked by risk**")
    for _, r in ranked.iterrows():
        st.markdown(f"- **{int(r['risk (1-5)'])}/5 · {r['term']}** ({r['assessment']}) — {r['summary']} "
                    f"_[{r['section'] or 'SECTION MISSING'}]_")
    unreviewed = terms[terms["assessment"] == "Not reviewed"]["term"].tolist()
    if unreviewed:
        st.warning("Not yet reviewed: " + "; ".join(unreviewed))
    ai_panel("08", f"Desk term checklist:\n{csv(terms)}", with_docs=True)
    gate("08")

# ------------------------------------------------------------------ 10 audit inputs (needed by memo)

figs = []
for _, r in inputs_df.iterrows():
    figs.append(("03 Inputs", r["figure"], r["value"], r["source"], r["kind"]))
for _, r in assump_df.iterrows():
    figs.append(("03 Assumptions", r["assumption"], ", ".join(memo.fmt(r[y]) for y in demo.YEARS),
                 r["source"], "assumption"))
for _, r in cov_df[cov_df["active"]].iterrows():
    figs.append(("04 Covenants", r["covenant"], r["level"], r["source"], "contract"))
for _, r in sig_df.iterrows():
    figs.append(("05 Signals", r["figure"], r["value"], r["source"], "historical"))
for _, r in assets.dropna(subset=["asset"]).iterrows():
    figs.append(("06 Assets", f"{r['asset']} book value", r["book value"], r["source"], "historical"))
for _, r in val_df.iterrows():
    kind = "historical" if r["item"].startswith("Revolver") else "assumption"
    figs.append(("06 Valuation", r["item"], r["value"], r["source"], kind))
ca_docs = register[(register["category"] == "Credit agreement") & (register["status"] == "Received")]["id"]
ca_id = str(ca_docs.iloc[0]).upper() if len(ca_docs) else None
for _, r in ranked.iterrows():
    # agreement terms cite a section of the credit agreement held in the register
    section = str(r["section"]).strip()
    figs.append(("08 Agreement", r["term"], r["assessment"],
                 f"{ca_id} {section}" if ca_id and section else "", "contract"))
figures = pd.DataFrame(figs, columns=["section", "figure", "value", "source", "kind"])
figures["source"] = figures["source"].fillna("").astype(str)
figures["value"] = figures["value"].map(memo.fmt)

pulled_ok = bool(d["data_source"]) and d["data_source"].startswith(("(C)", "(D)"))
audit_df, block = analysis.source_tie_audit(figures, doc_ids, tied, pulled_ok, untied)

# ------------------------------------------------------------------ 09 memo

with tabs[7]:
    step_header("09")
    rec = memo.desk_recommendation(signals, base_breach, min_headroom, block)
    sig_gate = st.session_state.gates.get("09")
    gaps = [b for b in block][:15]
    if unreviewed:
        gaps.append(f"{len(unreviewed)} credit-agreement term(s) not reviewed")
    if missing:
        gaps.append("Missing data-room categories: " + ", ".join(missing))
    cov_text = "; ".join(
        f"{r['covenant']} {memo.fmt(r['level'])} _[{r['source'] or 'UNSOURCED'}]_"
        for _, r in cov_df[cov_df["active"]].iterrows()) or "none proposed"
    draft = memo.build_memo(dict(
        deal=d, base=base, inputs=inp, src=src, recommendation=rec, signals=signals, terms=terms,
        first_break=ftb, breach_points=bp if len(bp) else pd.DataFrame({"covenant": []}),
        base_headroom=base_ht if len(base_ht) else pd.DataFrame({"covenant": []}),
        recovery_base=recov.get("Base", 0.0), recovery_stress=recov.get("Stress", 0.0),
        covenant_text=cov_text, gaps=gaps,
        signature=f"{sig_gate['reviewer']} — {sig_gate['at']}" if sig_gate else "UNSIGNED — not for committee",
    ))
    st.markdown(f"**Desk draft recommendation:** {rec[0]} — {rec[1]}")
    c1, c2 = st.columns(2)
    if c1.button("Regenerate memo from desk outputs"):
        st.session_state.memo_text = draft
    if "09" in st.session_state.ai_out and c2.button("Use Claude's draft as the memo"):
        st.session_state.memo_text = st.session_state.ai_out["09"]
    # keep an unedited draft in sync with the desk; never overwrite manual edits
    if not st.session_state.memo_text or st.session_state.memo_text == st.session_state.get("last_draft"):
        st.session_state.memo_text = draft
    st.session_state.last_draft = draft
    st.text_area("IC memo (editable markdown)", key="memo_text", height=420)
    with st.expander("Preview"):
        st.markdown(st.session_state.memo_text)
    prior = "\n\n".join(f"### Step {k} output\n{v}" for k, v in sorted(st.session_state.ai_out.items()) if k < "09")
    ai_panel("09", f"Desk memo draft (figures with sources):\n{draft}\n\nPrior Claude outputs:\n{prior}")

    st.markdown("---")
    signer = d["signer"]
    with st.container(border=True):
        st.markdown(f"**Signature — {PROMPTS['09']['gate']}**")
        if sig_gate:
            st.success(f"Signed by **{sig_gate['reviewer']}** at {sig_gate['at']}")
            if st.button("Withdraw signature"):
                st.session_state.gates.pop("09")
                st.rerun()
        elif not signer:
            st.warning("Name the signer in deal setup (sidebar) first.")
        else:
            ack = st.checkbox(f"I, {signer}, have reviewed this memo and take responsibility for the credit decision.")
            if st.button("Sign memo", type="primary", disabled=not ack):
                st.session_state.gates["09"] = {"reviewer": signer,
                                                "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
                st.rerun()
    st.download_button("Download memo (.md)", st.session_state.memo_text,
                       file_name=f"IC_memo_{(d['borrower'] or 'deal').replace(' ', '_')}.md")

# ------------------------------------------------------------------ 10 audit

with tabs[8]:
    step_header("10")
    n_pass = int((audit_df["result"] == "PASS").sum())
    n_lab = int((audit_df["result"] == "LABELED").sum())
    n_fail = int((audit_df["result"] == "FAIL").sum())
    c = st.columns(4)
    c[0].metric("Figures scanned", len(audit_df))
    c[1].metric("Tie to source", n_pass)
    c[2].metric("Labeled assumptions", n_lab)
    c[3].metric("BLOCK list", len(block))
    if block:
        st.error(f"**NO GO** — {len(block)} untied figure(s). A single untied number blocks the memo.")
        st.markdown("**BLOCK list**\n" + "\n".join(f"- {b}" for b in block))
    else:
        st.success("**GO** — every figure ties to a data-room document, a ledger line, or a pulled figure.")
    signed = "09" in st.session_state.gates
    st.info(("Memo is signed by " + st.session_state.gates["09"]["reviewer"]) if signed else
            "The auditor informs the human; the memo still needs its named signature (step 09).")
    if not block and signed and st.button("Release to committee"):
        st.balloons()
    st.markdown("**Pass/fail per figure**")
    st.dataframe(
        audit_df.style.apply(
            lambda r: ["color: #dc2626" if r["result"] == "FAIL" else
                       "color: #b45309" if r["result"] == "LABELED" else ""] * len(r), axis=1),
        width="stretch", hide_index=True)
    st.caption("The deterministic check covers every structured figure. Free text you or Claude add to the memo "
               "is checked by running prompt 10 with Claude below.")
    ai_panel("10", f"Memo:\n{st.session_state.memo_text}\n\nFigure register with sources:\n{csv(audit_df)}\n"
                   f"Data-room register:\n{csv(register)}\nReconciliation:\n{csv(recon)}")
    gate("10")

# Rendered last so the export carries this run's edits from every tab.
with st.sidebar:
    st.download_button("Export deal (JSON)", export_state(), file_name="credit_desk_deal.json",
                       mime="application/json", width="stretch")
