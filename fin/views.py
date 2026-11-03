"""Page renderers. Each takes a context dict `X` with keys: co, m, T, name."""
from __future__ import annotations

import html
import re

import numpy as np
import pandas as pd
import streamlit as st

from . import charts as C
from . import export as EX
from . import model as MD
from . import pdf_tools as PT
from .narrative import build_case_study, to_markdown
from .ui import PLOT_CFG, card, card_title, check_rows, html_table, kpi_head, list_rows, pill
from .utils import CURRENCY, is_nan, money, mult, num, pct

_k = iter(range(10**9))


def plot(fig, key=None):
    st.plotly_chart(fig, width="stretch", config=PLOT_CFG, theme=None, key=key or f"pc{next(_k)}")


def chips(items: list[tuple[str, str]], cls="") -> str:
    return "".join(f"<span class='chip {cls}'><span style='color:var(--muted)'>{html.escape(k)}</span> &nbsp;<b style='color:var(--text)'>{html.escape(v)}</b></span>" for k, v in items)


def safe(x, fmt="{:.1f}"):
    return "–" if is_nan(x) else fmt.format(x)


def health_scores(m) -> dict:
    L = m.latest
    c3 = m.cagr("Revenue", 3) if len(m.df) > 3 else np.nan

    def sc(v, lo, hi, invert=False):
        if is_nan(v):
            return 0
        x = (v - lo) / (hi - lo)
        x = 1 - x if invert else x
        return float(np.clip(x, 0, 1) * 100)
    return {
        "Growth": sc(c3 if not is_nan(c3) else L.get("Revenue Growth %"), 0, 20),
        "Profitability": sc(L.get("Net Margin %"), 0, 20),
        "Returns": sc(L.get("ROCE %"), 5, 30),
        "Safety": sc(L.get("Debt / Equity"), 0, 2, invert=True),
        "Cash quality": sc(L.get("CFO / PAT"), 0.3, 1.3),
        "Efficiency": sc(L.get("Asset Turnover"), 0.3, 1.6),
    }


