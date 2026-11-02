# FinSight: annual report and financial model dashboard

A Streamlit + Plotly dashboard that turns a company's financials into KPIs, performance charts, ratio analysis, a written case study, an automatic 3-statement model with DCF, and downloadable reports. Dark green UI modelled on your reference image, with a dark/light toggle.

## Run it (Windows, Python 3.14)

1. Unzip the folder.
2. Double-click **`run_windows.bat`**. The first run creates a `.venv`, installs packages (a few minutes) and opens http://localhost:8501.
3. Click **Try the demo** on the welcome screen to see everything with synthetic data.

Manual way:
```
py -3.14 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
macOS/Linux: `bash run_mac_linux.sh`

**Screenshots (OCR) need Tesseract**, a separate program: install from https://github.com/UB-Mannheim/tesseract/wiki, then either add it to PATH or paste `C:\Program Files\Tesseract-OCR\tesseract.exe` in the sidebar's *Tesseract path* box. Everything else works without it.

## What you can upload (Data Hub)

| Input | What happens |
|---|---|
| **Screener.in Excel export** ("Export to Excel" on a company page) | Best path. Reads the *Data Sheet*: 10-year P&L, balance sheet, cash flow, price. The whole dashboard and model build automatically. |
| **Any Excel / CSV** | Line items in column A, years or dates across the top (or years down the rows). Common names like "Revenue from operations" or "Finance costs" are mapped automatically. |
| **Annual report PDF** | Finds the Chairman's message, business overview, MD&A, risks, governance, statements. Summarises them, mines key facts, and extracts the balance sheet / P&L / cash-flow lines into an editable table. **You review and correct, then click Apply.** |
| **Screenshots** (PNG/JPG) | OCR reads the lines, and you review them in the same editable table. |

Each Excel/CSV upload becomes its own company, so you can compare several on the **Compare companies** page.

## Pages

- **Dashboard**: KPI cards with sparklines, valuation snapshot, key ratios, cash-flow chart, year-on-year changes, cost-structure and asset-mix donuts, health scorecard, profile radar.
- **Financial performance**: income statement, balance sheet and cash-flow tabs, with a revenue-to-profit waterfall, growth, expense mix, working-capital days, leverage, cash conversion and the full statement tables.
- **KPIs & ratios**: gauges, DuPont tree, ratio groups (profitability, returns, leverage, efficiency, cash flow, valuation, per share, growth) and a metric explorer.
- **Business case study**: a written analysis of the year (business snapshot, year in review, growth, costs, returns, balance sheet, cash allocation, strengths and watch-outs, outlook). Uses the annual report text when one is loaded.
- **Annual report**: section browser, extractive summaries, themes (outlook, strategy, risks, capital allocation), key facts and full-text search.
- **Financial model**: auto-built 3-statement projection (3–10 years), Bear/Base/Bull scenarios, DCF with a CAPM WACC helper and a WACC × growth sensitivity table. Every driver is editable and defaults come from the company's own history. The balance sheet balances by construction, and a check row proves it.
- **Reports & export**: Excel workbook (including a **live-formula model** you can edit in Excel), PDF report, standalone HTML dashboard, CSV of all metrics.

## Please read: limits and accuracy

- **PDF and screenshot extraction is rule-based, not perfect.** It reads clean text-based statements well; multi-column, scanned or unusual layouts need correction in the review table. Always check the totals against the source before relying on the numbers.
- Scanned PDFs (no text layer) are not read directly. Upload page screenshots instead.
- The **case study is generated from rules and templates**, not an AI model. It states facts from your numbers and quotes sentences from the report. It does not "understand" the business beyond that.
- **Not covered**: segment and geography tables, notes to accounts, shareholding pattern, related-party details, quarterly trends (the Screener quarterly sheet is read but not charted), industry and peer data not in your files.
- **Projections are mechanical extrapolations** of history, and the DCF is very sensitive to WACC and terminal growth (the app warns when terminal value exceeds 75% of EV). Capex is estimated from the net-block movement. This is not investment advice.
- In **light mode** the editable review table in Data Hub keeps Streamlit's dark styling; everything else follows the theme.
- Demo data is **synthetic**, not a real company.

## Folder layout

```
app.py              main app, navigation, Data Hub, export page
fin/parsers.py      Screener / Excel / CSV / text-line parsing, line-item mapping
fin/pdf_tools.py    PDF text, sections, summaries, key facts, OCR
fin/analytics.py    KPIs, ratios, scorecard
fin/model.py        projections, scenarios, DCF
fin/narrative.py    case-study writer
fin/charts.py       Plotly charts      fin/views.py   page layouts
fin/ui.py           CSS theme          fin/theme.py   colour tokens
fin/export.py       Excel / PDF / HTML export
samples/            demo Screener-format Excel and a sample annual report PDF
```

Chart colours follow a palette checked for colour-blind separation and contrast in both modes.
