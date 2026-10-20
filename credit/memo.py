"""Prompt 09: assemble the IC memo draft from the desk's sourced outputs."""
from __future__ import annotations

import pandas as pd


def fmt(v, dp: int = 2) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if isinstance(v, float) and v == float("inf"):
        return "n.m."
    if isinstance(v, (int, float)):
        return f"{v:,.{dp}f}"
    return str(v)


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def desk_recommendation(signals: pd.DataFrame, base_breach: bool, min_headroom: float,
                        block: list[str]) -> tuple[str, str]:
    reds = int((signals["severity"] == "red").sum())
    ambers = int((signals["severity"] == "amber").sum())
    if base_breach or reds:
        return "DECLINE OR RESTRUCTURE", (
            f"{'Base case breaches a covenant. ' if base_breach else ''}"
            f"{reds} red signal(s)."
        )
    if ambers or min_headroom < 15:
        return "APPROVE WITH CONDITIONS", (
            f"{ambers} amber signal(s); tightest base-case headroom {min_headroom:.0f}%."
        )
    if block:
        return "APPROVE SUBJECT TO SOURCE TIE-OUT", f"{len(block)} untied figure(s) outstanding."
    return "APPROVE", f"No red/amber signals; tightest base-case headroom {min_headroom:.0f}%."


def build_memo(ctx: dict) -> str:
    d = ctx["deal"]
    base = ctx["base"]
    y1 = base.iloc[0]
    rec, why = ctx["recommendation"]
    signals = ctx["signals"]
    flagged = signals[signals["severity"].isin(["red", "amber"])]
    risks = "\n".join(
        f"- **{r['signal']}** ({r['severity']}): {r['figure']}. {r['implication']} _[{r['source']}]_"
        for _, r in flagged.iterrows()
    ) or "- No red or amber signals from prompt 05."
    terms = ctx["terms"]
    loose = terms[terms["assessment"] != "Standard"].sort_values("risk (1-5)", ascending=False)
    term_lines = "\n".join(
        f"- {r['term']} — {r['assessment']} (risk {int(r['risk (1-5)'])}) _[{r['section'] or 'SECTION MISSING'}]_"
        for _, r in loose.head(5).iterrows()
    ) or "- No lender-unfriendly terms flagged in prompt 08."
    first = ctx["first_break"]
    first_txt = (
        f"The first scenario to break is **{first[0]}**, tripping **{first[1]}** in {first[2]}."
        if first else "No stress scenario breaches a covenant over the projection."
    )
    gaps = ctx["gaps"]
    gap_txt = "\n".join(f"- {g}" for g in gaps) if gaps else "- None."

    return f"""# Investment Committee Memo — {d.get('borrower') or '[BORROWER]'}

**Deal type:** {d.get('deal_type')} · **Sector:** {d.get('sector')} · **Facility:** {d.get('size')} · \
**Rate:** {d.get('rate')} · **Target close:** {d.get('date')}

> Desk draft. Every figure below is carried from steps 03–08 with its source. \
It does not reach committee until a named human signs it.

## 1. Recommendation
**{rec}** — {why}

## 2. Thesis
1. **Debt service capacity.** Y1 DSCR {fmt(y1['dscr'])}x and FCCR {fmt(y1['fccr'])}x on \
EBITDA of {fmt(y1['ebitda'], 1)} _[model, prompt 03; historicals {ctx['src']['ltm_ebitda']}]_.
2. **Deleveraging path.** Total leverage moves from {fmt(base.iloc[0]['total_leverage'])}x in Y1 to \
{fmt(base.iloc[-1]['total_leverage'])}x in {base.iloc[-1]['year']} _[model, prompt 03]_.
3. **Downside protection.** Our facility recovers {fmt(ctx['recovery_base'], 0)}% at base and \
{fmt(ctx['recovery_stress'], 0)}% at stress (LGD {fmt(100 - ctx['recovery_base'], 0)}% / \
{fmt(100 - ctx['recovery_stress'], 0)}%) _[recovery, prompt 06]_.

## 3. Structure and pricing
- Facility {fmt(ctx['inputs'].facility, 1)} at base rate + {fmt(ctx['inputs'].spread)}% \
(floor {fmt(ctx['inputs'].floor)}%), {fmt(ctx['inputs'].amort_pct)}% annual amortisation, \
{fmt(ctx['inputs'].pik_pct, 0)}% of coupon PIK _[{ctx['src']['facility']}; {ctx['src']['spread']}]_.
- Covenants: {ctx['covenant_text']}

## 4. Key risks and mitigants
{risks}

**Credit agreement terms that weaken protection (prompt 08):**
{term_lines}

## 5. Downside case
{first_txt}

{md_table(ctx['breach_points'])}

## 6. Exhibit — base-case covenant headroom
{md_table(ctx['base_headroom'])}

## 7. Gaps the thesis cannot close yet
{gap_txt}

---
**Signed:** {ctx['signature']}
"""