# =============================================================================
def overview(X):
    co, m, T = X["co"], X["m"], X["T"]
    L, P = m.latest, m.prev
    d = m.df
    per = m.latest_period
    cols = st.columns(4, gap="medium")
    specs = [("Revenue", "Revenue", True, "Revenue Growth %"), ("EBITDA", "EBITDA", True, "EBITDA Growth %"),
             ("Net profit (to owners)", "PAT", True, "PAT Growth %"), ("Free cash flow", "FCF", True, None)]
    for c, (lab, col, up, gcol) in zip(cols, specs):
        with c:
            with card("kpi"):
                dv = L.get(gcol) if gcol else m.delta(col)
                kpi_head(lab, money(L.get(col), unit=False) + f" <span style='font-size:14px;color:var(--muted);font-weight:500'>{CURRENCY['unit']}</span>",
                         pill(dv, good_up=up), f"vs {m.prev_period}" if P is not None else "")
                s = d[col].dropna().tail(10)
                if len(s) >= 2:
                    plot(C.sparkline(s.values, T, up=s.iloc[-1] >= s.iloc[0]))

    r2 = st.columns([1.05, 1.35, 1.0], gap="medium")
    with r2[0]:
        with card("val"):
            card_title("Valuation snapshot", f"at current price" if not is_nan(L.get("Price")) else "price not provided")
            mc = L.get("Market Cap")
            st.markdown(f"<div class='hero'>{money(mc, unit=False) if not is_nan(mc) else '–'} <span style='font-size:14px;color:var(--muted)'>{CURRENCY['unit']}</span></div>"
                        f"<div class='card-sub'>Market capitalisation</div>", unsafe_allow_html=True)
            st.markdown(chips([("P/E", mult(L.get("P/E"))), ("P/B", mult(L.get("P/B"))), ("EV/EBITDA", mult(L.get("EV/EBITDA"))),
                               ("Div. yield", pct(L.get("Dividend Yield %"))), ("EPS", f"₹{safe(L.get('EPS'), '{:.2f}')}")]), unsafe_allow_html=True)
            ok, tot = m.score()
            st.markdown(f"<div style='margin-top:14px'><span class='chip {'good' if ok / max(tot, 1) >= .7 else 'bad' if ok / max(tot, 1) < .5 else ''}'>Health score <b style='color:var(--text)'>{ok}/{tot}</b></span></div>", unsafe_allow_html=True)
    with r2[1]:
        with card("tiles"):
            card_title("Key ratios", f"{per}")
            tiles = [("ROE", pct(L.get("ROE %")), "◎"), ("ROCE", pct(L.get("ROCE %")), "◉"), ("EBITDA margin", pct(L.get("EBITDA Margin %")), "▤"),
                     ("Net margin", pct(L.get("Net Margin %")), "▦"), ("Debt / equity", mult(L.get("Debt / Equity"), 2), "⚖"),
                     ("Interest cover", mult(L.get("Interest Coverage")), "⛨"), ("CFO / PAT", mult(L.get("CFO / PAT"), 2), "⇄"),
                     ("Payout", pct(L.get("Dividend Payout %")), "₹")]
            grid = "".join(f"<div style='text-align:center;padding:8px 2px'><div class='row-ic' style='margin:0 auto 6px;width:44px;height:44px;font-size:17px;color:var(--accent)'>{ic}</div>"
                           f"<div style='font-size:11px;color:var(--muted)'>{lab}</div><div style='font-weight:600;font-size:14px'>{v}</div></div>" for lab, v, ic in tiles)
            st.markdown(f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:4px'>{grid}</div>", unsafe_allow_html=True)
    with r2[2]:
        with card("bal"):
            nd = L.get("Net Debt")
            card_title("Balance sheet strength")
            lab = "Net cash" if not is_nan(nd) and nd < 0 else "Net debt"
            st.markdown(f"<div class='hero'>{money(abs(nd), unit=False) if not is_nan(nd) else '–'} <span style='font-size:14px;color:var(--muted)'>{CURRENCY['unit']}</span></div>"
                        f"<div class='card-sub'>{lab} · borrowings {money(L.get('Debt'))} · cash {money(L.get('Cash'))}</div>", unsafe_allow_html=True)
            de = L.get("Debt / Equity")
            st.markdown(chips([("Debt/Equity", mult(de, 2)), ("Net debt/EBITDA", mult(L.get("Net Debt / EBITDA"))), ("Equity", money(L.get("Equity")))]), unsafe_allow_html=True)

    r3 = st.columns([2.1, 1], gap="medium")
    with r3[0]:
        with card("cf"):
            h1, h2 = st.columns([3, 1])
            with h1:
                card_title("Cash flow", "operating vs free cash flow")
                fcf = L.get("FCF")
                st.markdown(f"<div class='hero'>{money(fcf, unit=False) if not is_nan(fcf) else '–'} <span style='font-size:14px;color:var(--muted)'>{CURRENCY['unit']} free cash flow, {per}</span></div>", unsafe_allow_html=True)
            with h2:
                st.markdown(f"<div style='text-align:right;padding-top:8px'>{pill(m.delta('FCF'))}</div>", unsafe_allow_html=True)
            if d["CFO"].notna().sum() >= 2:
                plot(C.cashflow_chart(d.tail(10), T))
            else:
                st.info("Cash flow data not available in the uploaded file.")
    with r3[1]:
        with card("act"):
            card_title("What changed", f"{per} vs {m.prev_period}" if P is not None else per)
            if P is not None:
                items = [("▲", "Revenue", L["Revenue Growth %"], money(L["Revenue"]), True), ("◧", "EBITDA", L.get("EBITDA Growth %"), money(L["EBITDA"]), True),
                         ("₹", "Net profit", L.get("PAT Growth %"), money(L["PAT"]), True), ("◎", "EPS", L.get("EPS Growth %"), f"₹{safe(L.get('EPS'), '{:.2f}')}", True),
                         ("⛨", "Debt", m.delta("Debt"), money(L.get("Debt")), False), ("▣", "Cash", m.delta("Cash"), money(L.get("Cash")), True)]
                rows = [(ic, t, "year-on-year", f"{v}<br>{pill(g, good_up=gu, decimals=1)}") for ic, t, g, v, gu in items]
                st.markdown(list_rows(rows), unsafe_allow_html=True)
            else:
                st.caption("Needs at least two periods.")

    r4 = st.columns([1.7, 1, 1], gap="medium")
    with r4[0]:
        with card("rp"):
            plot(C.bars_with_line(d.tail(10), ["Revenue", "PAT"], "EBITDA Margin %", T, title="Revenue, net profit and EBITDA margin", line_name="EBITDA margin"))
    with r4[1]:
        with card("cs"):
            cs = m.cost_structure()
            if len(cs):
                top = cs.sort_values(ascending=False)
                if len(top) > 5:
                    top = pd.concat([top.head(5), pd.Series({"Others": top.iloc[5:].sum()})])
                plot(C.donut(list(top.index), list(top.values), T, title="Cost structure", center=f"{pct(L['Cost % Sales'], 0)}<br><span style='font-size:10px;color:{T['muted']}'>of sales</span>"))
            else:
                st.caption("Cost breakdown not available.")
    with r4[2]:
        with card("am"):
            comp = {"Net block": L.get("Net Block"), "CWIP": L.get("CWIP"), "Investments": L.get("Investments"), "Receivables": L.get("Receivables"),
                    "Inventory": L.get("Inventory"), "Cash": L.get("Cash"), "Other": L.get("Other Current/Misc Assets")}
            comp = {k: v for k, v in comp.items() if not is_nan(v) and v > 0}
            if comp:
                plot(C.donut(list(comp), list(comp.values()), T, title="Asset mix", center=f"{money(L.get('Total Assets'), unit=False)}<br><span style='font-size:10px;color:{T['muted']}'>total assets</span>"))
            else:
                st.caption("Balance sheet not available.")

    r5 = st.columns([1, 1], gap="medium")
    with r5[0]:
        with card("sc"):
            ok, tot = m.score()
            card_title("Financial health scorecard", f"{ok} of {tot} checks pass")
            st.markdown(check_rows(m.scorecard()), unsafe_allow_html=True)
    with r5[1]:
        with card("rd"):
            card_title("Business profile", "0–100 score per dimension (mechanical scale)")
            plot(C.radar(health_scores(m), T))


# =============================================================================
def performance(X):
    co, m, T = X["co"], X["m"], X["T"]
    d, L = m.df, m.latest
    t1, t2, t3 = st.tabs(["Income statement", "Balance sheet", "Cash flow"])
    n = st.session_state.get("years_shown", 10)
    with t1:
        c = st.columns([1.6, 1], gap="medium")
        with c[0]:
            with card("p1"):
                plot(C.bars_with_line(d.tail(n), ["Revenue", "EBITDA", "PAT"], "EBITDA Margin %", T, title="Revenue, EBITDA, net profit", line_name="EBITDA margin", height=380))
        with c[1]:
            with card("p2"):
                if not is_nan(L.get("EBITDA")):
                    items = [("Revenue", L["Revenue"], "absolute"), ("Op. costs", -L["Operating Expenses"], "relative"), ("EBITDA", 0, "total"),
                             ("Other inc.", L["Other Income"], "relative"), ("Deprn.", -L["Depreciation"], "relative"), ("Interest", -L["Interest"], "relative"),
                             ("Tax", -(L["Tax"] if not is_nan(L["Tax"]) else 0), "relative")]
                    mo = L.get("Minority & others")
                    if not is_nan(mo) and abs(mo) > 0.005 * abs(L["Revenue"]):
                        items += [("Minority", -mo, "relative")]
                    items += [("PAT", 0, "total")]
                    plot(C.waterfall(items, T, title=f"{m.latest_period}: from revenue to profit", height=380))
        c = st.columns(2, gap="medium")
        with c[0]:
            with card("p3"):
                plot(C.area_line(d.tail(n), ["Revenue Growth %", "EBITDA Growth %", "PAT Growth %"], T, title="Year-on-year growth (%)", fill_first=False))
        with c[1]:
            with card("p4"):
                exp_cols = [k for k in ["Raw Material Cost", "Employee Cost", "Power and Fuel", "Other Mfr. Exp", "Selling and admin", "Other Expenses"] if d[k].notna().any()]
                if exp_cols:
                    tmp = d.tail(n).copy()
                    for k in exp_cols:
                        tmp[k] = tmp[k] / tmp["Revenue"] * 100
                    plot(C.stacked(tmp, exp_cols, T, title="Expenses as % of sales", percent=False))
        with card("p5"):
            card_title("Income statement", f"{CURRENCY['symbol']} {CURRENCY['unit']}")
            pl_t = co.pl.iloc[:, -n:].copy()
            rec = m.df.reindex(pl_t.columns)
            if "PAT (total)" in rec and rec["Minority & others"].abs().max() > 0.005 * max(abs(rec["PAT (total)"]).max(), 1) and "Net profit" in pl_t.index:
                at = pl_t.index.get_loc("Net profit")
                extra = pd.DataFrame({"Profit after tax (PBT - Tax)": rec["PAT (total)"],
                                      "Less: minority, associates & others (derived)": -rec["Minority & others"]}).T
                pl_t = pd.concat([pl_t.iloc[:at], extra, pl_t.iloc[at:]])
                pl_t = pl_t.rename(index={"Net profit": "Net profit (attributable to owners)"})
            st.markdown(html_table(pl_t), unsafe_allow_html=True)
            st.caption("Net profit is the Screener Data Sheet figure after minority interest, so it matches EPS. "
                       "Screener's web page shows profit before minority (PBT - Tax); the reconciliation rows bridge the two.")
    with t2:
        c = st.columns(2, gap="medium")
        with c[0]:
            with card("b1"):
                cols = [k for k in ["Net Block", "CWIP", "Investments", "Receivables", "Inventory", "Cash", "Other Current/Misc Assets"] if d[k].notna().any()]
                plot(C.stacked(d.tail(n), cols, T, title="Where the money is invested (assets)"))
        with c[1]:
            with card("b2"):
                tmp = d.tail(n).copy()
                tmp["Equity "] = tmp["Equity"]
                plot(C.stacked(tmp, ["Equity ", "Debt", "Other Liabilities"], T, title="How it is funded (liabilities)"))
        c = st.columns(2, gap="medium")
        with c[0]:
            with card("b3"):
                plot(C.area_line(d.tail(n), ["Receivable Days", "Inventory Days", "Other Liab. Days"], T, title="Working-capital days", suffix=" d", fill_first=False))
        with c[1]:
            with card("b4"):
                plot(C.area_line(d.tail(n), ["Debt / Equity", "Net Debt / EBITDA"], T, title="Leverage (x)", suffix="x", fill_first=False))
        with card("b5"):
            card_title("Balance sheet", f"{CURRENCY['symbol']} {CURRENCY['unit']}")
            st.markdown(html_table(co.bs.iloc[:, -n:]), unsafe_allow_html=True)
    with t3:
        c = st.columns([1.6, 1], gap="medium")
        with c[0]:
            with card("c1"):
                import plotly.graph_objects as go
                dd = d.tail(n)
                fig = go.Figure()
                for i, (k, nm) in enumerate([("CFO", "Operating"), ("CFI", "Investing"), ("CFF", "Financing")]):
                    fig.add_trace(go.Bar(x=dd.index, y=dd[k], name=nm, marker=dict(color=T["cat"][[0, 2, 3][i]], cornerradius=4), hovertemplate=f"{nm}: %{{y:,.0f}}<extra></extra>"))
                fig.add_trace(go.Scatter(x=dd.index, y=dd["FCF"], name="Free cash flow", mode="lines+markers", line=dict(color=T["lime"], width=2.4), marker=dict(size=7)))
                C._base(fig, T, height=380, title="Cash flow by activity")
                fig.update_layout(barmode="group")
                plot(fig)
        with c[1]:
            with card("c2"):
                tail = d.tail(5)
                capex, dv = tail["Capex"].sum(), tail["Dividend"].sum()
                rest = tail["CFO"].sum() - capex - dv
                vals = {"Capex": capex, "Dividends": dv, "Retained / debt paydown": max(rest, 0)}
                vals = {k: v for k, v in vals.items() if not is_nan(v) and v > 0}
                if vals:
                    plot(C.donut(list(vals), list(vals.values()), T, title="Where 5-yr operating cash went", height=380, center=f"{money(tail['CFO'].sum(), unit=False)}<br><span style='font-size:10px;color:{T['muted']}'>5-yr CFO</span>"))
        c = st.columns(2, gap="medium")
        with c[0]:
            with card("c3"):
                plot(C.area_line(d.tail(n), ["CFO / PAT", "CFO / EBITDA"], T, title="Cash conversion (x)", suffix="x", fill_first=False))
        with c[1]:
            with card("c4"):
                plot(C.area_line(d.tail(n), ["FCF Margin %", "Capex % Sales"], T, title="FCF margin and capex intensity (%)", fill_first=False))
        with card("c5"):
            card_title("Cash flow statement", f"{CURRENCY['symbol']} {CURRENCY['unit']}")
            if co.cf.empty:
                st.caption("No cash flow data.")
            else:
                st.markdown(html_table(co.cf.iloc[:, -n:]), unsafe_allow_html=True)


# =============================================================================
RATIO_GROUPS = {
    "Profitability": ["EBITDA Margin %", "EBIT Margin %", "PBT Margin %", "Net Margin %", "Tax Rate %"],
    "Returns": ["ROE %", "ROCE %", "ROA %", "ROIC %"],
    "Leverage & liquidity": ["Debt / Equity", "Net Debt / EBITDA", "Interest Coverage", "Liabilities / Assets %", "Equity Multiplier"],
    "Efficiency": ["Asset Turnover", "Receivable Days", "Inventory Days", "Working Capital Days", "NWC % Sales"],
    "Cash flow": ["CFO / PAT", "CFO / EBITDA", "FCF Margin %", "Capex % Sales", "Dividend Payout %"],
    "Valuation": ["P/E", "P/B", "EV/EBITDA", "Earnings Yield %", "Dividend Yield %", "Price/Sales"],
    "Per share": ["EPS", "BVPS", "DPS"],
    "Growth": ["Revenue Growth %", "EBITDA Growth %", "PAT Growth %", "EPS Growth %"],
}


def ratios(X):
    co, m, T = X["co"], X["m"], X["T"]
    d, L = m.df, m.latest
    g = st.columns(4, gap="medium")
    gauges = [("ROE", L.get("ROE %"), 0, 40, "%"), ("ROCE", L.get("ROCE %"), 0, 40, "%"), ("Debt / equity", L.get("Debt / Equity"), 0, 2, "x"), ("Interest cover", L.get("Interest Coverage"), 0, 30, "x")]
    for c, (t, v, lo, hi, s) in zip(g, gauges):
        with c:
            with card("g"):
                plot(C.gauge(v, lo, hi, T, t, suffix=s))
    r = st.columns([1.15, 1], gap="medium")
    with r[0]:
        with card("dp"):
            card_title("DuPont decomposition", f"ROE = net margin × asset turnover × equity multiplier · {m.latest_period}")
            if not any(is_nan(L.get(k)) for k in ("ROE %", "Net Margin %", "Asset Turnover", "Equity Multiplier")):
                plot(C.dupont_tree(L, T))
            else:
                st.caption("Needs profit and balance sheet data.")
    with r[1]:
        with card("dpt"):
            plot(C.area_line(d.tail(10), ["ROE %", "ROCE %", "Net Margin %"], T, title="Return and margin trend (%)", fill_first=False, height=250))

    tabs = st.tabs(list(RATIO_GROUPS))
    for tab, (grp, cols) in zip(tabs, RATIO_GROUPS.items()):
        with tab:
            cols = [c for c in cols if c in d.columns and d[c].notna().any()]
            if not cols:
                st.caption("Not enough data for this group.")
                continue
            c = st.columns([1.3, 1], gap="medium")
            with c[0]:
                with card("rt"):
                    suffix = "%" if all("%" in x for x in cols) else ("x" if all(any(t in x for t in ("/", "Coverage", "Turnover", "Multiplier", "P/", "EV")) for x in cols) else "")
                    plot(C.area_line(d.tail(10), cols, T, title=grp, suffix=suffix, fill_first=False))
            with c[1]:
                with card("rtab"):
                    card_title("Latest vs previous")
                    rows = []
                    for k in cols:
                        a, b = L.get(k), (m.prev.get(k) if m.prev is not None else np.nan)
                        diff = a - b if not (is_nan(a) or is_nan(b)) else np.nan
                        rows.append((k, safe(a, "{:,.2f}"), safe(b, "{:,.2f}"), "–" if is_nan(diff) else f"{diff:+.2f}"))
                    head = "<tr><th></th><th>Latest</th><th>Prev</th><th>Δ</th></tr>"
                    body = "".join(f"<tr><td>{html.escape(a)}</td><td>{b}</td><td>{c_}</td><td class='{'neg' if d_.startswith('-') else ''}'>{d_}</td></tr>" for a, b, c_, d_ in rows)
                    st.markdown(f"<div class='tbl-wrap'><table class='fin'><thead>{head}</thead><tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
            with card("rfull"):
                st.markdown(html_table(d[cols].tail(10).T), unsafe_allow_html=True)

    with card("expl"):
        card_title("Metric explorer", "pick any computed metric to chart")
        allm = [c for c in d.columns if d[c].notna().sum() >= 2]
        sel = st.multiselect("Metrics", allm, default=["Revenue", "PAT"], key="explorer_sel", label_visibility="collapsed")
        if sel:
            kind = st.radio("Chart", ["Line", "Bar"], horizontal=True, key="explorer_kind", label_visibility="collapsed")
            import plotly.graph_objects as go
            fig = go.Figure()
            for i, k in enumerate(sel):
                if kind == "Bar":
                    fig.add_trace(go.Bar(x=d.index, y=d[k], name=k, marker=dict(color=T["cat"][i % 6], cornerradius=4)))
                else:
                    fig.add_trace(go.Scatter(x=d.index, y=d[k], name=k, mode="lines+markers", line=dict(color=T["cat"][i % 6], width=2.4)))
            plot(C._base(fig, T, height=330))
            if len(sel) > 1:
                st.caption("Metrics with very different scales share one axis here — pick comparable metrics, or use one at a time.")


# =============================================================================
def case_study(X):
    co, m, T = X["co"], X["m"], X["T"]
    report = X.get("report")
    ps = X.get("proj_summary")
    L = m.latest
    with card("hero"):
        c = st.columns([2.2, 1])
        with c[0]:
            st.markdown(f"<div class='crumb'>Case study · {m.latest_period}</div><div class='page-title'>{html.escape(co.name)}</div>", unsafe_allow_html=True)
            st.markdown(chips([("Revenue", money(L["Revenue"])), ("EBITDA", money(L["EBITDA"])), ("PAT", money(L["PAT"])), ("ROCE", pct(L.get("ROCE %"))),
                               ("D/E", mult(L.get("Debt / Equity"), 2))]), unsafe_allow_html=True)
        with c[1]:
            ok, tot = m.score()
            st.markdown(f"<div style='text-align:right'><div class='card-sub'>Health score</div><div class='hero'>{ok}<span style='color:var(--muted);font-size:20px'>/{tot}</span></div></div>", unsafe_allow_html=True)
    secs = build_case_study(m, co.name, report, ps)
    left, right = st.columns(2, gap="medium")
    for i, s in enumerate(secs):
        with (left if i % 2 == 0 else right):
            with card("narr"):
                inner = f"<div class='narr'><h4>{html.escape(s['title'])}</h4>"
                for p in s.get("body", []):
                    inner += f"<p>{html.escape(p)}</p>"
                if s.get("bullets"):
                    inner += "<ul>" + "".join(f"<li>{html.escape(b)}</li>" for b in s["bullets"]) + "</ul>"
                if s.get("strengths"):
                    inner += "<p><b>Strengths</b></p><ul>" + "".join(f"<li>{html.escape(b)}</li>" for b in s["strengths"]) + "</ul>"
                if s.get("watch"):
                    inner += "<p><b>Watch-outs</b></p><ul>" + "".join(f"<li>{html.escape(b)}</li>" for b in s["watch"]) + "</ul>"
                for th, sents in (s.get("themes") or {}).items():
                    inner += f"<p><b>{html.escape(th)}</b></p>" + "".join(f"<div class='quote'>{html.escape(x)}</div>" for x in sents[:2])
                st.markdown(inner + "</div>", unsafe_allow_html=True)
    st.download_button("Download case study (Markdown)", to_markdown(secs).encode("utf-8"), file_name=f"{co.name}_case_study.md", mime="text/markdown")


# =============================================================================
def annual_report(X):
    co, T = X["co"], X["T"]
    rep = X.get("report")
    if not rep:
        with card("nr"):
            st.markdown("### No annual report loaded for this company")
            st.write("Upload the annual report PDF in **Data Hub**. The dashboard will locate the Chairman's message, MD&A, risk and governance sections, "
                      "summarise them, mine key facts, and extract the financial statements for you to review.")
            if st.button("Go to Data Hub", type="primary"):
                st.session_state.page = "Data Hub"
                st.rerun()
        return
    pages = rep["pages"]
    secs = rep["sections"]
    c = st.columns(4, gap="medium")
    for col, (lab, val) in zip(c, [("Pages read", f"{len(pages):,}"), ("Sections found", f"{len(secs)}"), ("Key facts mined", f"{len(rep['facts'])}"), ("Words", f"{sum(len(p.split()) for p in pages):,}")]):
        with col:
            with card("rk"):
                st.markdown(f"<div class='card-sub'>{lab}</div><div class='kpi-value'>{val}</div>", unsafe_allow_html=True)
    if rep["facts"]:
        with card("rf"):
            card_title("Key facts found in the report", "regex-mined; verify against the source")
            st.markdown(chips(rep["facts"]), unsafe_allow_html=True)
    l, r = st.columns([1, 2], gap="medium")
    with l:
        with card("rs"):
            card_title("Sections detected")
            if secs:
                choice = st.radio("Section", list(secs), label_visibility="collapsed", key="rep_section_choice",
                                  format_func=lambda k: f"{k}  ·  p.{secs[k]['start']}" + (f"–{secs[k]['end']}" if secs[k]['end'] > secs[k]['start'] else ""))
            else:
                choice = None
                st.caption("No standard headings detected (scanned PDF?).")
    with r:
        with card("rv"):
            if choice:
                s = secs[choice]
                card_title(choice, f"pages {s['start']}–{s['end']}")
                summ = PT.summarise(s["text"], 5)
                st.markdown("**Summary (extractive)**")
                for x in summ:
                    st.markdown(f"<div class='quote'>{html.escape(x)}</div>", unsafe_allow_html=True)
                with st.expander("Read full section text"):
                    st.text(s["text"][:12000])
            else:
                st.caption("Select a section on the left.")
    if rep["themes"]:
        with card("rth"):
            card_title("Themes across the report", "sentences ranked by numbers and relevance")
            tabs = st.tabs(list(rep["themes"]))
            for t, (name, sents) in zip(tabs, rep["themes"].items()):
                with t:
                    for x in sents:
                        st.markdown(f"<div class='quote'>{html.escape(x)}</div>", unsafe_allow_html=True)
    with card("rq"):
        card_title("Search the report")
        q = st.text_input("Search", placeholder="e.g. dividend, capacity, litigation, ESG", label_visibility="collapsed", key="rep_search")
        if q and len(q) >= 3:
            rx = re.compile(re.escape(q), re.I)
            hits = []
            for i, p in enumerate(pages):
                for s in PT.split_sentences(p):
                    if rx.search(s):
                        hits.append((i + 1, s))
            st.caption(f"{len(hits)} matching sentences")
            for pg, s in hits[:25]:
                st.markdown(f"<div class='quote'><span style='color:var(--muted)'>p.{pg}</span> &nbsp;{rx.sub(lambda mm: f'<mark>{mm.group(0)}</mark>', html.escape(s))}</div>", unsafe_allow_html=True)


# =============================================================================
def model_page(X):
    co, m, T = X["co"], X["m"], X["T"]
    name = co.name
    L = m.latest
    key = f"A::{name}"
    if key not in st.session_state:
        st.session_state[key] = MD.default_assumptions(m, 5)
    A: MD.Assumptions = st.session_state[key]

    with card("mh"):
        c = st.columns([2.4, 1, 1, 1])
        with c[0]:
            st.markdown(f"<div class='crumb'>Auto financial model</div><div class='page-title'>{html.escape(name)}</div>"
                        f"<div class='card-sub'>Built from {m.latest_period} actuals and history. Edit anything below; every statement and the DCF recalculate.</div>", unsafe_allow_html=True)
        with c[1]:
            scenario = st.radio("Scenario", list(MD.SCENARIOS), index=1, horizontal=False, key="scenario")
        with c[2]:
            n_years = st.select_slider("Forecast years", [3, 4, 5, 6, 7, 8, 10], value=A.n_years, key="n_years")
        with c[3]:
            if st.button("Reset assumptions"):
                st.session_state[key] = MD.default_assumptions(m, n_years)
                for k in [k for k in st.session_state if str(k).startswith("as_")]:
                    del st.session_state[k]
                st.rerun()
    if n_years != A.n_years:
        st.session_state[key] = A = MD.default_assumptions(m, n_years)
        for k in [k for k in st.session_state if str(k).startswith("as_")]:
            del st.session_state[k]

    labels = MD.next_labels(m.latest_period, A.n_years)
    with st.expander("Assumptions (auto-filled from history — edit freely)", expanded=True):
        st.caption("Year-by-year drivers")
        cols = st.columns(A.n_years)
        for i, col in enumerate(cols):
            with col:
                A.rev_growth[i] = st.number_input(f"{labels[i]} growth %", value=float(A.rev_growth[i]), step=0.5, key=f"as_g{i}_{name}")
                A.ebitda_margin[i] = st.number_input(f"{labels[i]} EBITDA %", value=float(A.ebitda_margin[i]), step=0.5, key=f"as_m{i}_{name}")
                A.debt_change_pct[i] = st.number_input(f"{labels[i]} Δdebt %", value=float(A.debt_change_pct[i]), step=5.0, key=f"as_d{i}_{name}")
        st.caption("Structural drivers")
        c = st.columns(4)
        A.other_income_pct = c[0].number_input("Other income % sales", value=float(A.other_income_pct), step=0.1, key=f"as_oi_{name}")
        A.dep_pct_opening_block = c[1].number_input("Depreciation % opening block", value=float(A.dep_pct_opening_block), step=0.5, key=f"as_dp_{name}")
        A.interest_rate = c[2].number_input("Interest rate %", value=float(A.interest_rate), step=0.25, key=f"as_ir_{name}")
        A.tax_rate = c[3].number_input("Tax rate %", value=float(A.tax_rate), step=0.5, key=f"as_tx_{name}")
        c = st.columns(4)
        A.capex_pct_sales = c[0].number_input("Capex % sales", value=float(A.capex_pct_sales), step=0.5, key=f"as_cx_{name}")
        A.recv_days = c[1].number_input("Receivable days", value=float(A.recv_days), step=1.0, key=f"as_rd_{name}")
        A.inv_days = c[2].number_input("Inventory days", value=float(A.inv_days), step=1.0, key=f"as_iv_{name}")
        A.other_liab_pct_sales = c[3].number_input("Other liabilities % sales", value=float(A.other_liab_pct_sales), step=0.5, key=f"as_ol_{name}")
        c = st.columns(4)
        A.resid_assets_pct_sales = c[0].number_input("Misc. assets % sales", value=float(A.resid_assets_pct_sales), step=0.5, key=f"as_ms_{name}")
        A.payout_pct = c[1].number_input("Dividend payout %", value=float(A.payout_pct), step=1.0, key=f"as_py_{name}")
        A.min_cash = c[2].number_input("Minimum cash", value=float(A.min_cash), step=50.0, key=f"as_mc_{name}")
        A.minority_pct = c[3].number_input("Minority & others % of PAT", value=float(A.minority_pct), min_value=0.0, max_value=90.0, step=0.5, key=f"as_mn_{name}")
    st.session_state[key] = A

    proj = MD.project(m, A, scenario)
    for n_ in proj.notes:
        st.warning(n_)
    bal_err = float(proj.bs.loc["Check (L - A)"].abs().max())
    shown = [proj.base_label] + proj.labels
    pc = tuple(proj.labels)

    k = st.columns(4, gap="medium")
    last = proj.labels[-1]
    rev_c = ((proj.pl.loc["Revenue", last] / proj.pl.loc["Revenue", proj.base_label]) ** (1 / len(proj.labels)) - 1) * 100
    for col, (lab, val, sub) in zip(k, [(f"Revenue {last}", money(proj.pl.loc['Revenue', last]), f"CAGR {pct(rev_c)}"),
                                        (f"EBITDA {last}", money(proj.pl.loc['EBITDA', last]), f"margin {pct(proj.pl.loc['EBITDA', last] / proj.pl.loc['Revenue', last] * 100)}"),
                                        (f"Net profit {last}", money(proj.pl.loc['PAT', last]), f"EPS ₹{safe(proj.pl.loc['EPS', last], '{:.1f}')}"),
                                        (f"Cash {last}", money(proj.bs.loc['Cash', last]), "balance sheet balances ✓" if bal_err < 0.01 else f"imbalance {bal_err:.2f}")]):
        with col:
            with card("mk"):
                st.markdown(f"<div class='card-sub'>{lab}</div><div class='kpi-value'>{val}</div><div class='card-sub'>{sub}</div>", unsafe_allow_html=True)

    tabs = st.tabs(["Projected statements", "Charts", "DCF valuation", "Scenarios", "Ratios"])
    with tabs[0]:
        for ttl, df in (("Profit & loss", proj.pl), ("Balance sheet", proj.bs), ("Cash flow", proj.cf)):
            with card("ps"):
                card_title(ttl, f"{CURRENCY['symbol']} {CURRENCY['unit']} · projected columns in green")
                st.markdown(html_table(df[shown], proj_cols=pc), unsafe_allow_html=True)
    with tabs[1]:
        c = st.columns(2, gap="medium")
        with c[0]:
            with card("mc1"):
                plot(C.projection_chart(m.df, proj.pl, proj.base_label, proj.labels, T, "Revenue"))
        with c[1]:
            with card("mc2"):
                plot(C.projection_chart(m.df, proj.pl, proj.base_label, proj.labels, T, "PAT"))
        c = st.columns(2, gap="medium")
        with c[0]:
            with card("mc3"):
                rt = proj.ratios.T
                plot(C.area_line(rt, ["EBITDA Margin %", "Net Margin %", "ROCE %", "ROE %"], T, title="Margins and returns (%)", fill_first=False))
        with c[1]:
            with card("mc4"):
                cf = proj.cf.T[["CFO", "Capex", "FCF"]].copy()
                import plotly.graph_objects as go
                fig = go.Figure()
                fig.add_trace(go.Bar(x=cf.index, y=cf["CFO"], name="CFO", marker=dict(color=T["cat"][0], cornerradius=4)))
                fig.add_trace(go.Bar(x=cf.index, y=-cf["Capex"], name="Capex", marker=dict(color=T["cat"][2], cornerradius=4)))
                fig.add_trace(go.Scatter(x=cf.index, y=cf["FCF"], name="FCF", mode="lines+markers", line=dict(color=T["lime"], width=2.4)))
                C._base(fig, T, title="Operating cash flow, capex and FCF").update_layout(barmode="group")
                plot(fig)
    with tabs[2]:
        with st.expander("Estimate WACC with CAPM (optional)"):
            c = st.columns(5)
            rf = c[0].number_input("Risk-free %", value=7.0, step=0.1, key="rf")
            beta = c[1].number_input("Beta", value=1.0, step=0.05, key="beta")
            erp = c[2].number_input("Equity risk premium %", value=5.5, step=0.1, key="erp")
            kd = c[3].number_input("Pre-tax cost of debt %", value=A.interest_rate, step=0.25, key="kd")
            wd = c[4].number_input("Debt weight %", value=float(np.clip((L.get("Debt") or 0) / ((L.get("Debt") or 0) + (L.get("Market Cap") if not is_nan(L.get("Market Cap")) else (L.get("Equity") or 1))) * 100, 0, 80)), step=1.0, key="wd")
            w = MD.wacc_capm(rf, beta, erp, kd, A.tax_rate, wd / 100)
            st.write(f"Cost of equity **{w['cost_of_equity']:.2f}%** · after-tax cost of debt **{w['cost_of_debt_after_tax']:.2f}%** · WACC **{w['wacc']:.2f}%**")
            if st.button("Use this WACC"):
                st.session_state["wacc_in"] = round(w["wacc"], 2)
                st.rerun()
        c = st.columns(4)
        wacc_v = c[0].number_input("WACC %", value=float(st.session_state.get("wacc_in", 12.0)), step=0.25, key="wacc_in")
        g_v = c[1].number_input("Terminal growth %", value=5.0, step=0.25, key="g_in")
        mid = c[2].toggle("Mid-year discounting", value=False)
        price_default = float(L.get("Price")) if not is_nan(L.get("Price")) else 0.0
        price_v = c[3].number_input("Current price ₹", value=price_default, step=1.0, key=f"px_{name}")
        sh_in = None
        if is_nan(L.get("Shares (Cr)")):
            sh_in = st.number_input("Shares outstanding (Cr) — not found in your data; needed for per-share value", min_value=0.0, value=float(st.session_state.get(f"sh_{name}", 0.0)), step=1.0, key=f"sh_{name}") or None
        inp = MD.DCFInputs(wacc_v, g_v, mid, True, price_v or None, sh_in)
        res = MD.run_dcf(m, proj, inp)
        X["dcf"] = res
        if "error" in res:
            st.error(res["error"])
        else:
            k = st.columns(4, gap="medium")
            ups = res["upside"]
            for col, (lab, val, extra) in zip(k, [("Enterprise value", money(res["ev"]), f"terminal value = {pct(res['tv_share'], 0)} of EV"),
                                                  ("Equity value", money(res["equity"]), f"net cash/(debt) adj. {money(res['cash'] + res['investments'] - res['debt'])}"),
                                                  ("Value per share", f"₹{res['per_share']:,.0f}" if not is_nan(res["per_share"]) else "n/a", f"implied exit {mult(res['implied_exit_multiple'])} EBITDA" if not is_nan(res["per_share"]) else "enter share count above"),
                                                  ("vs market price", pill(ups), f"market ₹{res['price']:,.0f}" if res.get("price") else "enter a price")]):
                with col:
                    with card("dk"):
                        st.markdown(f"<div class='card-sub'>{lab}</div><div class='kpi-value'>{val}</div><div class='card-sub'>{extra}</div>", unsafe_allow_html=True)
            c = st.columns([1.2, 1], gap="medium")
            with c[0]:
                with card("dt"):
                    card_title("Free cash flow to firm", f"{CURRENCY['symbol']} {CURRENCY['unit']}")
                    tdf = res["fcff"].copy()
                    tdf.loc["Discounted FCFF"] = res["pv"]
                    st.markdown(html_table(tdf, proj_cols=tuple(tdf.columns)), unsafe_allow_html=True)
            with c[1]:
                with card("dsn"):
                    grid = MD.sensitivity(m, proj, inp)
                    plot(C.heatmap(grid, T, title="Value per share (₹): WACC vs terminal growth", fmt=",.0f"))
            if res["tv_share"] > 75:
                st.info(f"Terminal value is {res['tv_share']:.0f}% of enterprise value, so the result is very sensitive to WACC and terminal growth. Treat it as a range.")
    with tabs[3]:
        inp2 = MD.DCFInputs(float(st.session_state.get("wacc_in", 12.0)), float(st.session_state.get("g_in", 5.0)), False, True,
                            (st.session_state.get(f"px_{name}") or None))
        summ = MD.scenario_summary(m, A, inp2)
        X["scen"] = summ
        c = st.columns([1.2, 1], gap="medium")
        with c[0]:
            with card("sn1"):
                card_title("Bear / Base / Bull", "growth −4 / 0 / +4 pp · margin −2 / 0 / +1.5 pp versus your assumptions")
                st.markdown(html_table(summ, d=1), unsafe_allow_html=True)
        with c[1]:
            with card("sn2"):
                plot(C.scenario_chart(summ, T, price=inp2.current_price))
    with tabs[4]:
        with card("pr"):
            card_title("Projected ratios")
            st.markdown(html_table(proj.ratios, proj_cols=pc), unsafe_allow_html=True)

    X["proj"] = proj
    X["assumptions"] = A
    X["scenario"] = scenario
    X["dcf_inputs"] = (float(st.session_state.get("wacc_in", 12.0)), float(st.session_state.get("g_in", 5.0)))


# =============================================================================
def compare(X):
    T = X["T"]
    comps = st.session_state.companies
    names = list(comps)
    if len(names) < 2:
        with card("cmp0"):
            st.markdown("### Add at least two companies")
            st.write("Upload more Screener / Excel / CSV files in **Data Hub** (each upload becomes a company), or load a second demo company to try this page.")
            if st.button("Load a second demo company", type="primary"):
                X["load_demo_peer"]()
                st.rerun()
        return
    from .analytics import Metrics
    sel = st.multiselect("Companies", names, default=names[:4], key="cmp_sel")
    if len(sel) < 2:
        st.info("Select two or more companies.")
        return
    ms = {n: Metrics(comps[n]) for n in sel}
    rows = {}
    for n, mm in ms.items():
        L = mm.latest
        rows[n] = {"Period": mm.latest_period, "Revenue": L["Revenue"], "EBITDA": L["EBITDA"], "PAT": L["PAT"], "Revenue CAGR 3y %": mm.cagr("Revenue", 3),
                   "EBITDA Margin %": L["EBITDA Margin %"], "Net Margin %": L["Net Margin %"], "ROE %": L["ROE %"], "ROCE %": L["ROCE %"],
                   "Debt / Equity": L["Debt / Equity"], "Interest Coverage": L["Interest Coverage"], "CFO / PAT": L["CFO / PAT"], "P/E": L["P/E"], "P/B": L["P/B"],
                   "EV/EBITDA": L["EV/EBITDA"], "Health score": mm.score()[0]}
    df = pd.DataFrame(rows).T
    with card("cmp1"):
        card_title("Side-by-side (latest period)")
        st.markdown(html_table(df.T), unsafe_allow_html=True)
    metric = st.selectbox("Compare on", [c for c in df.columns if c != "Period"], index=4, key="cmp_metric")
    c = st.columns(2, gap="medium")
    num_df = df.drop(columns=["Period"]).astype(float)
    with c[0]:
        with card("cmp2"):
            plot(C.compare_bar(num_df, metric, T))
    with c[1]:
        with card("cmp3"):
            plot(C.compare_lines({n: mm.df["Revenue"] for n, mm in ms.items()}, T, "Revenue indexed to 100 at first year", rebase=True))
    c = st.columns(2, gap="medium")
    with c[0]:
        with card("cmp4"):
            plot(C.compare_lines({n: mm.df["EBITDA Margin %"] for n, mm in ms.items()}, T, "EBITDA margin (%)"))
    with c[1]:
        with card("cmp5"):
            plot(C.compare_lines({n: mm.df["ROCE %"] for n, mm in ms.items()}, T, "ROCE (%)"))
    if all(not is_nan(x) for x in num_df.index.map(lambda n: 1)):
        import plotly.graph_objects as go
        with card("cmp6"):
            fig = go.Figure()
            for i, n in enumerate(sel):
                hs = health_scores(ms[n])
                fig.add_trace(go.Scatterpolar(r=list(hs.values()) + [list(hs.values())[0]], theta=list(hs) + [list(hs)[0]], name=n, line=dict(color=T["cat"][i % 6], width=2),
                                              fill="toself", fillcolor=C._spark_fill(T["cat"][i % 6], 0.10)))
            fig.update_layout(height=340, margin=dict(l=40, r=40, t=20, b=30), paper_bgcolor="rgba(0,0,0,0)", font=dict(color=T["text2"]),
                              polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(range=[0, 100], gridcolor=T["grid"]), angularaxis=dict(gridcolor=T["grid"])),
                              legend=dict(orientation="h", y=-0.08))
            plot(fig)
