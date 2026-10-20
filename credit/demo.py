"""Starting tables for a demo deal and a blank deal.

The demo borrower is fictional and every figure is illustrative.
"""
from __future__ import annotations

import pandas as pd

YEARS = ["Y1", "Y2", "Y3", "Y4", "Y5"]

DOC_CATEGORIES = [
    "Term sheet",
    "Audited financials",
    "Management accounts / LTM",
    "Financial model",
    "Credit agreement",
    "Existing debt schedule",
    "Customer concentration",
    "AR aging",
    "Quality of earnings",
    "General ledger / trial balance",
    "Bank statements",
    "Legal & corporate",
    "Other",
]
DOC_STATUS = ["Received", "Illegible", "Requested", "Missing"]

# key, figure, kind  (kind drives what the auditor accepts as a source)
INPUT_ROWS = [
    ("ltm_revenue", "LTM revenue", "historical"),
    ("ltm_ebitda", "LTM EBITDA (as underwritten)", "historical"),
    ("cash", "Cash on balance sheet", "historical"),
    ("other_debt", "Other debt remaining", "historical"),
    ("other_debt_rate", "Other debt rate %", "contract"),
    ("facility", "Facility size", "contract"),
    ("spread", "Spread %", "contract"),
    ("floor", "Base-rate floor %", "contract"),
    ("amort_pct", "Annual amortisation % of principal", "contract"),
    ("pik_pct", "% of coupon paid in kind", "contract"),
    ("tax_rate", "Cash tax rate %", "assumption"),
]

ASSUMPTION_ROWS = [
    ("growth", "Revenue growth %"),
    ("margin", "EBITDA margin %"),
    ("capex_pct", "Capex % revenue"),
    ("nwc_pct", "NWC investment % of revenue change"),
    ("da_pct", "D&A % revenue"),
    ("base_rate", "Base rate (forward curve) %"),
]

COVENANTS = [
    ("total_leverage", "Max total leverage (x)"),
    ("dscr", "Min DSCR (x)"),
    ("fccr", "Min FCCR (x)"),
    ("interest_coverage", "Min interest coverage (x)"),
]

SIGNAL_ROWS = [
    ("revenue_prior", "Revenue — prior year"),
    ("revenue_current", "Revenue — current year"),
    ("ar_prior", "Accounts receivable — prior year end"),
    ("ar_current", "Accounts receivable — current year end"),
    ("reported_ebitda", "Reported EBITDA"),
    ("adjusted_ebitda", "Adjusted EBITDA"),
    ("undrawn_revolver", "Undrawn revolver"),
    ("maturities_24m", "Debt maturing within 24 months"),
    ("monthly_burn", "Monthly cash burn (0 if generative)"),
]

AGREEMENT_TERMS = [
    ("Financial covenant(s) & test frequency", "Financial covenants"),
    ("Equity cure rights", "Financial covenants"),
    ("Consolidated EBITDA add-backs (cap, look-forward)", "Definitions"),
    ("Incremental / free-and-clear capacity", "Debt baskets"),
    ("MFN protection (margin, sunset)", "Debt baskets"),
    ("Restricted payments builder / starter basket", "Negative covenants"),
    ("Investments in unrestricted subsidiaries (J.Crew)", "Negative covenants"),
    ("Liability management / uptier protection (Serta)", "Amendments"),
    ("Release of guarantors (Chewy)", "Guarantees & security"),
    ("Asset sale sweep & reinvestment rights", "Mandatory prepayments"),
    ("Excess cash flow sweep", "Mandatory prepayments"),
    ("Required-lender thresholds / sacred rights", "Amendments"),
]
ASSESSMENTS = ["Standard", "Loose", "Aggressive", "Not reviewed"]


def _inputs(values: dict, sources: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"key": k, "figure": f, "value": float(values.get(k, 0.0)),
             "source": sources.get(k, ""), "kind": kind}
            for k, f, kind in INPUT_ROWS
        ]
    )


def _assumptions(values: dict, sources: dict) -> pd.DataFrame:
    rows = []
    for k, label in ASSUMPTION_ROWS:
        row = {"key": k, "assumption": label}
        row.update(dict(zip(YEARS, values.get(k, [0.0] * 5))))
        row["source"] = sources.get(k, "")
        rows.append(row)
    return pd.DataFrame(rows)


