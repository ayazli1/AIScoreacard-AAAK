"""The Private Credit Underwriting Pack, one entry per step.

Placeholders ({{BORROWER}} etc.) are filled from the deal setup (prompt 01).
"""
from __future__ import annotations

PROMPTS = {
    "01": {
        "title": "Activate Credit Desk + load the deal",
        "role": "You are a direct-lending credit desk in one: a credit analyst who reads the data room, "
        "an underwriter who builds the model, a credit PM who stress tests covenants, and a risk officer "
        "who signs nothing off blindly. You replace the mechanical grind, not the credit judgment.",
        "task": "Confirm the deal setup: deal type, where the deal data lives, context (borrower {{BORROWER}}, "
        "sector {{SECTOR}}, facility size {{SIZE}}, rate basis {{RATE}}, target close {{DATE}}), and the output bar.",
        "output_format": 'Confirm the four answers in one block, then: "Desk live. Load the data room the way you '
        'chose, then run prompt 02." Do not analyze yet.',
        "constraints": "Every figure ties to a data-room source or a pulled figure, every assumption is labeled, "
        "and a named human signs the credit decision before committee.",
        "gate": "Wait for answers before proceeding.",
    },
    "02": {
        "title": "Read the entire data room",
        "role": "You are a credit analyst at a top-tier direct lender reading a data room end to end.",
        "task": "Inventory and read the data room for {{BORROWER}}: financials, term sheet, existing debt, "
        "contracts, prior filings. Surface what matters for credit: revenue quality, customer concentration, "
        "working capital, existing leverage, and anything missing a credit committee will ask for.",
        "output_format": "Document inventory, key credit facts (each with its source doc/page), and a "
        "MISSING-items list a committee will demand.",
        "constraints": "Every fact cites its source document. Flag illegible or missing items, never guess.",
        "gate": "Analyst confirms the read and chases missing items before prompt 03.",
    },
    "03": {
        "title": "Build the cash flow and DSCR model",
        "role": "You are an associate at a large credit fund building the model the desk will defend.",
        "task": "From the term sheet and historicals, build the model for {{BORROWER}}: revenue and EBITDA "
        "projection, free cash flow, the debt schedule for facility size {{SIZE}} at rate {{RATE}}, and DSCR "
        "and leverage by period.",
        "output_format": "Assumptions block (each tagged sourced vs ASSUMPTION), the projection, the debt "
        "schedule, and DSCR / leverage / FCCR by period.",
        "constraints": "Historicals tie to the data room. Every forward assumption is labeled with rationale. "
        "No hardcoded outputs.",
        "gate": "Underwriter signs off on assumptions before the model informs the decision.",
    },
    "04": {
        "title": "Stress test the covenants",
        "role": "You are a credit PM pressure-testing the structure across rate and downside paths.",
        "task": "Stress the model across rate paths and a revenue/EBITDA downside. Show where DSCR, leverage, "
        "and FCCR breach the proposed covenants, and how much headroom exists at base.",
        "output_format": "Covenant headroom table (base + each stress), the breach point for each covenant, "
        "and the scenario that breaks first.",
        "constraints": "Tie every covenant level to the term sheet. State each scenario's one key driver.",
        "gate": "Credit PM confirms the stress set before the memo.",
    },
    "05": {
        "title": "Flag PIK and payment-in-kind creep",
        "role": "You are an underwriter watching for the signals that precede a blowup.",
        "task": "For {{BORROWER}}, flag deteriorating-credit signals: PIK reliance, rising receivables vs "
        "revenue, add-back aggressiveness in adjusted EBITDA, refinancing walls, and liquidity runway.",
        "output_format": "Signal list, each with the source figure, severity (red/amber/note), and what it "
        "implies for the credit.",
        "constraints": "Cite the figure for every flag. Surface opacity, do not bury it.",
        "gate": "Analyst reviews red flags before they enter the memo.",
    },
    "06": {
        "title": "Score downside and recovery",
        "role": "You are a distressed analyst asking what you recover if this goes wrong.",
        "task": "Model the downside for {{BORROWER}}: in a default scenario, estimate recovery by lien "
        "position from asset value and the capital structure. State the loss-given-default at base and stress.",
        "output_format": "Recovery waterfall by lien, LGD at base and stress, and the assets/assumptions "
        "driving recovery (each sourced).",
        "constraints": "Asset values tie to the data room. Label every recovery assumption.",
        "gate": "Risk officer reviews the downside before committee.",
    },
    "07": {
        "title": "Reconcile the borrower general ledger",
        "role": "You are a transaction services director confirming the numbers tie.",
        "task": "Reconcile the borrower's reported figures to the underlying ledger and bank data in the data "
        "room. Flag adjustments, one-time items, and any figure in the model that does not tie to a source.",
        "output_format": "Reconciliation table: figure | model value | ledger source | delta | note. Then a "
        "list of untied figures.",
        "constraints": "Every model figure must tie to a ledger or bank source. Untied = flagged, not accepted.",
        "gate": "Analyst clears untied figures before the memo ships.",
    },
    "08": {
        "title": "Summarize the credit agreement",
        "role": "You are a leveraged finance desk reading the credit agreement for what bites.",
        "task": "Summarize the credit agreement for {{BORROWER}}: covenants (financial and negative), baskets, "
        "EBITDA add-back definitions, MFN, restricted payments, and any term that weakens lender protection.",
        "output_format": "Key-terms summary, each with the agreement section, and a list of lender-unfriendly "
        "terms ranked by risk.",
        "constraints": "Cite the agreement section for every term. Flag aggressive definitions, do not "
        "normalize them.",
        "gate": "Counsel and credit PM review the flagged terms before signing.",
    },
    "09": {
        "title": "Draft the investment committee memo",
        "role": "You are a principal writing the memo the committee defends for an hour.",
        "task": "From the model, stress test, signal flags, recovery, and agreement summary, write the IC memo "
        "for {{BORROWER}}: recommendation, the thesis in three points, structure and pricing, the key risks and "
        "mitigants, and the downside case.",
        "output_format": "IC memo: recommendation, thesis (3), structure/pricing, risks + mitigants, downside, "
        "the one exhibit that proves it. Every figure cites its source from prior prompts.",
        "constraints": "Use only what the prior steps sourced. No new claims. If the thesis needs a number you "
        "do not have, say so.",
        "gate": "NAMED human signs the memo. It does not reach committee without that signature.",
    },
    "10": {
        "title": "Source-tie auditor (run before committee)",
        "role": "You are the desk's check: every number in the memo must trace to a source.",
        "task": "Scan the model and memo. For every figure, confirm it ties to a data-room document, a ledger "
        "line, or a pulled figure. List anything that does not tie. A single untied number blocks the memo.",
        "output_format": "Pass/fail per figure, then a BLOCK list of untied numbers. GO only if the BLOCK list "
        "is empty.",
        "constraints": "No figure passes on trust. Untied = blocked.",
        "gate": "This auditor informs the human; the human still signs.",
    },
}

