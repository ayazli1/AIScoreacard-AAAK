"""Prompt 03 + 04: cash flow / DSCR model, covenant headroom and stress testing.

All amounts are in the deal currency, millions. Rates and percentages are
entered as percents (5.0 means 5%).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ModelInputs:
    # Historicals (must tie to the data room)
    ltm_revenue: float
    ltm_ebitda: float
    cash: float
    other_debt: float
    other_debt_rate: float
    # Facility terms (term sheet)
    facility: float
    spread: float
    floor: float
    amort_pct: float
    pik_pct: float
    tax_rate: float
    # Forward assumptions, one value per projection year
    growth: list[float] = field(default_factory=list)
    margin: list[float] = field(default_factory=list)
    capex_pct: list[float] = field(default_factory=list)
    nwc_pct: list[float] = field(default_factory=list)
    da_pct: list[float] = field(default_factory=list)
    base_rate: list[float] = field(default_factory=list)

    @property
    def years(self) -> int:
        return len(self.growth)


@dataclass
class Scenario:
    name: str
    rate_shock_bps: float = 0.0
    revenue_shock_pct: float = 0.0
    margin_shock_pp: float = 0.0
    driver: str = ""


# metric column -> (label, direction). "max" covenants breach when the metric
# goes above the level, "min" covenants when it falls below.
METRICS = {
    "total_leverage": ("Total leverage (x)", "max"),
    "dscr": ("DSCR (x)", "min"),
    "fccr": ("FCCR (x)", "min"),
    "interest_coverage": ("Interest coverage (x)", "min"),
}

INF = float("inf")


def _ratio(num: float, den: float) -> float:
    if den <= 0:
        return INF if num > 0 else 0.0
    return num / den


def project(
    inp: ModelInputs,
    scenario: Scenario | None = None,
    ebitda_haircut_pct: float = 0.0,
) -> pd.DataFrame:
    """Annual projection with debt schedule and credit ratios."""
    s = scenario or Scenario("Base")
    rows = []
    prev_rev = inp.ltm_revenue
    balance = inp.facility
    other = inp.other_debt
    sched_amort = inp.facility * inp.amort_pct / 100
    cash = inp.cash
    for t in range(inp.years):
        rev = prev_rev * (1 + inp.growth[t] / 100)
        if t == 0:
            # level shift in year 1; it carries forward through prev_rev
            rev *= 1 - s.revenue_shock_pct / 100
        margin = inp.margin[t] - s.margin_shock_pp
        ebitda = rev * margin / 100 * (1 - ebitda_haircut_pct / 100)
        capex = rev * inp.capex_pct[t] / 100
        d_nwc = (rev - prev_rev) * inp.nwc_pct[t] / 100
        da = rev * inp.da_pct[t] / 100

        all_in = max(inp.base_rate[t] + s.rate_shock_bps / 100, inp.floor) + inp.spread
        interest = balance * all_in / 100
        pik = interest * inp.pik_pct / 100
        cash_interest_facility = interest - pik
        other_interest = other * (inp.other_debt_rate + s.rate_shock_bps / 100) / 100
        cash_interest = cash_interest_facility + other_interest
        amort = min(sched_amort, balance + pik)

        taxable = ebitda - da - interest - other_interest
        taxes = max(0.0, taxable * inp.tax_rate / 100)
        cfads = ebitda - capex - d_nwc - taxes
        debt_service = cash_interest + amort
        fcf = cfads - debt_service

        closing = balance + pik - amort
        total_debt = closing + other
        cash += fcf
        rows.append(
            {
                "year": f"Y{t + 1}",
                "revenue": rev,
                "ebitda": ebitda,
                "margin_pct": margin,
                "capex": capex,
                "d_nwc": d_nwc,
                "cash_taxes": taxes,
                "cfads": cfads,
                "all_in_rate_pct": all_in,
                "opening_balance": balance,
                "interest_total": interest,
                "pik_interest": pik,
                "cash_interest": cash_interest,
                "scheduled_amort": amort,
                "closing_balance": closing,
                "other_debt": other,
                "total_debt": total_debt,
                "debt_service": debt_service,
                "fcf_after_debt_service": fcf,
                "ending_cash": cash,
                "dscr": _ratio(cfads, debt_service),
                "fccr": _ratio(ebitda - capex - taxes, debt_service),
                "interest_coverage": _ratio(ebitda, cash_interest),
                "total_leverage": INF if ebitda <= 0 else total_debt / ebitda,
                "net_leverage": INF if ebitda <= 0 else max(total_debt - cash, 0) / ebitda,
            }
        )
        prev_rev = rev
        balance = closing
    return pd.DataFrame(rows)


def headroom(actual: float, level: float, direction: str) -> float:
    """Percent cushion before breach; negative means breached."""
    if direction == "max":
        if actual == INF:
            return -100.0
        return (level - actual) / level * 100 if level else 0.0
    if actual == INF:
        return 100.0
    return (actual - level) / actual * 100 if actual > 0 else -100.0


def breaches(df: pd.DataFrame, covenants: dict[str, float]) -> dict[str, str | None]:
    """First year each covenant breaches (None if never)."""
    out = {}
    for metric, level in covenants.items():
        direction = METRICS[metric][1]
        first = None
        for _, r in df.iterrows():
            if headroom(r[metric], level, direction) < 0:
                first = r["year"]
                break
        out[metric] = first
    return out


def headroom_table(
    inp: ModelInputs, scenarios: list[Scenario], covenants: dict[str, float]
) -> pd.DataFrame:
    rows = []
    for s in scenarios:
        df = project(inp, s)
        first = breaches(df, covenants)
        for metric, level in covenants.items():
            label, direction = METRICS[metric]
            worst = min(df[metric].tolist(), key=lambda v: headroom(v, level, direction))
            rows.append(
                {
                    "scenario": s.name,
                    "key driver": s.driver,
                    "covenant": label,
                    "level": level,
                    "worst actual": worst,
                    "min headroom %": headroom(worst, level, direction),
                    "first breach": first[metric] or "—",
                }
            )
    return pd.DataFrame(rows)


def _bisect(breached, lo: float, hi: float, iters: int = 40) -> float | None:
    if breached(lo):
        return lo
    if not breached(hi):
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        if breached(mid):
            hi = mid
        else:
            lo = mid
    return hi


def breach_points(inp: ModelInputs, covenants: dict[str, float]) -> pd.DataFrame:
    """For each covenant: EBITDA decline and rate shock that first trips it."""
    rows = []
    for metric, level in covenants.items():
        label, direction = METRICS[metric]

        def tripped_by_haircut(h):
            df = project(inp, ebitda_haircut_pct=h)
            return any(headroom(v, level, direction) < 0 for v in df[metric])

        def tripped_by_rate(bps):
            df = project(inp, Scenario("rate", rate_shock_bps=bps))
            return any(headroom(v, level, direction) < 0 for v in df[metric])

        h = _bisect(tripped_by_haircut, 0.0, 99.0)
        b = _bisect(tripped_by_rate, 0.0, 2000.0)
        rows.append(
            {
                "covenant": label,
                "level": level,
                "EBITDA decline to breach %": h,
                "rate shock to breach (bps)": b,
            }
        )
    return pd.DataFrame(rows)


def first_to_break(
    inp: ModelInputs, scenarios: list[Scenario], covenants: dict[str, float]
) -> tuple[str, str, str] | None:
    """(scenario, covenant, year) of the earliest breach across scenarios."""
    best = None
    for s in scenarios:
        df = project(inp, s)
        for metric, year in breaches(df, covenants).items():
            if year is None:
                continue
            key = (int(year[1:]), s.name)
            if best is None or key < best[0]:
                best = (key, (s.name, METRICS[metric][0], year))
    return best[1] if best else None