def demo() -> dict:
    deal = {
        "deal_type": "(A) Senior secured / unitranche direct loan",
        "data_source": "(D) A mix",
        "borrower": "Demo Borrower Co (fictional)",
        "sector": "B2B logistics software",
        "size": "225.0m unitranche",
        "rate": "SOFR + 575bps, 1.00% floor",
        "date": "2026-12-15",
        "signer": "",
    }
    register = pd.DataFrame(
        [
            ("D01", "Term sheet v3 (demo)", "Term sheet", 6, "Received", False),
            ("D02", "FY23–FY25 audited financials (demo)", "Audited financials", 84, "Received", False),
            ("D03", "LTM Sep-26 management accounts (demo)", "Management accounts / LTM", 22, "Received", False),
            ("D04", "Sponsor model (demo)", "Financial model", 1, "Received", False),
            ("D05", "Draft credit agreement (demo)", "Credit agreement", 212, "Received", False),
            ("D06", "Quality of earnings report (demo)", "Quality of earnings", 48, "Received", False),
            ("D07", "AR aging Sep-26 (demo)", "AR aging", 3, "Received", False),
            ("D08", "Trial balance FY25 (demo)", "General ledger / trial balance", 12, "Received", False),
            ("D09", "Customer cube (demo)", "Customer concentration", 1, "Requested", False),
        ],
        columns=["id", "document", "category", "pages", "status", "uploaded"],
    )
    inputs = _inputs(
        dict(ltm_revenue=250.0, ltm_ebitda=50.0, cash=15.0, other_debt=0.0, other_debt_rate=0.0,
             facility=225.0, spread=5.75, floor=1.0, amort_pct=1.0, pik_pct=0.0, tax_rate=25.0),
        dict(ltm_revenue="D03 p.4", ltm_ebitda="D06 p.11", cash="D03 p.9", other_debt="D01 p.2",
             other_debt_rate="D01 p.2", facility="D01 p.1", spread="D01 p.3", floor="D01 p.3",
             amort_pct="D01 p.3", pik_pct="D01 p.3",
             tax_rate="ASSUMPTION: statutory blended rate, no NOLs per D02"),
    )
    assumptions = _assumptions(
        dict(growth=[6, 6, 5, 5, 4], margin=[20, 20.5, 21, 21, 21], capex_pct=[3] * 5,
             nwc_pct=[10] * 5, da_pct=[2.5] * 5, base_rate=[4.0, 3.75, 3.5, 3.5, 3.5]),
        dict(growth="ASSUMPTION: sponsor case less 2pp; 3-yr CAGR 8% per D02",
             margin="ASSUMPTION: flat to LTM 20% with modest operating leverage",
             capex_pct="ASSUMPTION: 3-yr historical average per D02 p.40",
             nwc_pct="ASSUMPTION: historical NWC intensity per D06 p.30",
             da_pct="ASSUMPTION: in line with FY25 per D02 p.38",
             base_rate="PULLED: forward SOFR curve"),
    )
    covenants = pd.DataFrame(
        [
            {"key": "total_leverage", "covenant": "Max total leverage (x)", "active": True, "level": 6.0, "source": "D01 p.4"},
            {"key": "dscr", "covenant": "Min DSCR (x)", "active": True, "level": 1.25, "source": "D01 p.4"},
            {"key": "fccr", "covenant": "Min FCCR (x)", "active": True, "level": 1.10, "source": "D01 p.4"},
            {"key": "interest_coverage", "covenant": "Min interest coverage (x)", "active": False, "level": 1.75, "source": ""},
        ]
    )
    scenarios = pd.DataFrame(
        [
            {"scenario": "Rates +200bps", "rate shock bps": 200.0, "revenue shock %": 0.0, "margin shock pp": 0.0, "key driver": "Base rate path +200bps"},
            {"scenario": "Rates +400bps", "rate shock bps": 400.0, "revenue shock %": 0.0, "margin shock pp": 0.0, "key driver": "Base rate path +400bps"},
            {"scenario": "Revenue -15%", "rate shock bps": 0.0, "revenue shock %": 15.0, "margin shock pp": 2.0, "key driver": "Loss of top-2 customers"},
            {"scenario": "Severe downside", "rate shock bps": 200.0, "revenue shock %": 25.0, "margin shock pp": 4.0, "key driver": "Recession + rates higher for longer"},
        ]
    )
    signals = pd.DataFrame(
        [
            {"key": k, "figure": f, "value": v, "source": s}
            for (k, f), v, s in zip(
                SIGNAL_ROWS,
                [230.0, 250.0, 38.0, 46.0, 42.0, 50.0, 20.0, 0.0, 0.0],
                ["D02 p.12", "D03 p.4", "D02 p.18", "D07 p.1", "D02 p.12", "D06 p.11", "D01 p.2", "D01 p.2", "D03 p.9"],
            )
        ]
    )
    assets = pd.DataFrame(
        [
            {"asset": "Accounts receivable", "book value": 46.0, "base recovery %": 85.0, "stress recovery %": 70.0, "source": "D07 p.1"},
            {"asset": "Inventory", "book value": 8.0, "base recovery %": 60.0, "stress recovery %": 40.0, "source": "D03 p.9"},
            {"asset": "PP&E", "book value": 30.0, "base recovery %": 50.0, "stress recovery %": 30.0, "source": "D02 p.20"},
            {"asset": "Software & IP", "book value": 90.0, "base recovery %": 25.0, "stress recovery %": 10.0, "source": "D02 p.22"},
        ]
    )
    valuation = pd.DataFrame(
        [
            {"item": "Distressed EBITDA — base", "value": 35.0, "source": "ASSUMPTION: 30% below LTM EBITDA at default"},
            {"item": "EV multiple — base (x)", "value": 6.0, "source": "ASSUMPTION: 2 turns below sector precedent"},
            {"item": "Distressed EBITDA — stress", "value": 28.0, "source": "ASSUMPTION: 44% below LTM EBITDA"},
            {"item": "EV multiple — stress (x)", "value": 4.5, "source": "ASSUMPTION: trough multiple"},
            {"item": "Admin / priority claims", "value": 8.0, "source": "ASSUMPTION: 3% of facility for admin, tax, wages"},
            {"item": "Revolver drawn at default", "value": 20.0, "source": "D01 p.2"},
        ]
    )
    recon = pd.DataFrame(
        [
            {"figure": "LTM revenue", "model value": 250.0, "ledger value": 249.6, "ledger source": "D08 TB acct 4000-4999", "tolerance %": 0.5, "note": ""},
            {"figure": "Reported EBITDA", "model value": 42.0, "ledger value": 41.1, "ledger source": "D08 TB build", "tolerance %": 0.5, "note": "Gap to QoE bridge; chase"},
            {"figure": "Cash", "model value": 15.0, "ledger value": 15.0, "ledger source": "Bank statement Sep-26", "tolerance %": 0.0, "note": ""},
            {"figure": "Accounts receivable", "model value": 46.0, "ledger value": None, "ledger source": "", "tolerance %": 0.5, "note": "AR sub-ledger not yet in data room"},
        ]
    )
    terms = _terms(
        {
            0: ("§7.11", "Leverage and FCCR tested quarterly from first full quarter", "Standard", 1),
            1: ("§8.04", "5 cures, 2 in any 4 quarters, cure counts as EBITDA", "Loose", 3),
            2: ("§1.01 'Consolidated EBITDA' (k)", "Uncapped synergies with 24-month look-forward", "Aggressive", 5),
            3: ("§2.14", "Free-and-clear greater of 1.0x EBITDA and 50.0m", "Loose", 3),
            4: ("§2.14(e)", "50bps MFN, 6-month sunset", "Loose", 3),
            5: ("§7.06", "Builder basket from 50% CNI, no leverage test on starter", "Aggressive", 4),
        }
    )
    return dict(deal=deal, register=register, inputs=inputs, assumptions=assumptions,
                covenants=covenants, scenarios=scenarios, signals=signals, assets=assets,
                valuation=valuation, recon=recon, terms=terms)


def _terms(filled: dict) -> pd.DataFrame:
    rows = []
    for i, (term, cat) in enumerate(AGREEMENT_TERMS):
        sec, summary, assess, risk = filled.get(i, ("", "", "Not reviewed", 3))
        rows.append({"term": term, "category": cat, "section": sec, "summary": summary,
                     "assessment": assess, "risk (1-5)": risk})
    return pd.DataFrame(rows)


def blank() -> dict:
    d = demo()
    d["deal"] = {k: "" for k in d["deal"]}
    d["deal"]["deal_type"] = d["deal"]["data_source"] = None
    d["register"] = d["register"].iloc[0:0]
    for name in ("inputs", "signals", "valuation"):
        d[name]["value"] = 0.0
        d[name]["source"] = ""
    for name in ("assets", "recon"):
        d[name] = d[name].iloc[0:0]
    a = d["assumptions"]
    a[YEARS] = 0.0
    a["source"] = ""
    d["covenants"]["level"] = 0.0
    d["covenants"]["active"] = False
    d["covenants"]["source"] = ""
    d["terms"] = _terms({})
    return d
