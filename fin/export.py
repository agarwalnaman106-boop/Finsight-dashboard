"""Exports: Excel workbook (with a live-formula model), PDF report, standalone HTML dashboard."""
from __future__ import annotations

import io
from datetime import datetime

import numpy as np
import pandas as pd

from .analytics import Metrics
from .model import Assumptions, Projection, SCENARIOS, project
from .narrative import build_case_study
from .utils import money, pct

KPI_ROWS = [
    ("Revenue", "Revenue"), ("EBITDA", "EBITDA"), ("EBITDA margin %", "EBITDA Margin %"), ("Net profit (PAT)", "PAT"),
    ("Net margin %", "Net Margin %"), ("EPS (₹)", "EPS"), ("ROE %", "ROE %"), ("ROCE %", "ROCE %"),
    ("Debt / Equity", "Debt / Equity"), ("Interest coverage (x)", "Interest Coverage"), ("Operating cash flow", "CFO"),
    ("Free cash flow", "FCF"), ("Dividend payout %", "Dividend Payout %"), ("P/E (x)", "P/E"), ("P/B (x)", "P/B"),
    ("EV/EBITDA (x)", "EV/EBITDA"),
]


def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v) or np.isinf(v):
            return None
    except Exception:
        pass
    return float(v) if isinstance(v, (np.floating, np.integer)) else v


