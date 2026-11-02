"""Rule-based 'case study' writer: turns the numbers (and optional annual-report text) into readable analysis."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .analytics import Metrics
from .utils import money, pct, mult, is_nan


def _chg_word(x, up="rose", down="fell", flat="was flat"):
    if is_nan(x) or abs(x) < 0.5:
        return flat
    return up if x > 0 else down


def _pp(x):
    return "n/a" if is_nan(x) else f"{x:+.1f} pp"


def build_case_study(m: Metrics, name: str, report: dict | None = None, proj_summary: dict | None = None) -> list[dict]:
    """Returns list of {title, body: [paragraphs], bullets: [..]} sections."""
    L, P = m.latest, m.prev
    lp, pp_ = m.latest_period, m.prev_period
    sections: list[dict] = []

    # 1. Business snapshot --------------------------------------------------
    body, bullets = [], []
    if report and report.get("overview"):
        body.append(report["overview"])
    else:
        body.append(
            f"{name} reported {money(L['Revenue'])} of revenue in {lp}"
            + (f", {'up' if L.get('Revenue Growth %', 0) > 0 else 'down'} {pct(abs(L.get('Revenue Growth %', np.nan)))} from {pp_}." if P is not None and not is_nan(L.get('Revenue Growth %')) else ".")
            + " Upload the annual report PDF to enrich this section with the company's own description of its business."
        )
    if report and report.get("facts"):
        bullets += [f"{k}: {v}" for k, v in report["facts"]]
    mc = L.get("Market Cap")
    if not is_nan(mc):
        bullets.append(f"Market capitalisation {money(mc)}; P/E {mult(L.get('P/E'))}, P/B {mult(L.get('P/B'))}, EV/EBITDA {mult(L.get('EV/EBITDA'))}")
    sections.append({"title": "Business snapshot", "body": body, "bullets": bullets})

    # 2. Year in review -----------------------------------------------------
    body, bullets = [], []
    if P is not None:
        rev_g, ebitda_g, pat_g = L.get("Revenue Growth %"), L.get("EBITDA Growth %"), L.get("PAT Growth %")
        mdelta = L.get("EBITDA Margin %") - P.get("EBITDA Margin %")
        nmdelta = L.get("Net Margin %") - P.get("Net Margin %")
        body.append(
            f"In {lp}, revenue {_chg_word(rev_g)} {pct(abs(rev_g)) if not is_nan(rev_g) else ''} to {money(L['Revenue'])}. "
            f"EBITDA {_chg_word(ebitda_g)} {pct(abs(ebitda_g)) if not is_nan(ebitda_g) else ''} to {money(L['EBITDA'])}, "
            f"with the margin moving {_pp(mdelta)} to {pct(L['EBITDA Margin %'])}. "
            f"Net profit {_chg_word(pat_g)} {pct(abs(pat_g)) if not is_nan(pat_g) else ''} to {money(L['PAT'])} "
            f"(net margin {pct(L['Net Margin %'])}, {_pp(nmdelta)})."
        )
        # what drove profit growth?
        if not is_nan(rev_g) and not is_nan(pat_g):
            if pat_g > rev_g + 2:
                body.append("Profit grew faster than sales, indicating operating leverage and/or lower finance and tax costs.")
            elif pat_g < rev_g - 2:
                body.append("Profit grew slower than sales, so cost pressure or higher interest/depreciation/tax diluted the benefit of growth.")
    else:
        body.append(f"Only one period of data is available ({lp}), so year-on-year comparisons are not possible.")
    bullets += [
        f"Revenue {money(L['Revenue'])} · EBITDA {money(L['EBITDA'])} · PAT {money(L['PAT'])}",
        f"EPS ₹{L.get('EPS', np.nan):.2f}" + (f" ({pct(L.get('EPS Growth %'), sign=True)} YoY)" if not is_nan(L.get("EPS Growth %")) else ""),
    ]
    sections.append({"title": f"{lp} in review", "body": body, "bullets": bullets})

    # 3. Growth trajectory --------------------------------------------------
    body, bullets = [], []
    c3, c5, c10 = m.cagr("Revenue", 3), m.cagr("Revenue", 5), m.cagr("Revenue", 9)
    p3, p5 = m.cagr("PAT", 3), m.cagr("PAT", 5)
    parts = []
    if not is_nan(c3):
        parts.append(f"3-year revenue CAGR of {pct(c3)}")
    if not is_nan(c5):
        parts.append(f"5-year CAGR of {pct(c5)}")
    if not is_nan(c10):
        parts.append(f"long-run CAGR of {pct(c10)}")
    if parts:
        body.append("Over time the company has delivered " + ", ".join(parts) + ".")
    if not is_nan(p3):
        body.append(f"Net profit compounded at {pct(p3)} over three years" + (f" and {pct(p5)} over five." if not is_nan(p5) else "."))
    g = m.df["Revenue Growth %"].dropna()
    if len(g) >= 3:
        worst = g.idxmin()
        body.append(f"Growth has been {'steady' if g.std() < 5 else 'uneven'} (range {pct(g.min())} to {pct(g.max())}); the weakest year was {worst}.")
    sections.append({"title": "Growth trajectory", "body": body or ["Not enough history for growth analysis."], "bullets": bullets})

    # 4. Profitability and costs -------------------------------------------
    body, bullets = [], []
    em = m.df["EBITDA Margin %"].dropna()
    if len(em) >= 3:
        trend = em.iloc[-1] - em.iloc[-4 if len(em) >= 4 else 0]
        body.append(f"EBITDA margin has ranged between {pct(em.min())} and {pct(em.max())}; it is "
                    f"{'up' if trend > 0.5 else 'down' if trend < -0.5 else 'broadly unchanged'} {_pp(trend)} versus three years ago.")
    cs = m.cost_structure()
    if len(cs):
        tot = float(L["Revenue"])
        top = cs.sort_values(ascending=False).head(3)
        body.append("The largest cost lines are " + ", ".join(f"{k.lower()} ({pct(v / tot * 100)} of sales)" for k, v in top.items()) + ".")
        if P is not None:
            csp = m.cost_structure(pp_)
            diffs = {k: cs[k] / L["Revenue"] * 100 - csp.get(k, np.nan) / P["Revenue"] * 100 for k in cs.index if k in csp.index}
            if diffs:
                k = max(diffs, key=lambda x: abs(diffs[x]))
                if abs(diffs[k]) >= 0.3:
                    body.append(f"The biggest shift in cost mix was {k.lower()}, {'higher' if diffs[k] > 0 else 'lower'} by {abs(diffs[k]):.1f} pp of sales.")
    bullets.append(f"Depreciation {pct(L['Depreciation'] / L['Revenue'] * 100)} · Interest {pct(L['Interest'] / L['Revenue'] * 100)} · Effective tax rate {pct(L.get('Tax Rate %'))} of PBT")
    sections.append({"title": "Profitability & cost structure", "body": body, "bullets": bullets})

    # 5. Returns ------------------------------------------------------------
    body, bullets = [], []
    body.append(f"Return on equity was {pct(L.get('ROE %'))} and ROCE {pct(L.get('ROCE %'))}"
                + (f" (previous year {pct(P.get('ROE %'))} / {pct(P.get('ROCE %'))})." if P is not None else "."))
    if P is not None and not any(is_nan(x) for x in (L.get("Net Margin %"), P.get("Net Margin %"), L.get("Asset Turnover"), P.get("Asset Turnover"), L.get("Equity Multiplier"), P.get("Equity Multiplier"))):
        d = {
            "profit margin": (L["Net Margin %"] - P["Net Margin %"]) / P["Net Margin %"] if P["Net Margin %"] else 0,
            "asset turnover": (L["Asset Turnover"] - P["Asset Turnover"]) / P["Asset Turnover"] if P["Asset Turnover"] else 0,
            "leverage": (L["Equity Multiplier"] - P["Equity Multiplier"]) / P["Equity Multiplier"] if P["Equity Multiplier"] else 0,
        }
        k = max(d, key=lambda x: abs(d[x]))
        body.append(f"DuPont analysis: the largest driver of the change in ROE was {k} ({d[k] * 100:+.1f}%).")
    bullets.append(f"DuPont — net margin {pct(L.get('Net Margin %'))} × asset turnover {mult(L.get('Asset Turnover'), 2)} × equity multiplier {mult(L.get('Equity Multiplier'), 2)}")
    sections.append({"title": "Returns on capital", "body": body, "bullets": bullets})

    # 6. Balance sheet ------------------------------------------------------
    body, bullets = [], []
    de = L.get("Debt / Equity")
    nd = L.get("Net Debt")
    lev = "virtually debt-free" if not is_nan(de) and de < 0.1 else "conservatively financed" if not is_nan(de) and de < 0.5 else \
        "moderately leveraged" if not is_nan(de) and de < 1 else "highly leveraged"
    body.append(f"The balance sheet is {lev}: borrowings of {money(L['Debt'])} against equity of {money(L['Equity'])} "
                f"(debt/equity {mult(de, 2)}). "
                + (f"The company holds net cash of {money(-nd)}." if not is_nan(nd) and nd < 0 else f"Net debt stands at {money(nd)} ({mult(L.get('Net Debt / EBITDA'))} EBITDA)." if not is_nan(nd) else ""))
    if not is_nan(L.get("Interest Coverage")):
        body.append(f"Interest cover is {mult(L['Interest Coverage'])}, " + ("a comfortable buffer." if L["Interest Coverage"] > 4 else "which leaves limited room for earnings shocks."))
    if not is_nan(L.get("Working Capital Days")):
        d_prev = P.get("Working Capital Days") if P is not None else np.nan
        body.append(f"Receivable days are {L.get('Receivable Days', np.nan):.0f} and inventory days {L.get('Inventory Days', np.nan):.0f}; "
                    f"net working capital is {pct(L.get('NWC % Sales'))} of sales"
                    + (f" ({'tighter' if L['Working Capital Days'] < d_prev else 'looser'} than last year)." if not is_nan(d_prev) else "."))
    sections.append({"title": "Balance sheet & liquidity", "body": body, "bullets": bullets})

    # 7. Cash flow & allocation --------------------------------------------
    body, bullets = [], []
    if not is_nan(L.get("CFO")):
        body.append(f"Operating cash flow was {money(L['CFO'])} ({mult(L.get('CFO / PAT'), 2)} of net profit). "
                    + ("Cash conversion is strong." if L.get("CFO / PAT", 0) >= 1 else "Cash conversion lags reported profit, worth checking working-capital build-up."))
        if not is_nan(L.get("Capex")):
            body.append(f"Estimated capex was {money(L['Capex'])} ({pct(L.get('Capex % Sales'))} of sales), leaving free cash flow of {money(L['FCF'])} (FCF margin {pct(L.get('FCF Margin %'))}).")
        tail = m.df.tail(5)
        if tail["CFO"].notna().any():
            body.append(f"Over the last {len(tail)} years the business generated {money(tail['CFO'].sum())} of operating cash flow and "
                        f"{money(tail['FCF'].sum())} of free cash flow, and paid {money(tail['Dividend'].sum())} in dividends.")
    if not is_nan(L.get("Dividend Payout %")):
        bullets.append(f"Dividend payout {pct(L['Dividend Payout %'])} of profit" + (f" · yield {pct(L.get('Dividend Yield %'))}" if not is_nan(L.get("Dividend Yield %")) else ""))
    if not is_nan(L.get("CFF")):
        bullets.append(f"Financing cash flow {money(L['CFF'])} — " + ("net repayment/returns to capital providers" if L["CFF"] < 0 else "net funds raised"))
    sections.append({"title": "Cash flow & capital allocation", "body": body or ["Cash flow data not available."], "bullets": bullets})

    # 8. Strengths & watch-outs ---------------------------------------------
    strengths, watch = [], []
    for c in m.scorecard():
        if c["pass"] is True:
            strengths.append(f"{c['check']} ({c['detail']})")
        elif c["pass"] is False:
            watch.append(f"{c['check']} — currently {c['detail']}")
    sections.append({"title": "Strengths and watch-outs", "body": [], "bullets": [], "strengths": strengths, "watch": watch})

    # 9. Management view from annual report ---------------------------------
    if report and report.get("themes"):
        sections.append({"title": "From the annual report", "body": [], "bullets": [], "themes": report["themes"]})

    # 10. Outlook -----------------------------------------------------------
    if proj_summary:
        sections.append({"title": "Model outlook (base case)", "body": [
            f"Under the default assumptions the model projects revenue of {money(proj_summary['revenue_end'])} and net profit of "
            f"{money(proj_summary['pat_end'])} by {proj_summary['end_label']}, a revenue CAGR of {pct(proj_summary['rev_cagr'])}. "
            + (f"The DCF cross-check implies about ₹{proj_summary['value_ps']:,.0f} per share versus a market price of ₹{proj_summary['price']:,.0f}." if proj_summary.get("value_ps") and proj_summary.get("price") else "")
        ], "bullets": ["Assumptions are mechanical extrapolations of history — edit them on the Financial Model page."]})

    # 11. Verdict -----------------------------------------------------------
    ok, tot = m.score()
    tone = "strong" if tot and ok / tot >= 0.75 else "mixed" if tot and ok / tot >= 0.5 else "weak"
    sections.append({"title": "Scorecard verdict", "body": [
        f"{name} passes {ok} of {tot} health checks — a {tone} financial profile on these tests. "
        "This is a mechanical read of the reported numbers, not investment advice."], "bullets": []})
    return sections


def to_markdown(sections: list[dict]) -> str:
    out = []
    for s in sections:
        out.append(f"## {s['title']}")
        out += s.get("body", [])
        out += [f"- {b}" for b in s.get("bullets", [])]
        if s.get("strengths"):
            out.append("**Strengths**")
            out += [f"- {b}" for b in s["strengths"]]
        if s.get("watch"):
            out.append("**Watch-outs**")
            out += [f"- {b}" for b in s["watch"]]
        for t, sents in (s.get("themes") or {}).items():
            out.append(f"**{t}**")
            out += [f"- {x}" for x in sents]
        out.append("")
    return "\n".join(out)
