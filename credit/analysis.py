"""Prompts 05, 06, 07 and 10: warning signals, recovery waterfall,
ledger reconciliation and the source-tie auditor."""
from __future__ import annotations

import re

import pandas as pd

# ---------------------------------------------------------------- 05 signals

SEVERITY_ORDER = {"red": 0, "amber": 1, "note": 2, "clear": 3}


def _grade(value: float, amber: float, red: float, higher_is_worse: bool = True) -> str:
    if higher_is_worse:
        return "red" if value >= red else "amber" if value >= amber else "clear"
    return "red" if value <= red else "amber" if value <= amber else "clear"


def credit_signals(f: dict[str, float], src: dict[str, str]) -> pd.DataFrame:
    """Deteriorating-credit signals. `f` holds the figures, `src` their sources."""
    out = []

    def add(signal, figure, severity, implication, keys):
        out.append(
            {
                "signal": signal,
                "figure": figure,
                "severity": severity,
                "implication": implication,
                "source": "; ".join(src.get(k, "") or "UNSOURCED" for k in keys),
            }
        )

    pik = f["pik_share_pct"]
    sev = _grade(pik, 25, 50)
    if sev == "clear" and pik > 0:
        sev = "note"
    add(
        "PIK reliance",
        f"{pik:.0f}% of facility interest paid in kind",
        sev,
        "Cash interest capacity is being deferred; claim grows into a downturn."
        if pik > 0
        else "All interest paid in cash.",
        ["pik_share_pct"],
    )

    rev_g = _growth(f["revenue_prior"], f["revenue_current"])
    ar_g = _growth(f["ar_prior"], f["ar_current"])
    gap = ar_g - rev_g
    add(
        "Receivables vs revenue",
        f"AR growth {ar_g:.1f}% vs revenue growth {rev_g:.1f}% (gap {gap:+.1f}pp)",
        _grade(gap, 10, 25),
        "Revenue may be pulled forward or collections weakening; check AR aging."
        if gap >= 10
        else "Receivables moving in line with revenue.",
        ["revenue_prior", "revenue_current", "ar_prior", "ar_current"],
    )

    adj, rep = f["adjusted_ebitda"], f["reported_ebitda"]
    addback = (adj - rep) / adj * 100 if adj > 0 else 0.0
    add(
        "Add-back aggressiveness",
        f"Add-backs are {addback:.0f}% of adjusted EBITDA ({adj - rep:,.1f})",
        _grade(addback, 15, 30),
        "Leverage on reported EBITDA is materially higher than headline; "
        "test each add-back against QoE."
        if addback >= 15
        else "Adjustments within typical range.",
        ["adjusted_ebitda", "reported_ebitda"],
    )

    liquidity = f["cash"] + f["undrawn_revolver"]
    wall = f["maturities_24m"]
    wall_ratio = wall / liquidity * 100 if liquidity > 0 else (100.0 if wall > 0 else 0.0)
    add(
        "Refinancing wall (24m)",
        f"{wall:,.1f} maturing vs {liquidity:,.1f} liquidity ({wall_ratio:.0f}%)",
        _grade(wall_ratio, 50, 100),
        "Maturities exceed liquidity; refinancing risk sits inside the hold period."
        if wall_ratio >= 100
        else "Near-term maturities covered by liquidity."
        if wall_ratio < 50
        else "Maturities consume a large share of liquidity.",
        ["maturities_24m", "cash", "undrawn_revolver"],
    )

    burn = f["monthly_burn"]
    if burn > 0:
        runway = liquidity / burn
        add(
            "Liquidity runway",
            f"{runway:.0f} months at {burn:,.2f}/month burn",
            _grade(runway, 24, 12, higher_is_worse=False),
            "Company needs external capital inside the runway."
            if runway < 24
            else "Runway comfortable at current burn.",
            ["monthly_burn", "cash", "undrawn_revolver"],
        )
    else:
        add("Liquidity runway", "Cash generative (no burn)", "clear",
            "No runway constraint.", ["monthly_burn"])

    df = pd.DataFrame(out)
    return df.sort_values("severity", key=lambda s: s.map(SEVERITY_ORDER)).reset_index(drop=True)


def _growth(prior: float, current: float) -> float:
    return (current / prior - 1) * 100 if prior > 0 else 0.0


# --------------------------------------------------------------- 06 recovery