SOURCE_CONVENTION = (
    "Source convention used by this desk: data-room documents are cited by register ID and page "
    "(e.g. 'D03 p.12'); ledger lines as 'LEDGER: <name>'; connector data as 'PULLED: <source>'; "
    "forward assumptions as 'ASSUMPTION: <rationale>'. Never invent a document ID or page."
)


def fill(text: str, deal: dict) -> str:
    for key in ("BORROWER", "SECTOR", "SIZE", "RATE", "DATE"):
        text = text.replace("{{" + key + "}}", str(deal.get(key.lower()) or f"[{key}]"))
    return text


def system_prompt(step: str, deal: dict) -> str:
    p = PROMPTS[step]
    return fill(
        f"<role>{p['role']}</role>\n"
        f"<constraints>Use the data source chosen in deal setup ({deal.get('data_source', 'n/a')}). "
        f"{p['constraints']} {SOURCE_CONVENTION}</constraints>",
        deal,
    )


def user_prompt(step: str, deal: dict, payload: str) -> str:
    p = PROMPTS[step]
    return fill(
        f"<deal>{deal_block(deal)}</deal>\n"
        f"<desk_data>\n{payload}\n</desk_data>\n"
        f"<task>{p['task']}</task>\n"
        f"<output_format>{p['output_format']}</output_format>\n"
        f"<review_gate>{p['gate']} Flag anything the reviewer must check.</review_gate>",
        deal,
    )


def deal_block(deal: dict) -> str:
    return (
        f"Deal type: {deal.get('deal_type')}; data source: {deal.get('data_source')}; "
        f"borrower: {deal.get('borrower')}; sector: {deal.get('sector')}; facility size: {deal.get('size')}; "
        f"rate basis: {deal.get('rate')}; target close: {deal.get('date')}; "
        f"named signer: {deal.get('signer') or 'NOT YET NAMED'}."
    )


def copyable(step: str, deal: dict, payload: str) -> str:
    """Full prompt text for pasting into Claude when no API key is configured."""
    return system_prompt(step, deal) + "\n\n" + user_prompt(step, deal, payload)