# ----------------------------------------------------------------------------
# Excel
# ----------------------------------------------------------------------------
def to_excel(m: Metrics, co, A: Assumptions | None = None, scenario: str = "Base", wacc: float = 12.0, g: float = 5.0) -> bytes:
    import xlsxwriter
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": False})
    GREEN, DARKBG = "#0f9d6a", "#0d1512"
    f_title = wb.add_format({"bold": True, "font_size": 16, "font_color": DARKBG})
    f_hdr = wb.add_format({"bold": True, "bg_color": DARKBG, "font_color": "#ffffff", "align": "center", "border": 1})
    f_lbl = wb.add_format({"bold": False, "border": 1})
    f_lblb = wb.add_format({"bold": True, "border": 1, "bg_color": "#e8f5ee"})
    f_num = wb.add_format({"num_format": "#,##0.0;[Red]-#,##0.0", "border": 1})
    f_numb = wb.add_format({"num_format": "#,##0.0;[Red]-#,##0.0", "border": 1, "bold": True, "bg_color": "#e8f5ee"})
    f_inp = wb.add_format({"num_format": "0.0", "border": 1, "font_color": "#0000ff", "bg_color": "#fff9db"})
    f_pct = wb.add_format({"num_format": "0.0", "border": 1})
    f_note = wb.add_format({"italic": True, "font_color": "#555555", "text_wrap": True})
    f_chk = wb.add_format({"num_format": "0.00;[Red]-0.00", "border": 1, "font_color": "#888888"})

    # ---- Summary ----
    ws = wb.add_worksheet("Summary")
    ws.hide_gridlines(2)
    ws.set_column(0, 0, 32)
    ws.set_column(1, 12, 13)
    ws.write(0, 0, f"{co.name} — Financial summary", f_title)
    ws.write(1, 0, f"Generated {datetime.now():%d %b %Y} · Source: {', '.join(co.sources) or 'user data'} · Amounts in {co.meta.get('unit_label', '₹ Cr')}", f_note)
    tail = m.df.tail(10)
    ws.write(3, 0, "Metric", f_hdr)
    for j, p in enumerate(tail.index):
        ws.write(3, 1 + j, p, f_hdr)
    for i, (lab, col) in enumerate(KPI_ROWS):
        ws.write(4 + i, 0, lab, f_lbl)
        for j, p in enumerate(tail.index):
            v = _clean(tail.loc[p, col]) if col in tail.columns else None
            ws.write(4 + i, 1 + j, v if v is not None else "", f_num)
    n = len(tail)
    ch = wb.add_chart({"type": "column"})
    for r, color in ((4, GREEN), (7, "#c98500")):
        ch.add_series({"name": ["Summary", r, 0], "categories": ["Summary", 3, 1, 3, n], "values": ["Summary", r, 1, r, n],
                       "fill": {"color": color}, "gap": 80})
    ch.set_title({"name": "Revenue vs Net profit"}); ch.set_legend({"position": "bottom"}); ch.set_size({"width": 560, "height": 300})
    ws.insert_chart(4 + len(KPI_ROWS) + 2, 0, ch)
    ch2 = wb.add_chart({"type": "line"})
    for r, color in ((6, GREEN), (8, "#3987e5")):
        ch2.add_series({"name": ["Summary", r, 0], "categories": ["Summary", 3, 1, 3, n], "values": ["Summary", r, 1, r, n],
                        "line": {"color": color, "width": 2.25}})
    ch2.set_title({"name": "Margins (%)"}); ch2.set_legend({"position": "bottom"}); ch2.set_size({"width": 560, "height": 300})
    ws.insert_chart(4 + len(KPI_ROWS) + 2, 5, ch2)

    # ---- Statements ----
    for title, df in co.tables().items():
        if df.empty:
            continue
        w = wb.add_worksheet(title[:31])
        w.set_column(0, 0, 34); w.set_column(1, 30, 12)
        w.write(0, 0, f"{co.name} — {title}", f_title)
        w.write(2, 0, "Line item", f_hdr)
        for j, c in enumerate(df.columns):
            w.write(2, 1 + j, c, f_hdr)
        for i, idx in enumerate(df.index):
            bold = str(idx).lower().startswith(("total", "net profit", "profit before", "sales"))
            w.write(3 + i, 0, idx, f_lblb if bold else f_lbl)
            for j, c in enumerate(df.columns):
                v = _clean(df.loc[idx, c])
                w.write(3 + i, 1 + j, v if v is not None else "", f_numb if bold else f_num)
        w.freeze_panes(3, 1)

    # ---- Ratios ----
    w = wb.add_worksheet("Ratios")
    w.set_column(0, 0, 30); w.set_column(1, 30, 11)
    w.write(0, 0, "Ratio analysis", f_title)
    ratio_cols = [c for c in m.df.columns if any(t in c for t in ("%", "/", "Days", "Coverage", "Turnover", "Multiplier", "EPS", "BVPS", "DPS", "Yield"))]
    w.write(2, 0, "Ratio", f_hdr)
    for j, p in enumerate(m.df.index):
        w.write(2, 1 + j, p, f_hdr)
    for i, c in enumerate(ratio_cols):
        w.write(3 + i, 0, c, f_lbl)
        for j, p in enumerate(m.df.index):
            v = _clean(m.df.loc[p, c])
            w.write(3 + i, 1 + j, v if v is not None else "", f_pct)
    w.freeze_panes(3, 1)

    # ---- Live model ----
    if A is not None:
        _live_model(wb, m, A, scenario, wacc, g, dict(title=f_title, hdr=f_hdr, lbl=f_lbl, lblb=f_lblb, num=f_num, numb=f_numb,
                                                        inp=f_inp, note=f_note, chk=f_chk))
    wb.close()
    return buf.getvalue()


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _live_model(wb, m: Metrics, A: Assumptions, scenario: str, wacc: float, g: float, F: dict):
    ws = wb.add_worksheet("Live Model")
    ws.set_column(0, 0, 38); ws.set_column(1, 12, 13)
    base = project(m, A, "Base")
    n = A.n_years
    L = m.latest
    ws.write(0, 0, "Live 3-statement model (edit the yellow cells; everything else recalculates)", F["title"])
    ws.write(1, 0, "Blue-on-yellow = input. Scenario deltas let you flex growth/margin without touching the base path.", F["note"])
    ws.write(3, 0, "Item", F["hdr"])
    ws.write(3, 1, base.base_label, F["hdr"])
    for t, lab in enumerate(base.labels):
        ws.write(3, 2 + t, lab, F["hdr"])

    names = ["g", "mg", "dchg", "oi", "dep", "ir", "tx", "cx", "rd", "idays", "olp", "misc", "pay", "mn", "mincash", "gd", "md", "shares",
             "rev", "ebitda", "oinc", "depn", "intr", "pbt", "tax", "mino", "pat", "div", "eps",
             "sc", "res", "debt", "olc", "ol", "tl", "nb", "cwip", "invs", "recv", "inv", "misca", "cash", "ta", "chk",
             "cfo", "capex", "cfi", "cff", "ncf", "fcf", "dnwc", "draw"]
    labels = {
        "g": "Revenue growth % (per year)", "mg": "EBITDA margin % (per year)", "dchg": "Change in debt % (per year)",
        "oi": "Other income % of sales", "dep": "Depreciation % of opening net block", "ir": "Interest rate % on opening debt",
        "tx": "Tax rate %", "cx": "Capex % of sales", "rd": "Receivable days", "idays": "Inventory days",
        "olp": "Other liabilities % of sales", "misc": "Misc. assets % of sales", "pay": "Dividend payout %", "mn": "Minority & others % of PAT",
        "mincash": "Minimum cash balance", "gd": "Scenario: growth Δ (pp)", "md": "Scenario: margin Δ (pp)", "shares": "Shares (Cr)",
        "rev": "Revenue", "ebitda": "EBITDA", "oinc": "Other income", "depn": "Depreciation", "intr": "Interest", "pbt": "Profit before tax",
        "tax": "Tax", "mino": "Less: minority, associates & others", "pat": "Net profit (to owners)", "div": "Dividend", "eps": "EPS (₹)",
        "sc": "Share capital", "res": "Reserves", "debt": "Borrowings", "olc": "Other liabilities, excl. accumulated minority", "ol": "Other liabilities (incl. minority)", "tl": "Total liabilities",
        "nb": "Net block", "cwip": "CWIP", "invs": "Investments", "recv": "Receivables", "inv": "Inventory",
        "misca": "Other assets (misc.)", "cash": "Cash & bank", "ta": "Total assets", "chk": "Balance check (should be 0)",
        "cfo": "Cash from operations", "capex": "Capex", "cfi": "Cash from investing", "cff": "Cash from financing",
        "ncf": "Net cash flow", "fcf": "Free cash flow", "dnwc": "Increase in net working capital", "draw": "Revolver draw",
    }
    gd, md = SCENARIOS.get(scenario, (0, 0))
    row = {}
    r = 4
    sections = {"g": "ASSUMPTIONS", "rev": "PROFIT & LOSS", "sc": "BALANCE SHEET", "cfo": "CASH FLOW"}
    for k in names:
        if k in sections:
            ws.write(r, 0, sections[k], F["lblb"]); r += 1
        row[k] = r + 1  # 1-based excel row
        ws.write(r, 0, labels[k], F["lbl"])
        r += 1
    R = lambda k: row[k]  # noqa: E731

    sc_vals = dict(oi=A.other_income_pct, dep=A.dep_pct_opening_block, ir=A.interest_rate, tx=A.tax_rate, cx=A.capex_pct_sales,
                   rd=A.recv_days, idays=A.inv_days, olp=A.other_liab_pct_sales, misc=A.resid_assets_pct_sales, pay=A.payout_pct, mn=A.minority_pct,
                   mincash=A.min_cash, gd=gd, md=md, shares=float(L.get("Shares (Cr)", np.nan)) if pd.notna(L.get("Shares (Cr)", np.nan)) else 1.0)
    for k, v in sc_vals.items():
        ws.write(R(k) - 1, 1, _clean(v), F["inp"])
    per_year = {"g": A.rev_growth, "mg": A.ebitda_margin, "dchg": A.debt_change_pct}
    for k, arr in per_year.items():
        arr = (list(arr) + [arr[-1] if len(arr) else 0] * n)[:n]
        for t in range(n):
            ws.write(R(k) - 1, 2 + t, float(arr[t]), F["inp"])

    # base-year actuals
    b = base.pl[base.base_label], base.bs[base.base_label], base.cf[base.base_label]
    basev = {"rev": b[0]["Revenue"], "ebitda": b[0]["EBITDA"], "oinc": b[0]["Other Income"], "depn": b[0]["Depreciation"],
             "intr": b[0]["Interest"], "pbt": b[0]["PBT"], "tax": b[0]["Tax"], "mino": b[0]["Minority & others"], "pat": b[0]["PAT"], "div": b[0]["Dividend"],
             "sc": b[1]["Share Capital"], "res": b[1]["Reserves"], "debt": b[1]["Debt"], "ol": b[1]["Other Liabilities"], "olc": b[1]["Other Liabilities"],
             "nb": b[1]["Net Block"], "cwip": b[1]["CWIP"], "invs": b[1]["Investments"], "recv": b[1]["Receivables"],
             "inv": b[1]["Inventory"], "misca": b[1]["Other Assets (misc.)"], "cash": b[1]["Cash"],
             "cfo": b[2]["CFO"], "capex": b[2]["Capex"], "cfi": b[2]["CFI"], "cff": b[2]["CFF"], "ncf": b[2]["Net Cash Flow"],
             "fcf": b[2]["FCF"]}
    for k, v in basev.items():
        v = _clean(v)
        ws.write(R(k) - 1, 1, v if v is not None else "", F["num"])
    ws.write_formula(R("eps") - 1, 1, f"=B{R('pat')}/$B${R('shares')}", F["num"])
    ws.write_formula(R("tl") - 1, 1, f"=B{R('sc')}+B{R('res')}+B{R('debt')}+B{R('ol')}", F["numb"])
    ws.write_formula(R("ta") - 1, 1, f"=B{R('nb')}+B{R('cwip')}+B{R('invs')}+B{R('recv')}+B{R('inv')}+B{R('misca')}+B{R('cash')}", F["numb"])
    ws.write_formula(R("chk") - 1, 1, f"=B{R('tl')}-B{R('ta')}", F["chk"])

    for t in range(n):
        c, p = _col(2 + t), _col(1 + t)
        k = R
        debt_plan = f"MAX({p}{k('debt')}*(1+{c}{k('dchg')}/100),0)"
        fm = {
            "rev": f"={p}{k('rev')}*(1+({c}{k('g')}+$B${k('gd')})/100)",
            "ebitda": f"={c}{k('rev')}*({c}{k('mg')}+$B${k('md')})/100",
            "oinc": f"={c}{k('rev')}*$B${k('oi')}/100",
            "depn": f"={p}{k('nb')}*$B${k('dep')}/100",
            "intr": f"={p}{k('debt')}*$B${k('ir')}/100",
            "pbt": f"={c}{k('ebitda')}+{c}{k('oinc')}-{c}{k('depn')}-{c}{k('intr')}",
            "tax": f"=MAX({c}{k('pbt')},0)*$B${k('tx')}/100",
            "mino": f"=MAX({c}{k('pbt')}-{c}{k('tax')},0)*$B${k('mn')}/100",
            "pat": f"={c}{k('pbt')}-{c}{k('tax')}-{c}{k('mino')}",
            "div": f"=MAX({c}{k('pat')},0)*$B${k('pay')}/100",
            "eps": f"={c}{k('pat')}/$B${k('shares')}",
            "sc": f"={p}{k('sc')}",
            "res": f"={p}{k('res')}+{c}{k('pat')}-{c}{k('div')}",
            "debt": f"={debt_plan}+{c}{k('draw')}",
            "olc": f"={c}{k('rev')}*$B${k('olp')}/100",
            "ol": f"={c}{k('olc')}+({p}{k('ol')}-{p}{k('olc')})+{c}{k('mino')}",
            "nb": f"=MAX({p}{k('nb')}+{c}{k('capex')}-{c}{k('depn')},0)",
            "cwip": f"={p}{k('cwip')}", "invs": f"={p}{k('invs')}",
            "recv": f"={c}{k('rev')}*$B${k('rd')}/365", "inv": f"={c}{k('rev')}*$B${k('idays')}/365",
            "misca": f"={c}{k('rev')}*$B${k('misc')}/100",
            "cash": f"={p}{k('cash')}+{c}{k('ncf')}",
            "tl": f"={c}{k('sc')}+{c}{k('res')}+{c}{k('debt')}+{c}{k('ol')}",
            "ta": f"={c}{k('nb')}+{c}{k('cwip')}+{c}{k('invs')}+{c}{k('recv')}+{c}{k('inv')}+{c}{k('misca')}+{c}{k('cash')}",
            "chk": f"={c}{k('tl')}-{c}{k('ta')}",
            "cfo": f"={c}{k('pat')}+{c}{k('mino')}+{c}{k('depn')}-{c}{k('dnwc')}",
            "capex": f"={c}{k('rev')}*$B${k('cx')}/100",
            "cfi": f"=-{c}{k('capex')}",
            "draw": f"=MAX(0,$B${k('mincash')}-({p}{k('cash')}+{c}{k('cfo')}+{c}{k('cfi')}+({debt_plan}-{p}{k('debt')})-{c}{k('div')}))",
            "cff": f"=({debt_plan}-{p}{k('debt')})-{c}{k('div')}+{c}{k('draw')}",
            "ncf": f"={c}{k('cfo')}+{c}{k('cfi')}+{c}{k('cff')}",
            "fcf": f"={c}{k('cfo')}-{c}{k('capex')}",
            "dnwc": f"=({c}{k('recv')}+{c}{k('inv')}+{c}{k('misca')})-({p}{k('recv')}+{p}{k('inv')}+{p}{k('misca')})-({c}{k('olc')}-{p}{k('olc')})",
        }
        for key, formula in fm.items():
            fmt = F["chk"] if key == "chk" else F["numb"] if key in ("rev", "pat", "tl", "ta", "fcf") else F["num"]
            ws.write_formula(R(key) - 1, 2 + t, formula, fmt)

    # DCF block
    d0 = r + 2
    ws.write(d0, 0, "DCF VALUATION (live)", F["lblb"])
    ws.write(d0 + 1, 0, "WACC %", F["lbl"]); ws.write(d0 + 1, 1, wacc, F["inp"])
    ws.write(d0 + 2, 0, "Terminal growth %", F["lbl"]); ws.write(d0 + 2, 1, g, F["inp"])
    ws.write(d0 + 3, 0, "FCFF", F["lbl"])
    ws.write(d0 + 4, 0, "Discount factor", F["lbl"])
    ws.write(d0 + 5, 0, "PV of FCFF", F["lbl"])
    last = _col(1 + n)
    for t in range(n):
        c = _col(2 + t)
        ws.write_formula(d0 + 3, 2 + t, f"=({c}{R('ebitda')}-{c}{R('depn')})*(1-$B${R('tx')}/100)+{c}{R('depn')}-{c}{R('capex')}-{c}{R('dnwc')}", F["num"])
        ws.write_formula(d0 + 4, 2 + t, f"=1/(1+$B${d0 + 2}/100)^{t + 1}", F["num"])
        ws.write_formula(d0 + 5, 2 + t, f"={c}{d0 + 4}*{c}{d0 + 5}", F["num"])
    ws.write(d0 + 6, 0, "Terminal value (at end of last year)", F["lbl"])
    ws.write_formula(d0 + 6, 1, f"={last}{d0 + 4}*(1+$B${d0 + 3}/100)/(($B${d0 + 2}-$B${d0 + 3})/100)", F["num"])
    ws.write(d0 + 7, 0, "PV of terminal value", F["lbl"])
    ws.write_formula(d0 + 7, 1, f"=B{d0 + 7}*{last}{d0 + 5}", F["num"])
    ws.write(d0 + 8, 0, "Enterprise value", F["lblb"])
    ws.write_formula(d0 + 8, 1, f"=SUM(C{d0 + 6}:{last}{d0 + 6})+B{d0 + 8}", F["numb"])
    ws.write(d0 + 9, 0, "Less: debt / Add: cash + investments (latest actual)", F["lbl"])
    ws.write_formula(d0 + 9, 1, f"=-B{R('debt')}+B{R('cash')}+B{R('invs')}", F["num"])
    ws.write(d0 + 10, 0, "Equity value (after minority share)", F["lblb"])
    ws.write_formula(d0 + 10, 1, f"=(B{d0 + 9}+B{d0 + 10})*(1-$B${R('mn')}/100)", F["numb"])
    ws.write(d0 + 11, 0, "Value per share (₹)", F["lblb"])
    ws.write_formula(d0 + 11, 1, f"=B{d0 + 11}/$B${R('shares')}", F["numb"])
    ws.freeze_panes(4, 1)
    return {"value_cell": f"B{d0 + 12}", "check_row": R("chk"), "pat_row": R("pat"), "last_col": last}