def recovery_waterfall(value: float, claims: pd.DataFrame) -> pd.DataFrame:
    """Distribute `value` down the capital structure.

    `claims` needs columns: claim, rank (lower is senior), amount.
    Claims sharing a rank are paid pari passu, pro rata.
    """
    remaining = max(value, 0.0)
    rows = []
    for rank, group in claims.sort_values("rank").groupby("rank", sort=True):
        total = group["amount"].sum()
        paid_total = min(remaining, total)
        remaining -= paid_total
        for _, c in group.iterrows():
            share = c["amount"] / total if total else 0.0
            paid = paid_total * share
            rows.append(
                {
                    "claim": c["claim"],
                    "rank": rank,
                    "amount": c["amount"],
                    "recovered": paid,
                    "recovery %": paid / c["amount"] * 100 if c["amount"] else 0.0,
                    "LGD %": (1 - paid / c["amount"]) * 100 if c["amount"] else 0.0,
                }
            )
    cols = ["claim", "rank", "amount", "recovered", "recovery %", "LGD %"]
    return pd.DataFrame(rows, columns=cols)


def distressed_value(assets: pd.DataFrame, column: str) -> float:
    """Liquidation value: sum of book value x recovery rate in `column`."""
    return float((assets["book value"] * assets[column] / 100).sum())


# ---------------------------------------------------------- 07 reconciliation


def reconcile(rows: pd.DataFrame) -> pd.DataFrame:
    """Columns in: figure, model value, ledger value, ledger source, tolerance %."""
    df = rows.copy()
    df["delta"] = df["model value"] - df["ledger value"]
    tol = df["tolerance %"].fillna(0).abs() / 100 * df["ledger value"].abs()
    has_source = df["ledger source"].fillna("").str.strip() != ""
    has_ledger = df["ledger value"].notna()
    within = df["delta"].abs() <= tol + 1e-9
    df["status"] = "TIED"
    df.loc[~has_ledger, "status"] = "UNTIED — no ledger figure"
    df.loc[has_ledger & ~has_source, "status"] = "UNTIED — no ledger source"
    df.loc[has_ledger & has_source & ~within, "status"] = "UNTIED — delta outside tolerance"
    return df


# ---------------------------------------------------------- 10 source tie-out

DOC_REF = re.compile(r"^\s*(D\d{2,})\b", re.IGNORECASE)


def classify_source(
    source: str,
    kind: str,
    doc_ids: set[str],
    tied_ledger: set[str],
    pulled_allowed: bool,
) -> tuple[str, str]:
    """Return (PASS|FAIL|LABELED, reason) for one figure's source.

    Accepted forms:
      D03 p.12               -> data-room document (must exist in the register)
      LEDGER: <figure name>  -> must be TIED in the reconciliation
      PULLED: <connector>    -> only if the deal setup allows connector data
      ASSUMPTION: <why>      -> allowed for forward assumptions only
    """
    s = (source or "").strip()
    if not s:
        return "FAIL", "no source"
    m = DOC_REF.match(s)
    if m:
        doc = m.group(1).upper()
        if doc in doc_ids:
            return "PASS", f"ties to {doc}"
        return "FAIL", f"{doc} is not in the data-room register"
    upper = s.upper()
    if upper.startswith("LEDGER:"):
        name = s.split(":", 1)[1].strip().lower()
        if name in tied_ledger:
            return "PASS", "tied in reconciliation"
        return "FAIL", "ledger line not tied in reconciliation (prompt 07)"
    if upper.startswith("PULLED:"):
        if pulled_allowed:
            return "PASS", "pulled figure"
        return "FAIL", "deal setup does not allow connector data"
    if upper.startswith("ASSUMPTION"):
        rationale = s.split(":", 1)[1].strip() if ":" in s else ""
        if kind != "assumption":
            return "FAIL", "historical / contractual figure cannot be an assumption"
        if not rationale:
            return "FAIL", "assumption has no rationale"
        return "LABELED", "labeled assumption with rationale"
    return "FAIL", "unrecognised source format"


def source_tie_audit(
    figures: pd.DataFrame,
    doc_ids: set[str],
    tied_ledger: set[str],
    pulled_allowed: bool,
    untied_recon: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    """figures columns: section, figure, value, source, kind. Returns (table, block_list)."""
    df = figures.copy()
    results = [
        classify_source(r["source"], r["kind"], doc_ids, tied_ledger, pulled_allowed)
        for _, r in df.iterrows()
    ]
    df["result"] = [r[0] for r in results]
    df["reason"] = [r[1] for r in results]
    block = [
        f"{r['section']} · {r['figure']} = {r['value']} ({r['reason']})"
        for _, r in df.iterrows()
        if r["result"] == "FAIL"
    ]
    block += [f"Reconciliation · {name} is untied" for name in untied_recon]
    return df, block
