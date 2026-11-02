"""Synthetic demo data (NOT a real company) used for the 'Load demo' button and for testing."""
from __future__ import annotations

import io
from datetime import datetime

import numpy as np

DEMO_NAME = "Demo Industries Ltd (synthetic)"


def build_demo_rows(seed: int = 7):
    rng = np.random.default_rng(seed)
    years = list(range(2016, 2026))
    n = len(years)
    sales = [2100.0]
    for _ in range(n - 1):
        sales.append(sales[-1] * (1 + rng.normal(0.115, 0.04)))
    sales = np.array(sales)
    sales[4] *= 0.93  # a dip (covid-style) year
    for i in range(5, n):
        sales[i] = max(sales[i], sales[i - 1] * 1.04)

    pct = {"Raw Material Cost": 0.46, "Change in Inventory": -0.004, "Power and Fuel": 0.035, "Other Mfr. Exp": 0.03,
           "Employee Cost": 0.085, "Selling and admin": 0.05, "Other Expenses": 0.045}
    exp = {k: [] for k in pct}
    for i in range(n):
        drift = (i - 4) * 0.0012
        for k, v in pct.items():
            f = v + rng.normal(0, 0.003) + (drift if k == "Raw Material Cost" else -drift / 2 if k == "Employee Cost" else 0)
            exp[k].append(sales[i] * f)
    exp = {k: np.array(v) for k, v in exp.items()}
    tot_exp = sum(exp.values())
    other_inc = sales * 0.011 + rng.normal(0, 4, n)
    dep = np.zeros(n)
    intr = np.zeros(n)
    pbt = np.zeros(n); tax = np.zeros(n); pat = np.zeros(n); div = np.zeros(n)

    eq_cap = 80.0
    reserves = [1100.0]
    debt = [900.0]
    net_block = [1300.0]
    cwip = [120.0]
    invest = [150.0]
    recv, invent, cash = [], [], []
    other_liab = []
    resid_oth = []
    cfo, cfi, cff = [], [], []
    recv_days = 62 + rng.normal(0, 3, n)
    inv_days = 58 + rng.normal(0, 3, n)
    olp = 0.115
    recv0 = sales[0] * recv_days[0] / 365
    inv0 = sales[0] * inv_days[0] / 365
    recv.append(recv0); invent.append(inv0); cash.append(180.0)
    other_liab.append(sales[0] * olp)
    resid_oth.append(sales[0] * 0.03)
    prev_wc_assets = recv0 + inv0 + resid_oth[0]
    for i in range(n):
        if i == 0:
            dep[i] = net_block[0] * 0.075
            intr[i] = debt[0] * 0.095
        else:
            dep[i] = net_block[i - 1] * 0.075
            intr[i] = debt[i - 1] * (0.095 - 0.0006 * i)
        ebitda = sales[i] - tot_exp[i]
        pbt[i] = ebitda + other_inc[i] - dep[i] - intr[i]
        tax[i] = pbt[i] * (0.255 if i < 3 else 0.24)
        pat[i] = pbt[i] - tax[i]
        div[i] = pat[i] * (0.18 + 0.01 * i / 3)
        if i > 0:
            recv.append(sales[i] * recv_days[i] / 365)
            invent.append(sales[i] * inv_days[i] / 365)
            other_liab.append(sales[i] * olp)
            resid_oth.append(sales[i] * 0.03)
            capex = sales[i] * (0.07 if i < 5 else 0.055)
            nb_new = net_block[-1] + capex * 0.85 - dep[i]
            cw_new = cwip[-1] + capex * 0.15
            d_wc = (recv[i] + invent[i] + resid_oth[i]) - (recv[i - 1] + invent[i - 1] + resid_oth[i - 1]) \
                - (other_liab[i] - other_liab[i - 1])
            d_debt = (-60.0 if i in (3, 4) else -90.0 if i >= 6 else 40.0)
            reserves.append(reserves[-1] + pat[i] - div[i])
            debt.append(max(debt[-1] + d_debt, 150))
            net_block.append(nb_new); cwip.append(cw_new); invest.append(invest[-1])
            cfo_i = pat[i] + dep[i] - d_wc
            cfi_i = -capex
            cff_i = (debt[i] - debt[i - 1]) - div[i]
            cash.append(cash[-1] + cfo_i + cfi_i + cff_i)
            cfo.append(cfo_i); cfi.append(cfi_i); cff.append(cff_i)
        else:
            cfo.append(pat[0] + dep[0] - 40); cfi.append(-sales[0] * 0.07); cff.append(-div[0] - 20)
    other_assets = [recv[i] + invent[i] + cash[i] + resid_oth[i] for i in range(n)]
    tot_liab = [eq_cap + reserves[i] + debt[i] + other_liab[i] for i in range(n)]
    tot_assets = [net_block[i] + cwip[i] + invest[i] + other_assets[i] for i in range(n)]
    # smooth the opening-year imbalance by adjusting year-0 reserves
    gap = tot_assets[0] - tot_liab[0]
    reserves[0] += gap
    for i in range(1, n):
        reserves[i] += gap
    tot_liab = [eq_cap + reserves[i] + debt[i] + other_liab[i] for i in range(n)]
    price = [pat[i] / 40.0 * (14 + 0.9 * i + rng.normal(0, 2)) for i in range(n)]
    shares_abs = 40.0 * 1e7
    return dict(years=years, sales=sales, exp=exp, other_inc=other_inc, dep=dep, intr=intr, pbt=pbt, tax=tax, pat=pat,
                div=div, eq_cap=eq_cap, reserves=reserves, debt=debt, other_liab=other_liab, net_block=net_block,
                cwip=cwip, invest=invest, other_assets=other_assets, recv=recv, invent=invent, cash=cash,
                tot_liab=tot_liab, tot_assets=tot_assets, cfo=cfo, cfi=cfi, cff=cff, price=price, shares_abs=shares_abs)