# ----------------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------------
def _mpl_charts(m: Metrics, proj: Projection | None) -> dict[str, bytes]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C = ["#1baf7a", "#eda100", "#2a78d6", "#e87ba4", "#6250d6", "#eb6834"]
    plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#cfdad3",
                         "axes.labelcolor": "#46544d", "xtick.color": "#46544d", "ytick.color": "#46544d"})
    d = m.df.tail(8)
    out = {}

    def save(fig, key):
        b = io.BytesIO()
        fig.savefig(b, format="png", dpi=170, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        out[key] = b.getvalue()

    fig, ax = plt.subplots(figsize=(6.2, 2.7))
    x = np.arange(len(d)); w = 0.38
    b1 = ax.bar(x - w / 2, d["Revenue"], w, color=C[0], label="Revenue")
    b2 = ax.bar(x + w / 2, d["PAT"], w, color=C[1], label="Net profit")
    ax.set_xticks(x, d.index); ax.legend(frameon=False, ncol=2, loc="upper left"); ax.set_title("Revenue and net profit", loc="left", fontsize=9, fontweight="bold")
    ax.bar_label(b1, fmt="%.0f", fontsize=6, padding=1); ax.bar_label(b2, fmt="%.0f", fontsize=6, padding=1)
    ax.yaxis.grid(True, color="#e8eeea"); ax.set_axisbelow(True)
    save(fig, "rev_pat")

    fig, ax = plt.subplots(figsize=(6.2, 2.5))
    for i, (c, lab) in enumerate([("EBITDA Margin %", "EBITDA margin"), ("Net Margin %", "Net margin"), ("ROCE %", "ROCE")]):
        if d[c].dropna().empty:
            continue
        ax.plot(d.index, d[c], color=C[i], lw=2, marker="o", ms=4, label=lab)
        ax.annotate(f"{d[c].dropna().iloc[-1]:.1f}%", (len(d) - 1, d[c].dropna().iloc[-1]), xytext=(4, 0), textcoords="offset points", fontsize=7, color="#0d1512")
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12)); ax.yaxis.grid(True, color="#e8eeea")
    ax.set_title("Margins and returns (%)", loc="left", fontsize=9, fontweight="bold")
    save(fig, "margins")

    fig, axs = plt.subplots(1, 2, figsize=(6.2, 2.7), gridspec_kw={"width_ratios": [1, 1]})
    cs = m.cost_structure()
    if len(cs):
        cs = cs.sort_values(ascending=False)
        top = cs.head(5)
        if len(cs) > 5:
            top["Others"] = cs.iloc[5:].sum()
        axs[0].pie(top.values, labels=None, colors=(C + ["#9aa7a0"])[: len(top)], startangle=90, wedgeprops=dict(width=0.42, edgecolor="white"))
        axs[0].legend([f"{k} ({v / top.sum() * 100:.0f}%)" for k, v in top.items()], frameon=False, fontsize=6.5, loc="center left", bbox_to_anchor=(0.95, 0.5))
        axs[0].set_title("Cost structure", loc="left", fontsize=9, fontweight="bold")
    L = m.latest
    comp = {"Net block": L.get("Net Block"), "CWIP": L.get("CWIP"), "Investments": L.get("Investments"), "Receivables": L.get("Receivables"),
            "Inventory": L.get("Inventory"), "Cash": L.get("Cash"), "Other": L.get("Other Current/Misc Assets")}
    comp = pd.Series({k: v for k, v in comp.items() if pd.notna(v) and v > 0})
    if len(comp):
        axs[1].pie(comp.values, colors=(C + ["#9aa7a0", "#7a8881"])[: len(comp)], startangle=90, wedgeprops=dict(width=0.42, edgecolor="white"))
        axs[1].legend([f"{k} ({v / comp.sum() * 100:.0f}%)" for k, v in comp.items()], frameon=False, fontsize=6.5, loc="center left", bbox_to_anchor=(0.95, 0.5))
        axs[1].set_title("Asset mix", loc="left", fontsize=9, fontweight="bold")
    fig.subplots_adjust(wspace=1.15)
    save(fig, "mix")

    if d["CFO"].notna().any():
        fig, ax = plt.subplots(figsize=(6.2, 2.5))
        x = np.arange(len(d)); w = 0.26
        ax.bar(x - w, d["CFO"], w, color=C[0], label="Operating"); ax.bar(x, d["CFI"], w, color=C[2], label="Investing"); ax.bar(x + w, d["CFF"], w, color=C[3], label="Financing")
        ax.plot(x, d["FCF"], color="#0d1512", lw=1.8, marker="o", ms=3, label="Free cash flow")
        ax.axhline(0, color="#9aa7a0", lw=0.8); ax.set_xticks(x, d.index); ax.legend(frameon=False, ncol=4, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.12))
        ax.yaxis.grid(True, color="#e8eeea"); ax.set_axisbelow(True); ax.set_title("Cash flows", loc="left", fontsize=9, fontweight="bold")
        save(fig, "cash")

    if proj is not None:
        cols = [proj.base_label] + proj.labels
        fig, ax = plt.subplots(figsize=(6.2, 2.5))
        x = np.arange(len(cols)); w = 0.38
        ax.bar(x - w / 2, proj.pl.loc["Revenue", cols], w, color=[C[0]] + [C[0]] * len(proj.labels), alpha=1, label="Revenue")
        ax.bar(x + w / 2, proj.pl.loc["PAT", cols], w, color=C[1], label="Net profit")
        ax.set_xticks(x, [c.replace(" (A)", "") for c in cols]); ax.legend(frameon=False, ncol=2, loc="upper left")
        ax.yaxis.grid(True, color="#e8eeea"); ax.set_axisbelow(True); ax.set_title("Projection (base case)", loc="left", fontsize=9, fontweight="bold")
        save(fig, "proj")
    return out


