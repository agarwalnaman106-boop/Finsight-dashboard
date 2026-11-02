"""KPI + ratio engine. Everything is computed from a Company (rows=items, cols=periods)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .parsers import Company, period_sort_key


def _row(df: pd.DataFrame, item: str, idx: list) -> pd.Series:
    if df is None or df.empty or item not in df.index:
        return pd.Series(np.nan, index=idx, dtype=float)
    return df.loc[item].reindex(idx).astype(float)


def _div(a: pd.Series, b: pd.Series) -> pd.Series:
    b = b.replace(0, np.nan)
    return a / b


def cagr(series: pd.Series, years: int) -> float:
    s = series.dropna()
    if len(s) <= years:
        return np.nan
    start, end = s.iloc[-years - 1], s.iloc[-1]
    if start is None or start <= 0 or end <= 0:
        return np.nan
    return (end / start) ** (1 / years) - 1


class Metrics:
    """Holds the per-period metric table `df` (index = periods)."""

    def __init__(self, co: Company):
        self.co = co
        self.idx = [p for p in co.periods]
        self.idx = sorted(self.idx, key=period_sort_key)
        self.df = self._build()

    # ------------------------------------------------------------------
    def _build(self) -> pd.DataFrame:
        co, idx = self.co, self.idx
        pl, bs, cf = co.pl, co.bs, co.cf
        m = pd.DataFrame(index=idx)
        g = lambda df, k: _row(df, k, idx)  # noqa: E731

        sales = g(pl, "Sales")
        other_inc = g(pl, "Other Income").fillna(0)
        dep = g(pl, "Depreciation").fillna(0)
        intr = g(pl, "Interest").fillna(0)
        pbt = g(pl, "Profit before tax")
        tax = g(pl, "Tax")
        pat = g(pl, "Net profit")
        div = g(pl, "Dividend Amount")
        div = div if div.isna().all() else div.fillna(0)

        exp_items = ["Raw Material Cost", "Change in Inventory", "Power and Fuel", "Other Mfr. Exp",
                     "Employee Cost", "Selling and admin", "Other Expenses"]
        exp_frame = pd.DataFrame({k: g(pl, k) for k in exp_items})
        total_exp = exp_frame.sum(axis=1, min_count=1)
        if pbt.notna().any():
            ebitda = pbt + intr + dep - other_inc
            # prefer explicit expense build when it reconciles (Screener-style)
            ebitda_b = sales - total_exp
            ebitda = ebitda.where(ebitda.notna(), ebitda_b)
        else:
            ebitda = sales - total_exp
            pbt = ebitda + other_inc - dep - intr
        if pat.isna().all() and pbt.notna().any():
            pat = pbt - tax.fillna(0)
        if tax.isna().all() and pbt.notna().any() and pat.notna().any():
            tax = pbt - pat
        m["Revenue"] = sales
        m["Other Income"] = other_inc
        m["Operating Expenses"] = sales - ebitda
        m["EBITDA"] = ebitda
        m["Depreciation"] = dep
        m["EBIT"] = ebitda - dep
        m["Interest"] = intr
        m["PBT"] = pbt
        m["Tax"] = tax
        m["PAT"] = pat
        m["Dividend"] = div
        for k in exp_items:
            m[k] = exp_frame[k]

        # ---- balance sheet ----
        eq_cap = g(bs, "Equity Share Capital")
        res = g(bs, "Reserves")
        equity = eq_cap.fillna(0) + res.fillna(0)
        equity = equity.where(eq_cap.notna() | res.notna())
        debt = g(bs, "Borrowings")
        oth_liab = g(bs, "Other Liabilities")
        nb, cwip, inv_ = g(bs, "Net Block"), g(bs, "Capital Work in Progress"), g(bs, "Investments")
        oth_assets = g(bs, "Other Assets")
        recv, inven, cash = g(bs, "Receivables"), g(bs, "Inventory"), g(bs, "Cash & Bank")
        tot_a = g(bs, "Total Assets")
        tot_l = g(bs, "Total Liabilities")
        tot_a = tot_a.where(tot_a.notna(), tot_l)
        built = nb.fillna(0) + cwip.fillna(0) + inv_.fillna(0) + oth_assets.fillna(0)
        tot_a = tot_a.where(tot_a.notna(), built.where(built > 0))
        m["Equity"] = equity
        m["Share Capital"] = eq_cap
        m["Reserves"] = res
        m["Debt"] = debt
        m["Other Liabilities"] = oth_liab
        m["Net Block"] = nb
        m["CWIP"] = cwip
        m["Investments"] = inv_
        m["Other Assets"] = oth_assets
        m["Receivables"] = recv
        m["Inventory"] = inven
        m["Cash"] = cash
        m["Total Assets"] = tot_a
        m["Capital Employed"] = equity + debt.fillna(0)
        m["Net Debt"] = debt.fillna(0) - cash.fillna(0)
        resid = oth_assets - recv.fillna(0) - inven.fillna(0) - cash.fillna(0)
        m["Other Current/Misc Assets"] = resid

        # ---- cash flow ----
        m["CFO"] = g(cf, "Cash from Operating Activity")
        m["CFI"] = g(cf, "Cash from Investing Activity")
        m["CFF"] = g(cf, "Cash from Financing Activity")
        m["Net Cash Flow"] = g(cf, "Net Cash Flow")
        if m["Net Cash Flow"].isna().all() and m["CFO"].notna().any():
            m["Net Cash Flow"] = m[["CFO", "CFI", "CFF"]].sum(axis=1, min_count=1)
        # capex estimate from net block movement
        fixed = nb.fillna(0) + cwip.fillna(0)
        capex = (fixed - fixed.shift(1) + dep).where(nb.notna())
        capex = capex.where(capex > 0, np.nan)
        m["Capex"] = capex
        m["FCF"] = m["CFO"] - capex
        m["FCF"] = m["FCF"].where(m["FCF"].notna(), m["CFO"] + m["CFI"])

        # ---- shares / per-share ----
        shares = g(bs, "No. of Equity Shares")
        adj = co.meta.get("adj_shares_series") or {}
        if adj:
            shares = shares.where(shares.notna(), pd.Series(adj).reindex(idx))
        if shares.isna().all() and co.meta.get("shares_cr"):
            shares = pd.Series(co.meta["shares_cr"], index=idx, dtype=float)
        shares = shares.ffill().bfill()
        m["Shares (Cr)"] = shares
        m["EPS"] = _div(pat, shares)
        m["BVPS"] = _div(equity, shares)
        m["DPS"] = _div(div, shares)

        # ---- growth ----
        for k, name in [("Revenue", "Revenue Growth %"), ("EBITDA", "EBITDA Growth %"), ("PAT", "PAT Growth %"),
                        ("EPS", "EPS Growth %")]:
            prev = m[k].shift(1)
            m[name] = ((m[k] - prev) / prev.abs().replace(0, np.nan) * 100).where(prev > 0)

        # ---- margins ----
        m["EBITDA Margin %"] = _div(m["EBITDA"], sales) * 100
        m["EBIT Margin %"] = _div(m["EBIT"], sales) * 100
        m["PBT Margin %"] = _div(pbt, sales) * 100
        m["Net Margin %"] = _div(pat, sales) * 100
        m["Tax Rate %"] = _div(tax, pbt) * 100

        # ---- returns ----
        avg = lambda s: ((s + s.shift(1)) / 2).where(s.shift(1).notna(), s)  # noqa: E731
        avg_eq, avg_ce, avg_ta = avg(equity), avg(m["Capital Employed"]), avg(tot_a)
        m["ROE %"] = _div(pat, avg_eq) * 100
        m["ROCE %"] = _div(pbt + intr, avg_ce) * 100
        m["ROA %"] = _div(pat, avg_ta) * 100
        m["ROIC %"] = _div(m["EBIT"] * (1 - (m["Tax Rate %"].clip(0, 50).fillna(25) / 100)), avg_ce) * 100

        # ---- leverage / coverage ----
        m["Debt / Equity"] = _div(debt, equity)
        m["Net Debt / EBITDA"] = _div(m["Net Debt"], ebitda)
        m["Interest Coverage"] = _div(m["EBIT"] + other_inc, intr)
        m["Equity Multiplier"] = _div(avg_ta, avg_eq)
        m["Asset Turnover"] = _div(sales, avg_ta)
        m["Liabilities / Assets %"] = _div(tot_a - equity, tot_a) * 100

        # ---- working capital ----
        m["Receivable Days"] = _div(recv, sales) * 365
        m["Inventory Days"] = _div(inven, sales) * 365
        m["Other Liab. Days"] = _div(oth_liab, sales) * 365
        m["NWC"] = recv.fillna(0) + inven.fillna(0) - oth_liab.fillna(0)
        m["NWC % Sales"] = _div(m["NWC"], sales) * 100
        m["Working Capital Days"] = m["Receivable Days"].fillna(0) + m["Inventory Days"].fillna(0) - m["Other Liab. Days"].fillna(0)

        # ---- cash quality / allocation ----
        m["CFO / PAT"] = _div(m["CFO"], pat)
        m["CFO / EBITDA"] = _div(m["CFO"], ebitda)
        m["FCF Margin %"] = _div(m["FCF"], sales) * 100
        m["Capex % Sales"] = _div(capex, sales) * 100
        m["Dividend Payout %"] = _div(div, pat) * 100
        m["Cost % Sales"] = _div(m["Operating Expenses"], sales) * 100

        # ---- valuation (latest only meaningful; per-year price if available) ----
        price = co.price.reindex(idx) if not co.price.empty else pd.Series(np.nan, index=idx)
        if co.meta.get("current_price") and len(idx):
            price = price.copy()
            price.iloc[-1] = co.meta["current_price"]
        m["Price"] = price
        m["P/E"] = _div(price, m["EPS"])
        m["P/B"] = _div(price, m["BVPS"])
        m["Market Cap"] = price * shares
        m["EV"] = m["Market Cap"] + m["Net Debt"]
        m["EV/EBITDA"] = _div(m["EV"], ebitda)
        m["Earnings Yield %"] = _div(m["EPS"], price) * 100
        m["Dividend Yield %"] = _div(m["DPS"], price) * 100
        m["Price/Sales"] = _div(m["Market Cap"], sales)

        # ---- DuPont ----
        m["DuPont: Net Margin %"] = m["Net Margin %"]
        m["DuPont: Asset Turnover"] = m["Asset Turnover"]
        m["DuPont: Equity Multiplier"] = m["Equity Multiplier"]
        return m

    # ------------------------------------------------------------------
    @property
    def latest(self) -> pd.Series:
        valid = self.df.dropna(how="all", subset=["Revenue", "PAT"])
        return valid.iloc[-1] if len(valid) else self.df.iloc[-1]

    @property
    def prev(self) -> pd.Series | None:
        valid = self.df.dropna(how="all", subset=["Revenue", "PAT"])
        return valid.iloc[-2] if len(valid) > 1 else None

    @property
    def latest_period(self) -> str:
        return self.latest.name

    @property
    def prev_period(self) -> str | None:
        return self.prev.name if self.prev is not None else None

    def delta(self, col: str, as_pct: bool = True):
        """YoY change of a metric: % change (values) or absolute change (ratios in %)."""
        cur, prev = self.latest.get(col), (self.prev.get(col) if self.prev is not None else np.nan)
        if pd.isna(cur) or pd.isna(prev):
            return np.nan
        if as_pct:
            return (cur - prev) / abs(prev) * 100 if prev else np.nan
        return cur - prev

    def cagr(self, col: str, years: int) -> float:
        return cagr(self.df[col], years) * 100

    def cost_structure(self, period: str | None = None) -> pd.Series:
        p = period or self.latest_period
        items = ["Raw Material Cost", "Change in Inventory", "Power and Fuel", "Other Mfr. Exp",
                 "Employee Cost", "Selling and admin", "Other Expenses"]
        s = self.df.loc[p, items].astype(float)
        s = s[s.abs() > 0].dropna()
        s["Change in Inventory"] = s.get("Change in Inventory", np.nan)
        s = s.dropna()
        return s[s > 0]

    def scorecard(self) -> list[dict]:
        """Eight transparent health checks -> pass/fail with the underlying number."""
        L = self.latest
        P = self.prev
        checks = []

        def add(name, ok, detail):
            checks.append({"check": name, "pass": None if ok is None else bool(ok), "detail": detail})

        add("Revenue is growing", None if pd.isna(L.get("Revenue Growth %")) else L["Revenue Growth %"] > 0,
            f"{L.get('Revenue Growth %', np.nan):.1f}% YoY")
        if P is not None:
            d = L.get("EBITDA Margin %", np.nan) - P.get("EBITDA Margin %", np.nan)
            add("EBITDA margin held or improved", None if pd.isna(d) else d >= -0.25, f"{d:+.1f} pp YoY")
        add("ROE above 12%", None if pd.isna(L.get("ROE %")) else L["ROE %"] >= 12, f"{L.get('ROE %', np.nan):.1f}%")
        add("ROCE above 12%", None if pd.isna(L.get("ROCE %")) else L["ROCE %"] >= 12, f"{L.get('ROCE %', np.nan):.1f}%")
        add("Debt / equity below 1x", None if pd.isna(L.get("Debt / Equity")) else L["Debt / Equity"] < 1,
            f"{L.get('Debt / Equity', np.nan):.2f}x")
        add("Interest cover above 3x", None if pd.isna(L.get("Interest Coverage")) else L["Interest Coverage"] > 3,
            f"{L.get('Interest Coverage', np.nan):.1f}x")
        add("Operating cash flow covers profit", None if pd.isna(L.get("CFO / PAT")) else L["CFO / PAT"] >= 0.8,
            f"CFO/PAT {L.get('CFO / PAT', np.nan):.2f}x")
        add("Free cash flow positive", None if pd.isna(L.get("FCF")) else L["FCF"] > 0,
            f"{L.get('FCF', np.nan):,.0f}")
        return checks

    def score(self) -> tuple[int, int]:
        c = [x for x in self.scorecard() if x["pass"] is not None]
        return sum(1 for x in c if x["pass"]), len(c)