def demo_screener_xlsx(seed: int = 7, name: str = DEMO_NAME) -> bytes:
    """Write the demo in the same layout as screener.in's 'Data Sheet' export."""
    import openpyxl
    d = build_demo_rows(seed)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data Sheet"
    dates = [datetime(y, 3, 31) for y in d["years"]]
    ws.append(["COMPANY NAME", name])
    ws.append(["CURRENT VERSION", "2"])
    ws.append([])
    ws.append(["META"])
    ws.append(["Number of shares", d["shares_abs"]])
    ws.append(["Face Value", 2])
    ws.append(["Current Price", round(d["price"][-1], 2)])
    ws.append(["Market Capitalization", round(d["price"][-1] * 40.0, 2)])
    ws.append([])
    ws.append(["PROFIT & LOSS"])
    ws.append(["Report Date"] + dates)
    r = lambda arr: [round(float(x), 2) for x in arr]  # noqa: E731
    ws.append(["Sales"] + r(d["sales"]))
    for k in ["Raw Material Cost", "Change in Inventory", "Power and Fuel", "Other Mfr. Exp", "Employee Cost",
              "Selling and admin", "Other Expenses"]:
        ws.append([k] + r(d["exp"][k]))
    ws.append(["Other Income"] + r(d["other_inc"]))
    ws.append(["Depreciation"] + r(d["dep"]))
    ws.append(["Interest"] + r(d["intr"]))
    ws.append(["Profit before tax"] + r(d["pbt"]))
    ws.append(["Tax"] + r(d["tax"]))
    ws.append(["Net profit"] + r(d["pat"]))
    ws.append(["Dividend Amount"] + r(d["div"]))
    ws.append([])
    ws.append(["QUARTERS"])
    ws.append([])
    ws.append(["BALANCE SHEET"])
    ws.append(["Report Date"] + dates)
    ws.append(["Equity Share Capital"] + [d["eq_cap"]] * len(dates))
    ws.append(["Reserves"] + r(d["reserves"]))
    ws.append(["Borrowings"] + r(d["debt"]))
    ws.append(["Other Liabilities"] + r(d["other_liab"]))
    ws.append(["Total"] + r(d["tot_liab"]))
    ws.append(["Net Block"] + r(d["net_block"]))
    ws.append(["Capital Work in Progress"] + r(d["cwip"]))
    ws.append(["Investments"] + r(d["invest"]))
    ws.append(["Other Assets"] + r(d["other_assets"]))
    ws.append(["Total"] + r(d["tot_assets"]))
    ws.append(["Receivables"] + r(d["recv"]))
    ws.append(["Inventory"] + r(d["invent"]))
    ws.append(["Cash & Bank"] + r(d["cash"]))
    ws.append(["No. of Equity Shares"] + [d["shares_abs"]] * len(dates))
    ws.append([])
    ws.append(["CASH FLOW:"])
    ws.append(["Report Date"] + dates)
    ws.append(["Cash from Operating Activity"] + r(d["cfo"]))
    ws.append(["Cash from Investing Activity"] + r(d["cfi"]))
    ws.append(["Cash from Financing Activity"] + r(d["cff"]))
    ws.append(["Net Cash Flow"] + r(np.array(d["cfo"]) + np.array(d["cfi"]) + np.array(d["cff"])))
    ws.append([])
    ws.append(["PRICE:"] + r(d["price"]))
    ws.append([])
    ws.append(["DERIVED:"])
    ws.append(["Adjusted Equity Shares in Cr"] + [40.0] * len(dates))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def demo_annual_report_pdf() -> bytes:
    """A small fake annual report (text) to exercise the PDF explorer."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak, Spacer, Preformatted
    d = build_demo_rows()
    st = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    S = []
    h = lambda t: S.append(Paragraph(t, st["Heading1"]))  # noqa: E731
    p = lambda t: (S.append(Paragraph(t, st["BodyText"])), S.append(Spacer(1, 8)))  # noqa: E731
    h("Demo Industries Ltd - Annual Report 2024-25 (synthetic sample)")
    p("This is a synthetic document generated for testing the dashboard. It is not a real company.")
    S.append(PageBreak())
    h("Chairman's Message")
    p("Dear Shareholders, FY25 was a year of disciplined growth. Revenue from operations rose to a record level and we "
      "continued to reduce borrowings while investing in capacity. We remain committed to a balanced capital allocation "
      "policy, returning cash to shareholders through dividends while funding growth from internal accruals.")
    p("Our outlook for the coming year is positive. We expect demand to remain healthy across our key end-markets and "
      "plan to commission a new plant to expand our specialty product capacity by 25 percent.")
    S.append(PageBreak())
    h("Business Overview")
    p("Demo Industries Ltd manufactures engineered components and specialty chemicals for the automotive, infrastructure and "
      "consumer durables sectors. The company operates 9 manufacturing plants across India and employs 6,240 permanent employees. "
      "Exports contribute about 31 percent of revenue to more than 40 countries.")
    p("The company has two business segments: Engineered Components and Specialty Chemicals. Engineered Components contributes "
      "about 64 percent of revenue and Specialty Chemicals the balance. Rated CRISIL AA+ for long-term borrowings.")
    S.append(PageBreak())
    h("Management Discussion and Analysis")
    p("Industry overview: The domestic manufacturing sector recorded healthy growth supported by infrastructure spending and "
      "rising consumption. Raw material prices were stable during the year, helping margins. The board recommended a final "
      "dividend of Rs. 2.50 per share for the year.")
    p("Risks and concerns: Commodity price volatility, currency fluctuations, regulatory changes and intense competition remain "
      "the principal risks. The company hedges a significant portion of its foreign currency exposure. "
      "Opportunities include the China-plus-one trend, premiumisation and the shift toward specialty grades.")
    p("Outlook: Management expects revenue growth of 12 to 14 percent and stable operating margins in the next year, "
      "supported by new capacity and a strong order book.")
    S.append(PageBreak())
    h("Risk Management")
    p("The company has a risk management framework overseen by the Risk Committee. Key risks include supply chain disruption, "
      "customer concentration (top 5 customers contribute 38 percent of revenue), cybersecurity and talent attrition.")
    S.append(PageBreak())
    h("Corporate Governance Report")
    p("The Board comprises 9 directors of whom 5 are independent. The Audit Committee met 5 times during the year.")
    S.append(PageBreak())
    h("Balance Sheet as at March 31, 2025")
    p("(Rs. in crore)")
    i = -1
    j = -2
    rows = [
        ("Equity share capital", d["eq_cap"], d["eq_cap"]),
        ("Other equity / Reserves", d["reserves"][i], d["reserves"][j]),
        ("Borrowings", d["debt"][i], d["debt"][j]),
        ("Other liabilities", d["other_liab"][i], d["other_liab"][j]),
        ("Total equity and liabilities", d["tot_liab"][i], d["tot_liab"][j]),
        ("Property, plant and equipment", d["net_block"][i], d["net_block"][j]),
        ("Capital work-in-progress", d["cwip"][i], d["cwip"][j]),
        ("Investments", d["invest"][i], d["invest"][j]),
        ("Inventories", d["invent"][i], d["invent"][j]),
        ("Trade receivables", d["recv"][i], d["recv"][j]),
        ("Cash and cash equivalents", d["cash"][i], d["cash"][j]),
        ("Total assets", d["tot_assets"][i], d["tot_assets"][j]),
    ]
    txt = "Particulars                              Note   March 31, 2025   March 31, 2024\n"
    for k, a, b in rows:
        txt += f"{k:<40} {'12':>4} {a:>15,.2f} {b:>15,.2f}\n"
    S.append(Preformatted(txt, st["Code"]))
    S.append(PageBreak())
    h("Statement of Profit and Loss for the year ended March 31, 2025")
    p("(Rs. in crore)")
    rows = [
        ("Revenue from operations", d["sales"][i], d["sales"][j]),
        ("Other income", d["other_inc"][i], d["other_inc"][j]),
        ("Cost of materials consumed", d["exp"]["Raw Material Cost"][i], d["exp"]["Raw Material Cost"][j]),
        ("Employee benefits expense", d["exp"]["Employee Cost"][i], d["exp"]["Employee Cost"][j]),
        ("Depreciation and amortisation expense", d["dep"][i], d["dep"][j]),
        ("Finance costs", d["intr"][i], d["intr"][j]),
        ("Profit before tax", d["pbt"][i], d["pbt"][j]),
        ("Tax expense", d["tax"][i], d["tax"][j]),
        ("Profit for the year", d["pat"][i], d["pat"][j]),
    ]
    txt = "Particulars                              Note   Year ended 2025   Year ended 2024\n"
    for k, a, b in rows:
        txt += f"{k:<40} {'20':>4} {a:>15,.2f} {b:>15,.2f}\n"
    S.append(Preformatted(txt, st["Code"]))
    S.append(PageBreak())
    h("Cash Flow Statement")
    p("(Rs. in crore)")
    rows = [
        ("Net cash from operating activities", d["cfo"][i], d["cfo"][j]),
        ("Net cash used in investing activities", d["cfi"][i], d["cfi"][j]),
        ("Net cash used in financing activities", d["cff"][i], d["cff"][j]),
    ]
    txt = "Particulars                                    2025            2024\n"
    for k, a, b in rows:
        a_s = f"({abs(a):,.2f})" if a < 0 else f"{a:,.2f}"
        b_s = f"({abs(b):,.2f})" if b < 0 else f"{b:,.2f}"
        txt += f"{k:<40} {a_s:>15} {b_s:>15}\n"
    S.append(Preformatted(txt, st["Code"]))
    doc.build(S)
    return buf.getvalue()


if __name__ == "__main__":
    open("samples/demo_screener_export.xlsx", "wb").write(demo_screener_xlsx())
    open("samples/demo_annual_report.pdf", "wb").write(demo_annual_report_pdf())
    print("written")