_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
]


def _register_unicode_font():
    """Register a TTF that contains the rupee sign. Returns (regular, bold) names or None."""
    import os
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for reg, bold in _FONT_CANDIDATES:
        if os.path.exists(reg) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("FS-Regular", reg))
                pdfmetrics.registerFont(TTFont("FS-Bold", bold))
                from reportlab.lib.fonts import addMapping
                addMapping("FS-Regular", 0, 0, "FS-Regular"); addMapping("FS-Regular", 1, 0, "FS-Bold")
                addMapping("FS-Regular", 0, 1, "FS-Regular"); addMapping("FS-Regular", 1, 1, "FS-Bold")
                if 0x20B9 in pdfmetrics.getFont("FS-Regular").face.charToGlyph:
                    return "FS-Regular", "FS-Bold"
            except Exception:
                continue
    return None


def to_pdf(m: Metrics, co, report: dict | None = None, proj: Projection | None = None, dcf: dict | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    GREEN = colors.HexColor("#0f9d6a"); INK = colors.HexColor("#0d1512"); GREY = colors.HexColor("#46544d")
    fonts = _register_unicode_font()
    ss = getSampleStyleSheet()
    base_font, bold_font = fonts or ("Helvetica", "Helvetica-Bold")
    for st in ss.byName.values():
        try:
            st.fontName = bold_font if "Bold" in st.fontName else base_font
        except Exception:
            pass
    H1 = ParagraphStyle("H1", parent=ss["Title"], textColor=INK, fontSize=22, leading=26, alignment=0, spaceAfter=4)
    H2 = ParagraphStyle("H2", parent=ss["Heading2"], textColor=GREEN, fontSize=13, spaceBefore=10, spaceAfter=4)
    B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9, leading=13, textColor=INK)
    SM = ParagraphStyle("SM", parent=B, fontSize=7.5, leading=10, textColor=GREY)
    BU = ParagraphStyle("BU", parent=B, leftIndent=10, bulletIndent=0)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
                            title=f"{co.name} — Financial report", author="FinSight")
    S = []
    L = m.latest
    S.append(Paragraph(co.name, H1))
    S.append(Paragraph(f"Financial analysis · Latest period {m.latest_period} · Generated {datetime.now():%d %b %Y}", SM))
    S.append(Spacer(1, 6))
    ok, tot = m.score()
    kp = [[Paragraph(f"<b>{lab}</b><br/><font size=13 color='#0f9d6a'><b>{val}</b></font>", B) for lab, val in row] for row in [
        [("Revenue", money(L["Revenue"])), ("EBITDA margin", pct(L["EBITDA Margin %"])), ("Net profit", money(L["PAT"])), ("Health score", f"{ok}/{tot}")],
        [("ROE", pct(L.get("ROE %"))), ("ROCE", pct(L.get("ROCE %"))), ("Debt / equity", f"{L.get('Debt / Equity', np.nan):.2f}x"), ("Free cash flow", money(L.get("FCF")))],
    ]]
    t = Table(kp, colWidths=[44 * mm] * 4)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfdad3")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e8e3")),
                           ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f9f7")), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    S.append(t)
    imgs = _mpl_charts(m, proj)
    for key in ("rev_pat", "margins"):
        if key in imgs:
            S.append(Spacer(1, 4)); S.append(Image(io.BytesIO(imgs[key]), width=170 * mm, height=170 * mm * 0.43 if key == "rev_pat" else 170 * mm * 0.4))

    ps = None
    if proj is not None:
        pl = proj.pl
        ps = {"revenue_end": pl.loc["Revenue", proj.labels[-1]], "pat_end": pl.loc["PAT", proj.labels[-1]], "end_label": proj.labels[-1],
              "rev_cagr": ((pl.loc["Revenue", proj.labels[-1]] / pl.loc["Revenue", proj.base_label]) ** (1 / len(proj.labels)) - 1) * 100}
        if dcf and "per_share" in dcf:
            ps.update(value_ps=dcf["per_share"], price=dcf.get("price"))
    S.append(PageBreak())
    S.append(Paragraph("Case study", H1))
    for sec in build_case_study(m, co.name, report, ps):
        block = [Paragraph(sec["title"], H2)]
        for para in sec.get("body", []):
            block.append(Paragraph(para, B)); block.append(Spacer(1, 3))
        for bl in sec.get("bullets", []):
            block.append(Paragraph(bl, BU, bulletText="•"))
        if sec.get("strengths"):
            block.append(Paragraph("<b>Strengths</b>", B))
            block += [Paragraph(x, BU, bulletText="•") for x in sec["strengths"]]
        if sec.get("watch"):
            block.append(Paragraph("<b>Watch-outs</b>", B))
            block += [Paragraph(x, BU, bulletText="•") for x in sec["watch"]]
        for th, sents in (sec.get("themes") or {}).items():
            block.append(Paragraph(f"<b>{th}</b>", B))
            block += [Paragraph(x, BU, bulletText="•") for x in sents]
        S.append(KeepTogether(block))
        if sec["title"].startswith("Profitability") and "mix" in imgs:
            S.append(Image(io.BytesIO(imgs["mix"]), width=170 * mm, height=170 * mm * 0.43))
        if sec["title"].startswith("Cash flow") and "cash" in imgs:
            S.append(Image(io.BytesIO(imgs["cash"]), width=170 * mm, height=170 * mm * 0.4))

    def tbl(df: pd.DataFrame, title: str, ncols: int = 6, d=1):
        df = df.iloc[:, -ncols:]
        data = [[title] + list(df.columns)]
        for idx in df.index:
            data.append([str(idx)] + ["" if pd.isna(v) else f"{v:,.{d}f}" for v in df.loc[idx]])
        tb = Table(data, repeatRows=1, colWidths=[52 * mm] + [(178 - 52) / max(len(df.columns), 1) * mm] * len(df.columns))
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("FONTNAME", (0, 0), (-1, -1), base_font),
                                ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d4ddd8")),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f9f7")])]))
        return tb

    S.append(PageBreak())
    S.append(Paragraph("Financial statements", H1))
    for ttl, df in co.tables().items():
        if not df.empty:
            S.append(Paragraph(ttl, H2)); S.append(tbl(df, ttl))
    ratio_cols = ["Revenue Growth %", "EBITDA Margin %", "Net Margin %", "ROE %", "ROCE %", "Debt / Equity", "Interest Coverage",
                  "Receivable Days", "Inventory Days", "CFO / PAT", "Dividend Payout %", "EPS"]
    S.append(Paragraph("Key ratios", H2))
    S.append(tbl(m.df[ratio_cols].T, "Ratio"))
    if proj is not None:
        S.append(PageBreak())
        S.append(Paragraph("Projection and valuation", H1))
        if "proj" in imgs:
            S.append(Image(io.BytesIO(imgs["proj"]), width=170 * mm, height=170 * mm * 0.4))
        S.append(Paragraph("Projected P&L", H2)); S.append(tbl(proj.pl, "₹ Cr", ncols=6))
        S.append(Paragraph("Projected cash flow", H2)); S.append(tbl(proj.cf, "₹ Cr", ncols=6))
        if dcf and "per_share" in dcf:
            S.append(Paragraph("DCF summary", H2))
            rows = [["WACC / terminal growth", f"{dcf['wacc']:.1f}% / {dcf['g']:.1f}%"], ["Enterprise value", money(dcf["ev"])],
                    ["Equity value", money(dcf["equity"])], ["Value per share", f"₹{dcf['per_share']:,.0f}"],
                    ["Current price", f"₹{dcf['price']:,.0f}" if dcf.get("price") else "n/a"],
                    ["Upside / (downside)", pct(dcf.get("upside"), sign=True)], ["Terminal value share of EV", pct(dcf["tv_share"])]]
            tb = Table(rows, colWidths=[70 * mm, 50 * mm])
            tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d4ddd8")), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("FONTNAME", (0, 0), (-1, -1), base_font),
                                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f6f9f7"))]))
            S.append(tb)
    S.append(Spacer(1, 10))
    S.append(Paragraph("Disclaimer: auto-generated from the data supplied. Figures extracted from PDFs/screenshots may contain errors; projections are "
                       "mechanical extrapolations. This is not investment advice.", SM))
    if fonts is None:
        _swap_rupee(S)
    doc.build(S)
    return buf.getvalue()


