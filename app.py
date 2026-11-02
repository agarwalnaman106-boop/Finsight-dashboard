"""FinSight — annual-report & Screener financial dashboard.  Run:  streamlit run app.py"""
from __future__ import annotations

import html
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
import streamlit as st

from fin import charts as C
from fin import export as EX
from fin import model as MD
from fin import pdf_tools as PT
from fin import sample, views
from fin.analytics import Metrics
from fin.parsers import (STATEMENT_OF, Company, UNIT_FACTORS, lines_to_company, merge_company, parse_any, period_label)
from fin.theme import tokens
from fin.ui import card, card_title, css
from fin.utils import set_currency

st.set_page_config(page_title="FinSight · Financial dashboard", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

# ----------------------------------------------------------------------------- state
S = st.session_state
S.setdefault("companies", {})
S.setdefault("reports", {})
S.setdefault("active", None)
S.setdefault("page", "Dashboard")
S.setdefault("mode", "dark")
S.setdefault("unit_choice", "₹ Crore")
S.setdefault("processed", set())
S.setdefault("jobs", {})
S.setdefault("exports", {})

UNITS = {"₹ Crore": ("₹", "Cr", True), "₹ Lakh": ("₹", "Lakh", True), "₹ Million": ("₹", "M", False), "$ Million": ("$", "M", False), "$ Billion": ("$", "B", False)}
set_currency(*UNITS[S.unit_choice])
T = tokens(S.mode)
st.markdown(css(T), unsafe_allow_html=True)

NAV = [("GENERAL", [("Dashboard", "▦"), ("Financial performance", "◧"), ("KPIs & ratios", "◎")]),
       ("ANALYSIS", [("Business case study", "▤"), ("Annual report", "▣"), ("Compare companies", "⇄")]),
       ("MODEL", [("Financial model", "∿")]),
       ("TOOLS", [("Data Hub", "⇪"), ("Reports & export", "⇩")])]
TITLES = {"Dashboard": "Overview", "Financial performance": "Financial performance", "KPIs & ratios": "KPIs & ratios", "Business case study": "Business case study",
          "Annual report": "Annual report explorer", "Compare companies": "Compare companies", "Financial model": "Automatic financial model",
          "Data Hub": "Data Hub", "Reports & export": "Reports & export"}


# ----------------------------------------------------------------------------- helpers
def add_company(co: Company, report: dict | None = None):
    S.companies[co.name] = co
    if report is not None:
        S.reports[co.name] = report
    S.active = co.name


def build_report(pages: list[str]) -> dict:
    secs = PT.find_sections(pages)
    full = "\n".join(pages)
    mdna = secs.get("Management discussion & analysis", {}).get("text", "") or full
    biz = secs.get("Business overview", {}).get("text", "")
    biz = "\n".join(biz.splitlines()[1:]) if biz.count("\n") > 1 else biz
    overview = " ".join(PT.summarise(biz, 3)) if biz else " ".join(PT.summarise("\n".join(pages[: min(len(pages), 25)]), 3))
    return {"pages": pages, "sections": secs, "facts": PT.key_facts(full), "themes": PT.theme_sentences(mdna if len(mdna) > 800 else full), "overview": overview}


def load_demo():
    co = parse_any(sample.demo_screener_xlsx(), "demo.xlsx")
    pages = PT.extract_pages(sample.demo_annual_report_pdf())
    add_company(co, build_report(pages))


def load_demo_peer():
    import random
    seed = random.randint(11, 99)
    nm = f"Peer Co {len(S.companies) + 1} (synthetic)"
    co = parse_any(sample.demo_screener_xlsx(seed=seed, name=nm), "peer.xlsx")
    S.companies[co.name] = co


def process_upload(f):
    sig = (f.name, f.size)
    if sig in S.processed:
        return
    ext = f.name.lower().rsplit(".", 1)[-1]
    data = f.getvalue()
    try:
        if ext in ("xlsx", "xlsm", "xls", "csv", "tsv", "txt"):
            co = parse_any(data, f.name)
            if co.empty():
                st.error(f"{f.name}: could not find financial rows. Expect line items in column A and years/dates across the top.")
            else:
                add_company(co, S.reports.get(co.name))
                st.success(f"Loaded {co.name}: {len(co.periods)} periods ({co.periods[0]} – {co.periods[-1]}).")
        elif ext == "pdf":
            pages = PT.extract_pages(data)
            if sum(len(p) for p in pages) < 200:
                st.warning(f"{f.name}: almost no text found — it looks scanned. Upload page screenshots instead (OCR), or run OCR on the PDF first.")
            rep = build_report(pages)
            lines, unit = PT.statement_lines(pages, rep["sections"])
            items = PT.lines_to_items(lines) if lines else pd.DataFrame(columns=["label", "mapped_to", "v1", "v2"])
            yrs = PT.detect_year_labels(pages) or ["FY25", "FY24"]
            S.jobs[f.name] = {"kind": "pdf", "report": rep, "items": items, "unit": unit, "years": (yrs + ["", ""])[:2], "name": f.name.rsplit(".", 1)[0]}
        elif ext in ("png", "jpg", "jpeg", "webp", "bmp"):
            lines, err = PT.ocr_image(data)
            if err:
                st.error(err)
            else:
                items = PT.lines_to_items(lines)
                S.jobs[f.name] = {"kind": "img", "report": None, "items": items, "unit": "₹ crore", "years": ["FY25", "FY24"], "name": f.name.rsplit(".", 1)[0], "raw": "\n".join(lines)}
        else:
            st.error(f"{f.name}: unsupported file type.")
        S.processed.add(sig)
    except Exception as e:
        st.error(f"{f.name}: {e}")


def current():
    if S.active and S.active in S.companies:
        co = S.companies[S.active]
        return co, Metrics(co)
    return None, None


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("<div class='brand'><div class='logo'>✦</div><div><b>FinSight</b><small>Annual report & model studio</small></div></div>", unsafe_allow_html=True)
    for sec, items in NAV:
        st.markdown(f"<div class='navhead'>{sec}</div>", unsafe_allow_html=True)
        for label, ic in items:
            if st.button(f"{ic}  {label}", key=f"nav_{label}", type="primary" if S.page == label else "secondary", width="stretch"):
                S.page = label
                st.rerun()
    st.markdown("<div class='navhead'>SETTINGS</div>", unsafe_allow_html=True)
    S.unit_choice = st.selectbox("Currency & unit", list(UNITS), index=list(UNITS).index(S.unit_choice), label_visibility="collapsed")
    tpath = st.text_input("Tesseract path (OCR)", value=S.get("tess", ""), placeholder=r"C:\Program Files\Tesseract-OCR\tesseract.exe", help="Only needed for screenshot upload if Tesseract is not on PATH.")
    if tpath and tpath != S.get("tess_applied"):
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tpath
            S["tess_applied"] = tpath
        except Exception:
            pass
    st.markdown("<div class='upgrade'><b>✦ Tip</b><small>Upload a Screener.in Excel export for an instant full model.</small></div>", unsafe_allow_html=True)

# ----------------------------------------------------------------------------- top bar
co, m = current()
tb = st.columns([2.2, 1.5, 0.9, 1.0], gap="small", vertical_alignment="center")
with tb[0]:
    st.markdown(f"<div class='crumb'>Dashboards</div><div class='page-title'>{TITLES[S.page]}</div>", unsafe_allow_html=True)
with tb[1]:
    if S.companies:
        names = list(S.companies)
        sel = st.selectbox("Company", names, index=names.index(S.active) if S.active in names else 0, label_visibility="collapsed")
        if sel != S.active:
            S.active = sel
            st.rerun()
with tb[2]:
    dark = st.toggle("Dark", value=S.mode == "dark", help="Switch between dark and light theme")
    if dark != (S.mode == "dark"):
        S.mode = "dark" if dark else "light"
        st.rerun()
with tb[3]:
    if st.button("⇩  Export", width="stretch"):
        S.page = "Reports & export"
        st.rerun()

# ----------------------------------------------------------------------------- Data Hub
def data_hub():
    left, right = st.columns([1.5, 1], gap="medium")
    with left:
        with card("up"):
            card_title("Upload financials", "any combination — each Excel/CSV becomes a company")
            files = st.file_uploader("Drop files", type=["xlsx", "xlsm", "xls", "csv", "tsv", "pdf", "png", "jpg", "jpeg", "webp"], accept_multiple_files=True,
                                     label_visibility="collapsed", key="uploader")
            for f in files or []:
                process_upload(f)
    with right:
        with card("how"):
            card_title("What can I upload?")
            st.markdown("""
- **Screener.in Excel export** (best): full 10-year P&L, balance sheet, cash flow and price — the model builds automatically.
- **Any Excel / CSV**: line items down column A, years or dates across the top. Common names are auto-mapped.
- **Annual report PDF**: sections, summary, key facts, plus the primary statements extracted for you to review and correct.
- **Screenshots** of statements: read with OCR, then review before applying.
""")
            if st.button("Load demo company (synthetic)", type="primary"):
                load_demo()
                S.page = "Dashboard"
                st.rerun()
            st.download_button("Download a sample Screener-format file", sample.demo_screener_xlsx(), file_name="sample_screener_export.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    for fname, job in list(S.jobs.items()):
        with card("job"):
            icon = "PDF" if job["kind"] == "pdf" else "Screenshot"
            card_title(f"Review extraction: {fname}", f"{icon} · values are read automatically — check them, fix any row, then apply")
            c = st.columns([1.6, 1, 1, 1.2])
            nm = c[0].text_input("Company name", value=job["name"], key=f"jn_{fname}")
            y1 = c[1].text_input("Column 1 period", value=job["years"][0], key=f"j1_{fname}", help="Usually the latest year, e.g. FY25")
            y2 = c[2].text_input("Column 2 period", value=job["years"][1], key=f"j2_{fname}", help="Usually the previous year, e.g. FY24 (leave blank if absent)")
            uni = c[3].selectbox("Reported in", list(UNIT_FACTORS), index=list(UNIT_FACTORS).index(job["unit"]) if job["unit"] in UNIT_FACTORS else 0, key=f"ju_{fname}")
            items = job["items"].copy()
            if items.empty:
                st.warning("No statement lines detected. Try another page or a clearer screenshot.")
            else:
                options = [""] + sorted(STATEMENT_OF)
                edited = st.data_editor(items, hide_index=True, width="stretch", num_rows="dynamic", key=f"je_{fname}",
                                        column_config={"label": st.column_config.TextColumn("Line in document", disabled=True),
                                                       "mapped_to": st.column_config.SelectboxColumn("Maps to", options=options, help="Choose the standard line item"),
                                                       "v1": st.column_config.NumberColumn(y1 or "Col 1", format="%.2f"), "v2": st.column_config.NumberColumn(y2 or "Col 2", format="%.2f")})
                unmapped = int((edited["mapped_to"].fillna("") == "").sum())
                st.caption(f"{len(edited) - unmapped} lines mapped · {unmapped} ignored. Only mapped lines are used.")
                merge_into = None
                if S.companies:
                    merge_into = st.selectbox("Merge into existing company (optional)", ["— create new —"] + list(S.companies), key=f"jm_{fname}")
                b = st.columns([1, 1, 3])
                if b[0].button("Apply to dashboard", type="primary", key=f"ja_{fname}"):
                    pl = [p for p in (period_label(y1), period_label(y2) if y2 else "") if p]
                    new = lines_to_company(edited, pl, UNIT_FACTORS[uni], nm, f"{icon}: {fname}")
                    if new.empty():
                        st.error("Nothing mapped yet. Set 'Maps to' for at least Sales and Net profit.")
                    else:
                        if merge_into and merge_into != "— create new —":
                            new = merge_company(S.companies[merge_into], new)
                            new.name = merge_into
                        add_company(new, job["report"] or S.reports.get(new.name))
                        del S.jobs[fname]
                        S.page = "Dashboard"
                        st.rerun()
                if b[1].button("Discard", key=f"jd_{fname}"):
                    del S.jobs[fname]
                    st.rerun()
            if job["report"]:
                if st.button("Use only the narrative (no numbers)", key=f"jr_{fname}", help="Attach this report's text to an existing company without importing numbers"):
                    if S.active:
                        S.reports[S.active] = job["report"]
                        del S.jobs[fname]
                        st.rerun()
                    else:
                        st.info("Load a company first.")
            if job["kind"] == "img":
                with st.expander("Raw OCR text"):
                    st.text(job.get("raw", ""))

    if S.companies:
        with card("loaded"):
            card_title("Loaded companies")
            for n, c_ in list(S.companies.items()):
                cc = st.columns([3, 2, 1, 1])
                cc[0].markdown(f"**{html.escape(n)}**")
                cc[1].caption(f"{len(c_.periods)} periods · {', '.join(c_.sources)}" + (" · report ✓" if n in S.reports else ""))
                if cc[2].button("Open", key=f"open_{n}"):
                    S.active = n
                    S.page = "Dashboard"
                    st.rerun()
                if cc[3].button("Remove", key=f"rm_{n}"):
                    S.companies.pop(n, None); S.reports.pop(n, None)
                    S.active = next(iter(S.companies), None)
                    st.rerun()


# ----------------------------------------------------------------------------- Export page
def export_page(X):
    co, m = X["co"], X["m"]
    report = X.get("report")
    A = S.get(f"A::{co.name}") or MD.default_assumptions(m, 5)
    scen = S.get("scenario", "Base")
    wacc, g = S.get("wacc_in", 12.0), S.get("g_in", 5.0)
    proj = MD.project(m, A, scen)
    px = S.get(f"px_{co.name}") or None
    dcf = MD.run_dcf(m, proj, MD.DCFInputs(wacc, g, False, True, px))
    opts = [("xlsx", "Excel workbook", "Summary, statements, ratios and a live-formula model you can edit in Excel.", "Prepare Excel"),
            ("pdf", "PDF report", "Case study, charts, statements, projections and DCF summary.", "Prepare PDF"),
            ("html", "Interactive dashboard (HTML)", "A standalone page with the main charts (opens in any browser, needs internet for Plotly).", "Prepare HTML"),
            ("csv", "Metrics (CSV)", "Every computed metric by period.", "Prepare CSV")]
    c = st.columns(2, gap="medium")
    for i, (k, title, desc, btn) in enumerate(opts):
        with c[i % 2]:
            with card("ex"):
                card_title(title, desc)
                bkey = (co.name, k)
                if st.button(btn, key=f"prep_{k}", type="primary"):
                    with st.spinner("Building…"):
                        if k == "xlsx":
                            S.exports[bkey] = (EX.to_excel(m, co, A, scen, wacc, g), f"{co.name}_financials.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                        elif k == "pdf":
                            S.exports[bkey] = (EX.to_pdf(m, co, report, proj, dcf if "per_share" in dcf else None), f"{co.name}_report.pdf", "application/pdf")
                        elif k == "csv":
                            S.exports[bkey] = (m.df.to_csv().encode("utf-8"), f"{co.name}_metrics.csv", "text/csv")
                        else:
                            d = m.df.tail(10)
                            figs = [("Revenue, profit and margin", C.bars_with_line(d, ["Revenue", "PAT"], "EBITDA Margin %", T)),
                                    ("Cash flow", C.cashflow_chart(d, T)),
                                    ("Margins and returns", C.area_line(d, ["EBITDA Margin %", "Net Margin %", "ROCE %", "ROE %"], T, fill_first=False)),
                                    ("Projection: revenue", C.projection_chart(m.df, proj.pl, proj.base_label, proj.labels, T, "Revenue"))]
                            S.exports[bkey] = (EX.figs_to_html(f"{co.name} — dashboard", figs, S.mode == "dark"), f"{co.name}_dashboard.html", "text/html")
                if bkey in S.exports:
                    data, fn, mime = S.exports[bkey]
                    st.download_button(f"Download {fn}", data, file_name=fn, mime=mime, key=f"dl_{k}")


# ----------------------------------------------------------------------------- welcome
def welcome():
    with card("welcome"):
        st.markdown("<div class='crumb'>Welcome</div><div class='page-title'>Turn any company's financials into a full dashboard</div>", unsafe_allow_html=True)
        st.markdown("<p style='margin-top:10px;color:var(--text2);max-width:760px;line-height:1.7'>Upload a <b>Screener.in Excel</b>, any <b>Excel/CSV</b>, an <b>annual report PDF</b> or <b>screenshots</b> of the statements. "
                    "You get KPIs, performance charts, ratio analysis, a written case study, an automatic 3-statement model with DCF, and exportable reports.</p>", unsafe_allow_html=True)
        c = st.columns([1, 1, 3])
        if c[0].button("Try the demo", type="primary"):
            load_demo()
            st.rerun()
        if c[1].button("Open Data Hub"):
            S.page = "Data Hub"
            st.rerun()


# ----------------------------------------------------------------------------- router
if S.page == "Data Hub":
    data_hub()
elif co is None:
    welcome()
else:
    m = Metrics(co)
    X = {"co": co, "m": m, "T": T, "report": S.reports.get(co.name), "load_demo_peer": load_demo_peer}
    for n in co.notes:
        st.caption(f"ℹ {n}")
    if S.page == "Dashboard":
        views.overview(X)
    elif S.page == "Financial performance":
        views.performance(X)
    elif S.page == "KPIs & ratios":
        views.ratios(X)
    elif S.page == "Business case study":
        try:
            A = S.get(f"A::{co.name}") or MD.default_assumptions(m, 5)
            p = MD.project(m, A, "Base")
            r = MD.run_dcf(m, p, MD.DCFInputs(12, 5, False, True, S.get(f"px_{co.name}") or None))
            X["proj_summary"] = {"revenue_end": p.pl.loc["Revenue", p.labels[-1]], "pat_end": p.pl.loc["PAT", p.labels[-1]], "end_label": p.labels[-1],
                                 "rev_cagr": ((p.pl.loc["Revenue", p.labels[-1]] / p.pl.loc["Revenue", p.base_label]) ** (1 / len(p.labels)) - 1) * 100,
                                 "value_ps": r.get("per_share"), "price": r.get("price")}
        except Exception:
            pass
        views.case_study(X)
    elif S.page == "Annual report":
        views.annual_report(X)
    elif S.page == "Compare companies":
        views.compare(X)
    elif S.page == "Financial model":
        up = st.file_uploader("Drop a Screener.in export (or any Excel/CSV) to rebuild the model for another company", type=["xlsx", "xlsm", "xls", "csv"], key="model_uploader")
        if up:
            process_upload(up)
            if S.active in S.companies and S.companies[S.active] is not co:
                st.rerun()
        views.model_page(X)
    elif S.page == "Reports & export":
        export_page(X)
