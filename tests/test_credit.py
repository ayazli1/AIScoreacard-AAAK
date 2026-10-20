import pandas as pd
import pytest

from credit import analysis, demo
from credit.model import ModelInputs, Scenario, breach_points, breaches, headroom, project


def inputs(**over):
    base = dict(ltm_revenue=100.0, ltm_ebitda=20.0, cash=10.0, other_debt=0.0, other_debt_rate=0.0,
                facility=80.0, spread=5.0, floor=1.0, amort_pct=1.0, pik_pct=0.0, tax_rate=25.0,
                growth=[0.0] * 3, margin=[20.0] * 3, capex_pct=[2.0] * 3, nwc_pct=[0.0] * 3,
                da_pct=[2.0] * 3, base_rate=[4.0] * 3)
    base.update(over)
    return ModelInputs(**base)


def test_flat_case_hand_calc():
    df = project(inputs())
    y1 = df.iloc[0]
    assert y1["ebitda"] == pytest.approx(20.0)
    assert y1["cash_interest"] == pytest.approx(80 * 0.09)
    taxes = (20 - 2 - 7.2) * 0.25
    assert y1["cash_taxes"] == pytest.approx(taxes)
    assert y1["dscr"] == pytest.approx((20 - 2 - taxes) / (7.2 + 0.8))
    assert y1["closing_balance"] == pytest.approx(79.2)
    assert y1["total_leverage"] == pytest.approx(79.2 / 20)


def test_floor_and_pik_accrete():
    df = project(inputs(base_rate=[0.0] * 3, pik_pct=50.0, amort_pct=0.0))
    y1 = df.iloc[0]
    assert y1["all_in_rate_pct"] == pytest.approx(6.0)  # floor 1 + spread 5
    assert y1["pik_interest"] == pytest.approx(80 * 0.06 * 0.5)
    assert y1["closing_balance"] == pytest.approx(80 + 2.4)


def test_rate_shock_raises_interest():
    base = project(inputs()).iloc[0]["cash_interest"]
    shocked = project(inputs(), Scenario("x", rate_shock_bps=200)).iloc[0]["cash_interest"]
    assert shocked == pytest.approx(base + 80 * 0.02)


def test_headroom_signs():
    assert headroom(4.0, 5.0, "max") == pytest.approx(20.0)
    assert headroom(6.0, 5.0, "max") < 0
    assert headroom(2.0, 1.5, "min") == pytest.approx(25.0)
    assert headroom(1.0, 1.5, "min") < 0


def test_breach_point_matches_leverage_cushion():
    inp = inputs(amort_pct=0.0)
    covs = {"total_leverage": 5.0}
    bp = breach_points(inp, covs).iloc[0]
    # leverage = 80 / (20 * (1-h)) hits 5.0x at h = 20%
    assert bp["EBITDA decline to breach %"] == pytest.approx(20.0, abs=0.01)
    df = project(inp, ebitda_haircut_pct=21)
    assert breaches(df, covs)["total_leverage"] == "Y1"


def test_waterfall_pari_passu_and_priority():
    claims = pd.DataFrame([
        {"claim": "admin", "rank": 0, "amount": 10.0},
        {"claim": "a", "rank": 1, "amount": 60.0},
        {"claim": "b", "rank": 1, "amount": 30.0},
        {"claim": "junior", "rank": 2, "amount": 50.0},
    ])
    wf = analysis.recovery_waterfall(55.0, claims).set_index("claim")
    assert wf.loc["admin", "recovered"] == pytest.approx(10.0)
    assert wf.loc["a", "recovery %"] == pytest.approx(50.0)
    assert wf.loc["b", "recovery %"] == pytest.approx(50.0)
    assert wf.loc["junior", "LGD %"] == pytest.approx(100.0)


def test_reconcile_statuses():
    rows = pd.DataFrame([
        {"figure": "rev", "model value": 100.0, "ledger value": 100.2, "ledger source": "TB", "tolerance %": 0.5},
        {"figure": "ebitda", "model value": 20.0, "ledger value": 19.0, "ledger source": "TB", "tolerance %": 0.5},
        {"figure": "ar", "model value": 5.0, "ledger value": None, "ledger source": "", "tolerance %": 0.5},
    ])
    status = analysis.reconcile(rows).set_index("figure")["status"]
    assert status["rev"] == "TIED"
    assert status["ebitda"].startswith("UNTIED — delta")
    assert status["ar"].startswith("UNTIED — no ledger figure")


@pytest.mark.parametrize("source,kind,result", [
    ("D01 p.3", "contract", "PASS"),
    ("D99 p.1", "contract", "FAIL"),
    ("", "historical", "FAIL"),
    ("ASSUMPTION: sponsor case less 2pp", "assumption", "LABELED"),
    ("ASSUMPTION: anything", "historical", "FAIL"),
    ("ASSUMPTION", "assumption", "FAIL"),
    ("LEDGER: rev", "historical", "PASS"),
    ("LEDGER: ebitda", "historical", "FAIL"),
    ("PULLED: forward curve", "assumption", "PASS"),
    ("trust me", "historical", "FAIL"),
])
def test_classify_source(source, kind, result):
    assert analysis.classify_source(source, kind, {"D01"}, {"rev"}, True)[0] == result


def test_signals_flag_addbacks_and_ar():
    f = dict(pik_share_pct=60, revenue_prior=100, revenue_current=105, ar_prior=10, ar_current=14,
             reported_ebitda=14, adjusted_ebitda=20, cash=5, undrawn_revolver=5, maturities_24m=12,
             monthly_burn=1)
    sev = analysis.credit_signals(f, {}).set_index("signal")["severity"]
    assert sev["PIK reliance"] == "red"
    assert sev["Receivables vs revenue"] == "red"   # 40% vs 5%
    assert sev["Add-back aggressiveness"] == "red"  # 30%
    assert sev["Refinancing wall (24m)"] == "red"
    assert sev["Liquidity runway"] == "red"         # 10 months


def test_demo_and_blank_project_cleanly():
    for d in (demo.demo(), demo.blank()):
        v = dict(zip(d["inputs"]["key"], d["inputs"]["value"]))
        a = {r["key"]: [r[y] for y in demo.YEARS] for _, r in d["assumptions"].iterrows()}
        df = project(ModelInputs(**v, **a))
        assert len(df) == 5