def _swap_rupee(story):
    """No TTF with ₹ found: replace the glyph with 'Rs.' so nothing renders as a box."""
    from reportlab.platypus import Paragraph, Table, KeepTogether
    def fix(o):
        if isinstance(o, Paragraph):
            o.text = o.text.replace("₹", "Rs. ")
            o.__init__(o.text, o.style, bulletText=getattr(o, "bulletText", None))
        elif isinstance(o, Table):
            for r in o._cellvalues:
                for i, c in enumerate(r):
                    if isinstance(c, str):
                        r[i] = c.replace("₹", "Rs. ")
                    else:
                        fix(c)
        elif isinstance(o, KeepTogether):
            for c in o._content:
                fix(c)
    for o in story:
        fix(o)


def figs_to_html(title: str, figs: list[tuple[str, object]], dark: bool = True) -> bytes:
    """Bundle Plotly figures into one standalone HTML dashboard."""
    bg, fg, card = ("#050806", "#eef3f0", "#0e1311") if dark else ("#f3f6f4", "#0d1512", "#ffffff")
    parts = [f"<html><head><meta charset='utf-8'><title>{title}</title><style>body{{background:{bg};color:{fg};font-family:Inter,Segoe UI,sans-serif;margin:0;padding:24px}}"
             f".grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:16px}}.card{{background:{card};border:1px solid rgba(128,128,128,.2);border-radius:16px;padding:12px}}"
             f"h1{{margin:0 0 16px}}h3{{margin:4px 8px;font-weight:600}}</style></head><body><h1>{title}</h1><div class='grid'>"]
    for i, (name, fig) in enumerate(figs):
        parts.append(f"<div class='card'><h3>{name}</h3>{fig.to_html(full_html=False, include_plotlyjs='cdn' if i == 0 else False)}</div>")
    parts.append("</div></body></html>")
    return "".join(parts).encode("utf-8")
