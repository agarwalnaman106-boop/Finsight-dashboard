"""Automatic 3-statement projection, scenarios and DCF built from a Metrics object."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, replace
import re

import numpy as np
import pandas as pd

from .analytics import Metrics, cagr

SCENARIOS = {  # (revenue growth delta in pp, EBITDA margin delta in pp)
    "Bear": (-4.0, -2.0),
    "Base": (0.0, 0.0),
    "Bull": (4.0, 1.5),
}


@dataclass
class Assumptions:
    n_years: int = 5
    rev_growth: list = field(default_factory=list)       # % per projected year
    ebitda_margin: list = field(default_factory=list)    # % per projected year
    other_income_pct: float = 1.0                        # % of sales
    dep_pct_opening_block: float = 7.0                   # % of opening net block
    interest_rate: float = 9.0                           # % on opening debt
    tax_rate: float = 25.0
    capex_pct_sales: float = 5.0
    recv_days: float = 60.0
    inv_days: float = 60.0
    other_liab_pct_sales: float = 10.0
    resid_assets_pct_sales: float = 3.0
    payout_pct: float = 20.0
    debt_change_pct: list = field(default_factory=list)  # % change in debt per year
    min_cash: float = 0.0
    minority_pct: float = 0.0                            # % of profit after tax that goes to minorities / others

    def to_dict(self):
        return asdict(self)


def next_labels(last: str, n: int) -> list[str]:
    m = re.match(r"FY(\d{2})$", str(last))
    if m:
        y = int(m[1])
        return [f"FY{(y + i) % 100:02d}E" for i in range(1, n + 1)]
    return [f"Y+{i}" for i in range(1, n + 1)]


def _clip(x, lo, hi, default):
    if x is None or pd.isna(x):
        return default
    return float(min(max(x, lo), hi))


def default_assumptions(m: Metrics, n_years: int = 5) -> Assumptions:
    df = m.df.dropna(subset=["Revenue"])
    L = m.latest
    c3 = cagr(df["Revenue"], 3) * 100 if len(df) > 3 else np.nan
    c5 = cagr(df["Revenue"], 5) * 100 if len(df) > 5 else np.nan
    last_g = L.get("Revenue Growth %", np.nan)
    anchors = [v for v in (c3, c5, last_g) if v is not None and not pd.isna(v)]
    start = _clip(np.mean(anchors) if anchors else 10.0, 3, 22, 10.0)
    end = max(min(start, 9.0), 6.0)
    growth = list(np.round(np.linspace(start, end, n_years), 1))
    mar = df["EBITDA Margin %"].dropna().tail(3)
    margin0 = float(mar.mean()) if len(mar) else 15.0
    margin = [round(margin0, 1)] * n_years
    nb_open = df["Net Block"].shift(1).iloc[-1] if "Net Block" in df and len(df) > 1 else np.nan
    dep_pct = _clip(L["Depreciation"] / nb_open * 100 if pd.notna(nb_open) and nb_open else np.nan, 1, 25, 7.0)
    debt_open = df["Debt"].shift(1).iloc[-1] if len(df) > 1 else np.nan
    rate = _clip(L["Interest"] / debt_open * 100 if pd.notna(debt_open) and debt_open else np.nan, 2, 18, 9.0)
    tax = _clip(L.get("Tax Rate %"), 10, 40, 25.0)
    capex = df["Capex % Sales"].dropna().tail(3)
    capex_pct = _clip(capex.mean() if len(capex) else np.nan, 0.5, 25, 5.0)
    oi = _clip(L["Other Income"] / L["Revenue"] * 100 if L["Revenue"] else np.nan, 0, 10, 1.0)
    pay = df["Dividend Payout %"].dropna().tail(3)
    mn = df["Minority share %"].dropna().tail(3) if "Minority share %" in df else []
    minority = _clip(float(np.mean(mn)) if len(mn) else np.nan, 0, 50, 0.0)
    return Assumptions(
        minority_pct=round(minority, 1),
        n_years=n_years, rev_growth=growth, ebitda_margin=margin, other_income_pct=round(oi, 1),
        dep_pct_opening_block=round(dep_pct, 1), interest_rate=round(rate, 1), tax_rate=round(tax, 1),
        capex_pct_sales=round(capex_pct, 1),
        recv_days=round(_clip(L.get("Receivable Days"), 0, 300, 60), 0),
        inv_days=round(_clip(L.get("Inventory Days"), 0, 300, 60), 0),
        other_liab_pct_sales=round(_clip(L["Other Liabilities"] / L["Revenue"] * 100 if L["Revenue"] else np.nan, 0, 60, 10), 1),
        resid_assets_pct_sales=round(_clip(L["Other Current/Misc Assets"] / L["Revenue"] * 100 if L["Revenue"] else np.nan, 0, 60, 3), 1),
        payout_pct=round(_clip(pay.mean() if len(pay) else np.nan, 0, 90, 20), 0),
        debt_change_pct=[0.0] * n_years,
    )


@dataclass
class Projection:
    labels: list
    base_label: str
    pl: pd.DataFrame
    bs: pd.DataFrame
    cf: pd.DataFrame
    ratios: pd.DataFrame
    notes: list
    assumptions: Assumptions


def project(m: Metrics, A: Assumptions, scenario: str = "Base") -> Projection:
    gd, md = SCENARIOS.get(scenario, (0.0, 0.0))
    n = A.n_years
    growth = (list(A.rev_growth) + [A.rev_growth[-1]] * n)[:n]
    margin = (list(A.ebitda_margin) + [A.ebitda_margin[-1]] * n)[:n]
    dchg = (list(A.debt_change_pct) + [0.0] * n)[:n]
    L = m.latest
    base = m.latest_period
    labels = next_labels(base, n)
    notes: list[str] = []

    def val(k, default=0.0):
        v = L.get(k, np.nan)
        return default if pd.isna(v) else float(v)

    sales0 = val("Revenue")
    eq_cap, res = val("Share Capital"), val("Reserves")
    if pd.isna(L.get("Share Capital")) and pd.isna(L.get("Reserves")):
        res = val("Equity")
    debt, ol = val("Debt"), val("Other Liabilities")
    nb, cwip, inv_ = val("Net Block"), val("CWIP"), val("Investments")
    recv, inven, cash = val("Receivables"), val("Inventory"), val("Cash")
    tl = eq_cap + res + debt + ol
    resid = tl - (nb + cwip + inv_ + recv + inven + cash)
    if abs(resid - val("Other Current/Misc Assets")) > 0.02 * max(tl, 1):
        notes.append("Base-year balance sheet did not reconcile exactly; the difference was absorbed in 'Other assets'.")
    shares = val("Shares (Cr)", np.nan)
    res0 = res
    ol_core, cum_min = ol, 0.0     # minority interest sits inside Other Liabilities; track the core part separately

    rows = {k: [] for k in ["Revenue", "EBITDA", "Other Income", "Depreciation", "Interest", "PBT", "Tax", "Minority & others", "PAT",
                            "Dividend", "EPS",
                            "Share Capital", "Reserves", "Debt", "Other Liabilities", "Total Liabilities",
                            "Net Block", "CWIP", "Investments", "Receivables", "Inventory", "Other Assets (misc.)",
                            "Cash", "Total Assets", "Check (L - A)",
                            "CFO", "Capex", "CFI", "CFF", "Net Cash Flow", "FCF", "ΔNWC", "Revolver draw"]}
    s_prev = sales0
    for t in range(n):
        g = (growth[t] + gd) / 100
        mg = (margin[t] + md) / 100
        sales = s_prev * (1 + g)
        ebitda = sales * mg
        oi = sales * A.other_income_pct / 100
        dep = nb * A.dep_pct_opening_block / 100
        intr = debt * A.interest_rate / 100
        pbt = ebitda + oi - dep - intr
        tax = max(pbt, 0) * A.tax_rate / 100
        pat_total = pbt - tax
        mino = max(pat_total, 0) * A.minority_pct / 100
        pat = pat_total - mino                      # attributable to owners
        div = max(pat, 0) * A.payout_pct / 100
        capex = sales * A.capex_pct_sales / 100
        nb_new = max(nb + capex - dep, 0)
        recv_n = sales * A.recv_days / 365
        inv_n = sales * A.inv_days / 365
        ol_core_n = sales * A.other_liab_pct_sales / 100
        cum_min += mino
        ol_n = ol_core_n + cum_min
        resid_n = sales * A.resid_assets_pct_sales / 100
        d_wc = (recv_n + inv_n + resid_n) - (recv + inven + resid) - (ol_core_n - ol_core)
        debt_plan = max(debt * (1 + dchg[t] / 100), 0)
        cfo = pat_total + dep - d_wc
        cfi = -capex
        cff = (debt_plan - debt) - div
        cash_new = cash + cfo + cfi + cff
        draw = 0.0
        if cash_new < A.min_cash:
            draw = A.min_cash - cash_new
            cash_new = A.min_cash
            cff += draw
            notes.append(f"{labels[t]}: cash shortfall of {draw:,.0f} funded by additional borrowing.")
        debt_new = debt_plan + draw
        res_new = res + pat - div
        tl_n = eq_cap + res_new + debt_new + ol_n
        ta_n = nb_new + cwip + inv_ + recv_n + inv_n + resid_n + cash_new
        vals = dict(Revenue=sales, EBITDA=ebitda, **{"Other Income": oi}, Depreciation=dep, Interest=intr, PBT=pbt, Tax=tax, **{"Minority & others": mino},
                    PAT=pat, Dividend=div, EPS=(pat / shares if shares and not pd.isna(shares) else np.nan),
                    **{"Share Capital": eq_cap}, Reserves=res_new, Debt=debt_new, **{"Other Liabilities": ol_n},
                    **{"Total Liabilities": tl_n}, **{"Net Block": nb_new}, CWIP=cwip, Investments=inv_,
                    Receivables=recv_n, Inventory=inv_n, **{"Other Assets (misc.)": resid_n}, Cash=cash_new,
                    **{"Total Assets": ta_n}, **{"Check (L - A)": tl_n - ta_n}, CFO=cfo, Capex=capex, CFI=cfi, CFF=cff,
                    **{"Net Cash Flow": cfo + cfi + cff}, FCF=cfo - capex, **{"ΔNWC": d_wc}, **{"Revolver draw": draw})
        for k, v in vals.items():
            rows[k].append(v)
        s_prev, nb, debt, ol, res, cash = sales, nb_new, debt_new, ol_n, res_new, cash_new
        ol_core = ol_core_n
        recv, inven, resid = recv_n, inv_n, resid_n

    # base-year (actual) column for context
    base_vals = dict(Revenue=sales0, EBITDA=val("EBITDA"), **{"Other Income": val("Other Income")},
                     Depreciation=val("Depreciation"), Interest=val("Interest"), PBT=val("PBT"), Tax=val("Tax"), **{"Minority & others": val("Minority & others")},
                     PAT=val("PAT"), Dividend=val("Dividend"), EPS=val("EPS", np.nan),
                     **{"Share Capital": eq_cap}, Reserves=res0, Debt=val("Debt"),
                     **{"Other Liabilities": val("Other Liabilities")}, **{"Total Liabilities": tl},
                     **{"Net Block": val("Net Block")}, CWIP=val("CWIP"), Investments=val("Investments"),
                     Receivables=val("Receivables"), Inventory=val("Inventory"), **{"Other Assets (misc.)": resid_base_value(L, tl)},
                     Cash=val("Cash"), **{"Total Assets": tl}, **{"Check (L - A)": 0.0}, CFO=val("CFO"), Capex=val("Capex", np.nan),
                     CFI=val("CFI"), CFF=val("CFF"), **{"Net Cash Flow": val("Net Cash Flow")}, FCF=val("FCF", np.nan),
                     **{"ΔNWC": np.nan}, **{"Revolver draw": 0.0})
    all_cols = [base + " (A)"] + labels
    full = pd.DataFrame({k: [base_vals[k]] + rows[k] for k in rows}, index=all_cols).T
    pl = full.loc[["Revenue", "EBITDA", "Other Income", "Depreciation", "Interest", "PBT", "Tax", "Minority & others", "PAT", "Dividend", "EPS"]]
    bs = full.loc[["Share Capital", "Reserves", "Debt", "Other Liabilities", "Total Liabilities", "Net Block", "CWIP",
                   "Investments", "Receivables", "Inventory", "Other Assets (misc.)", "Cash", "Total Assets", "Check (L - A)"]]
    cf = full.loc[["CFO", "Capex", "CFI", "CFF", "Net Cash Flow", "FCF", "ΔNWC", "Revolver draw"]]

    rt = pd.DataFrame(index=all_cols)
    rt["Revenue Growth %"] = full.loc["Revenue"].pct_change() * 100
    rt["EBITDA Margin %"] = full.loc["EBITDA"] / full.loc["Revenue"] * 100
    rt["Net Margin %"] = full.loc["PAT"] / full.loc["Revenue"] * 100
    eq = full.loc["Share Capital"] + full.loc["Reserves"]
    ce = eq + full.loc["Debt"]
    rt["ROE %"] = full.loc["PAT"] / ((eq + eq.shift(1)) / 2) * 100
    rt["ROCE %"] = (full.loc["PBT"] + full.loc["Interest"]) / ((ce + ce.shift(1)) / 2) * 100
    rt["Debt / Equity"] = full.loc["Debt"] / eq
    rt["Net Debt"] = full.loc["Debt"] - full.loc["Cash"]
    rt["Interest Coverage"] = (full.loc["EBITDA"] - full.loc["Depreciation"] + full.loc["Other Income"]) / full.loc["Interest"].replace(0, np.nan)
    rt["EPS"] = full.loc["EPS"]
    rt.iloc[0, rt.columns.get_indexer(["ROE %", "ROCE %"])] = [val("ROE %", np.nan), val("ROCE %", np.nan)]
    rt.iloc[0, rt.columns.get_loc("Revenue Growth %")] = val("Revenue Growth %", np.nan)
    rt = rt.T
    return Projection(labels=labels, base_label=base + " (A)", pl=pl, bs=bs, cf=cf, ratios=rt,
                      notes=list(dict.fromkeys(notes)), assumptions=A)


def resid_base_value(L: pd.Series, tl: float) -> float:
    g = lambda k: 0.0 if pd.isna(L.get(k)) else float(L.get(k))  # noqa: E731
    return tl - (g("Net Block") + g("CWIP") + g("Investments") + g("Receivables") + g("Inventory") + g("Cash"))


# ----------------------------------------------------------------------------
# DCF
# ----------------------------------------------------------------------------
@dataclass
class DCFInputs:
    wacc: float = 12.0          # %
    terminal_growth: float = 5.0  # %
    mid_year: bool = False
    include_investments: bool = True
    current_price: float | None = None
    shares: float | None = None   # Cr; used only when the data has no share count


def wacc_capm(rf: float, beta: float, erp: float, kd: float, tax: float, w_debt: float) -> dict:
    ke = rf + beta * erp
    kd_at = kd * (1 - tax / 100)
    w = ke * (1 - w_debt) + kd_at * w_debt
    return {"cost_of_equity": ke, "cost_of_debt_after_tax": kd_at, "wacc": w}


def fcff_table(proj: Projection) -> pd.DataFrame:
    A = proj.assumptions
    cols = proj.labels
    pl, cf = proj.pl[cols], proj.cf[cols]
    ebit = pl.loc["EBITDA"] - pl.loc["Depreciation"]
    nopat = ebit * (1 - A.tax_rate / 100)
    t = pd.DataFrame({
        "EBIT": ebit, "NOPAT": nopat, "Depreciation": pl.loc["Depreciation"], "Capex": -cf.loc["Capex"],
        "Change in NWC": -cf.loc["ΔNWC"],
    }).T
    t.loc["FCFF"] = t.loc["NOPAT"] + t.loc["Depreciation"] + t.loc["Capex"] + t.loc["Change in NWC"]
    return t


def run_dcf(m: Metrics, proj: Projection, inp: DCFInputs) -> dict:
    t = fcff_table(proj)
    f = t.loc["FCFF"].values.astype(float)
    n = len(f)
    w, g = inp.wacc / 100, inp.terminal_growth / 100
    if w <= g:
        return {"error": "WACC must be higher than the terminal growth rate."}
    shift = 0.5 if inp.mid_year else 0.0
    disc = np.array([(1 + w) ** -(i + 1 - shift) for i in range(n)])
    pv = f * disc
    tv = f[-1] * (1 + g) / (w - g)
    pv_tv = tv * (1 + w) ** -(n - shift if inp.mid_year else n)
    ev = pv.sum() + pv_tv
    L = m.latest
    debt = 0.0 if pd.isna(L.get("Debt")) else float(L["Debt"])
    cash = 0.0 if pd.isna(L.get("Cash")) else float(L["Cash"])
    invs = 0.0 if (pd.isna(L.get("Investments")) or not inp.include_investments) else float(L["Investments"])
    equity_all = ev - debt + cash + invs
    mpct = float(getattr(proj.assumptions, 'minority_pct', 0.0) or 0.0)
    minority_val = max(equity_all, 0) * mpct / 100
    equity = equity_all - minority_val
    shares = L.get("Shares (Cr)")
    if (shares is None or pd.isna(shares)) and inp.shares:
        shares = inp.shares
    ps = equity / shares if shares and not pd.isna(shares) else np.nan
    price = inp.current_price if inp.current_price else L.get("Price")
    upside = (ps / price - 1) * 100 if price and not pd.isna(price) and not pd.isna(ps) else np.nan
    ebitda_n = proj.pl.loc["EBITDA", proj.labels[-1]]
    return {
        "fcff": t, "pv": pv, "tv": tv, "pv_tv": pv_tv, "ev": ev, "debt": debt, "cash": cash, "investments": invs,
        "equity": equity, "minority": minority_val, "per_share": ps, "price": price, "upside": upside, "tv_share": pv_tv / ev * 100 if ev else np.nan,
        "implied_exit_multiple": tv / ebitda_n if ebitda_n else np.nan, "labels": proj.labels,
        "wacc": inp.wacc, "g": inp.terminal_growth,
    }


def sensitivity(m: Metrics, proj: Projection, inp: DCFInputs, w_step=1.0, g_step=0.5, k=2) -> pd.DataFrame:
    ws = [inp.wacc + w_step * i for i in range(-k, k + 1)]
    gs = [inp.terminal_growth + g_step * i for i in range(-k, k + 1)]
    grid = pd.DataFrame(index=[f"{w:.1f}%" for w in ws], columns=[f"{g:.1f}%" for g in gs], dtype=float)
    for w in ws:
        for g in gs:
            r = run_dcf(m, proj, replace(inp, wacc=w, terminal_growth=g))
            grid.loc[f"{w:.1f}%", f"{g:.1f}%"] = r.get("per_share", np.nan) if "error" not in r else np.nan
    grid.index.name = "WACC ↓ / g →"
    return grid


def scenario_summary(m: Metrics, A: Assumptions, inp: DCFInputs) -> pd.DataFrame:
    out = {}
    for sc in SCENARIOS:
        p = project(m, A, sc)
        r = run_dcf(m, p, inp)
        last = p.labels[-1]
        out[sc] = {
            f"Revenue {last}": p.pl.loc["Revenue", last],
            f"EBITDA {last}": p.pl.loc["EBITDA", last],
            f"PAT {last}": p.pl.loc["PAT", last],
            "Revenue CAGR %": ((p.pl.loc["Revenue", last] / p.pl.loc["Revenue", p.base_label]) ** (1 / len(p.labels)) - 1) * 100,
            "EV": r.get("ev", np.nan), "Equity value": r.get("equity", np.nan),
            "Value / share": r.get("per_share", np.nan), "Upside %": r.get("upside", np.nan),
        }
    return pd.DataFrame(out)
