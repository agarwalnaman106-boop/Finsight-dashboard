"""Styling + small HTML components that reproduce the reference dashboard look (dark green, glow cards, pill deltas)."""
from __future__ import annotations

import html
import itertools

import numpy as np
import pandas as pd
import streamlit as st

from .utils import is_nan

_counter = itertools.count()


def css(T: dict) -> str:
    dark = T["mode"] == "dark"
    glow = (f"radial-gradient(900px 420px at 88% -8%, {T['glow']}, transparent 60%), radial-gradient(700px 380px at 6% 105%, {T['glow']}, transparent 62%)"
            if dark else f"radial-gradient(900px 420px at 90% -10%, {T['glow']}, transparent 60%)")
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {{
  --bg:{T['bg']}; --panel:{T['panel']}; --card:{T['card']}; --card2:{T['card2']}; --border:{T['border']}; --border2:{T['border2']};
  --text:{T['text']}; --text2:{T['text2']}; --muted:{T['muted']}; --accent:{T['accent']}; --accent-soft:{T['accent_soft']};
  --pos:{T['pos']}; --neg:{T['neg']}; --warn:{T['warn']}; --lime:{T['lime']};
}}
html, body, [class*="css"], .stApp {{ font-family: 'Inter','Segoe UI',system-ui,sans-serif !important; }}
.stApp {{ background: {glow}, var(--bg); background-attachment: fixed; color: var(--text); }}
[data-testid="stAppViewContainer"], [data-testid="stMain"], .main {{ background: transparent !important; }}
header[data-testid="stHeader"] {{ background: transparent !important; pointer-events: none; }}
header[data-testid="stHeader"] * {{ pointer-events: none; }}
[data-testid="stExpandSidebarButton"] {{ background: var(--card) !important; border:1px solid var(--border2) !important; border-radius:12px !important; color: var(--text) !important; }}
[data-testid="stExpandSidebarButton"] svg {{ fill: var(--text) !important; color: var(--text) !important; }}
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] * , [data-testid="stSidebarCollapsedControl"] * {{ pointer-events: auto !important; }}
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stMainMenu"], [data-testid="stMainMenuButton"], [data-testid="stAppDeployButton"], .stDeployButton {{ display:none !important; }}
.block-container {{ padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1560px; }}
h1,h2,h3,h4,h5,p,span,label,div {{ color: var(--text); }}
.stMarkdown p, .stCaption, small {{ color: var(--text2); }}

/* sidebar */
[data-testid="stSidebar"] {{ background: var(--panel); border-right: 1px solid var(--border); }}
[data-testid="stSidebar"] > div:first-child {{ padding-top: 1rem; }}
[data-testid="stSidebar"] .block-container {{ padding: 0; }}
.brand {{ display:flex; align-items:center; gap:12px; padding:14px 16px; border:1px solid var(--border2); border-radius:16px; background:var(--card); margin-bottom:6px; }}
.brand .logo {{ width:34px; height:34px; border-radius:10px; background:var(--accent-soft); display:grid; place-items:center; color:var(--accent); font-size:18px; }}
.brand b {{ font-size:16px; letter-spacing:.2px; }} .brand small {{ display:block; color:var(--muted); font-size:11px; margin-top:1px; }}
.navhead {{ font-size:10.5px; letter-spacing:1.4px; color:var(--muted); font-weight:600; padding:20px 6px 10px; text-transform:uppercase; line-height:1.2; }}
[data-testid="stSidebar"] .stButton > button {{ width:100%; justify-content:flex-start; text-align:left; border:1px solid transparent; background:transparent;
  color:var(--text2); padding:9px 12px; border-radius:12px; font-weight:500; font-size:13.5px; box-shadow:none; }}
[data-testid="stSidebar"] .stButton > button:hover {{ background:var(--card2); color:var(--text); border-color:var(--border); }}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {{ background:var(--card2); color:var(--text); border:1px solid var(--border2);
  box-shadow: inset 3px 0 0 var(--accent); }}
[data-testid="stSidebar"] .stButton > button p {{ color:inherit; margin:0; text-align:left; }}
[data-testid="stSidebar"] .stButton > button div, [data-testid="stSidebar"] .stButton > button span {{ justify-content:flex-start !important; text-align:left !important; width:100%; }}
[data-testid="stSidebar"] .stButton > button {{ min-height:2.35rem; padding-top:6px; padding-bottom:6px; }}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap:0.2rem; }}
[data-testid="stSidebar"] .stSelectbox, [data-testid="stSidebar"] .stTextInput {{ padding:0 4px; }}
.upgrade {{ margin-top:18px; border:1px solid var(--border2); border-radius:14px; padding:12px 14px; background:linear-gradient(135deg,{T['accent_soft']},transparent); }}
.upgrade b {{ font-size:13px; }} .upgrade small {{ color:var(--muted); display:block; margin-top:2px; font-size:11px; }}

/* cards */
[class*="st-key-card"] {{ background: var(--card); border:1px solid var(--border); border-radius:20px; padding:18px 20px 12px; position:relative; overflow:hidden; }}
[class*="st-key-card"]::after {{ content:''; position:absolute; inset:0; pointer-events:none; border-radius:20px;
  background: radial-gradient(420px 160px at 100% 0%, {T['glow']}, transparent 70%); opacity:{0.9 if dark else 0.5}; }}
.card-title {{ font-size:14px; color:var(--text2); font-weight:500; margin-bottom:2px; display:flex; justify-content:space-between; align-items:center; }}
.card-sub {{ color:var(--muted); font-size:12px; margin-top:-2px; }}
.kpi-value {{ font-size:30px; font-weight:600; letter-spacing:-.5px; line-height:1.15; margin:6px 0 2px; color:var(--text); }}
.pill {{ display:inline-flex; align-items:center; gap:5px; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }}
.pill.up {{ background:{'rgba(46,216,143,.14)' if dark else 'rgba(15,157,106,.12)'}; color:var(--pos); }}
.pill.down {{ background:{'rgba(255,93,93,.14)' if dark else 'rgba(214,58,58,.10)'}; color:var(--neg); }}
.pill.flat {{ background:var(--card2); color:var(--text2); }}
.dots {{ color:var(--muted); letter-spacing:2px; font-size:14px; }}
.chip {{ display:inline-block; padding:4px 11px; border-radius:999px; font-size:11.5px; border:1px solid var(--border2); color:var(--text2); background:var(--card2); margin:2px 4px 2px 0; }}
.chip.good {{ color:var(--pos); border-color:{'rgba(46,216,143,.35)' if dark else 'rgba(15,157,106,.35)'}; }}
.chip.bad {{ color:var(--neg); border-color:{'rgba(255,93,93,.35)' if dark else 'rgba(214,58,58,.35)'}; }}
.row-item {{ display:flex; align-items:center; gap:12px; padding:10px 0; border-bottom:1px solid var(--border); }}
.row-item:last-child {{ border-bottom:none; }}
.row-ic {{ width:38px; height:38px; border-radius:50%; background:var(--card2); border:1px solid var(--border2); display:grid; place-items:center; font-size:15px; flex:none; }}
.row-main {{ flex:1; min-width:0; }} .row-main b {{ font-size:13.5px; font-weight:600; }} .row-main small {{ display:block; color:var(--muted); font-size:11.5px; }}
.row-val {{ font-weight:600; font-size:14px; white-space:nowrap; }}
.check {{ display:flex; gap:10px; align-items:flex-start; padding:7px 0; font-size:13px; }}
.check .ic {{ width:20px; height:20px; border-radius:50%; display:grid; place-items:center; font-size:11px; flex:none; margin-top:1px; font-weight:700; }}
.check .ic.ok {{ background:var(--accent-soft); color:var(--pos); }} .check .ic.no {{ background:{'rgba(255,93,93,.14)' if dark else 'rgba(214,58,58,.10)'}; color:var(--neg); }}
.check .ic.na {{ background:var(--card2); color:var(--muted); }}
.check small {{ color:var(--muted); display:block; }}
.hero {{ font-size:34px; font-weight:600; letter-spacing:-.6px; }}
.page-title {{ font-size:26px; font-weight:600; letter-spacing:-.4px; margin:0; }}
.crumb {{ color:var(--muted); font-size:13px; margin-bottom:4px; }}
.narr h4 {{ font-size:15px; margin:0 0 8px; color:var(--accent); font-weight:600; }}
.narr p {{ color:var(--text); font-size:14px; line-height:1.65; margin:0 0 8px; }}
.narr li {{ color:var(--text2); font-size:13.5px; line-height:1.6; }}
.quote {{ border-left:3px solid var(--accent); padding:4px 0 4px 12px; margin:8px 0; color:var(--text2); font-size:13.5px; line-height:1.6; }}

/* widget text follows our tokens (Streamlit's own theme is fixed dark) */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label, .stRadio label p, .stCheckbox label p, .stToggle label p, [data-testid="stCaptionContainer"] p,
.stTabs [data-baseweb="tab"] p, [data-testid="stExpander"] summary span, .stMultiSelect label p {{ color: var(--text2) !important; }}
.stTabs [aria-selected="true"] p {{ color: var(--text) !important; }}
[data-baseweb="input"], [data-baseweb="base-input"] {{ background: var(--card2) !important; border-radius:12px !important; }}
[data-baseweb="input"] input, [data-baseweb="base-input"] input {{ color: var(--text) !important; -webkit-text-fill-color: var(--text) !important; }}
[data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] {{ background: var(--card2) !important; color: var(--text) !important; }}
[data-testid="stNumberInputStepDown"] svg, [data-testid="stNumberInputStepUp"] svg {{ fill: var(--text2) !important; }}
[data-baseweb="select"] svg {{ fill: var(--text2) !important; }}
[data-baseweb="tag"] {{ background: var(--accent) !important; }} [data-baseweb="tag"] span {{ color:#04110b !important; }}
[data-testid="stSidebar"] [data-testid="stCollapseButton"] svg, [data-testid="stSidebar"] button svg {{ fill: var(--text2); color: var(--text2); }}
[data-testid="stFileUploaderDropzone"] button {{ background: var(--card); color: var(--text); border:1px solid var(--border2); }}
.stRadio [role="radiogroup"] label span {{ color: var(--text2); }}

/* inputs: element names for this Streamlit version */
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], [data-testid="stSelectbox"] div[role="group"], [data-testid="stMultiSelect"] div[role="group"],
[data-testid="stTextArea"] textarea {{ background: var(--card2) !important; border:1px solid var(--border2) !important; border-radius:12px !important; }}
[data-testid="stTextInputField"], [data-testid="stNumberInputField"], input[role="combobox"] {{ color: var(--text) !important; -webkit-text-fill-color: var(--text) !important; background: transparent !important; }}
[data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] {{ background: var(--card) !important; color: var(--text) !important; }}
[data-testid="stSelectboxVirtualDropdown"], [data-testid="stSelectboxVirtualDropdown"] ul {{ background: var(--card2) !important; }}
[role="option"], [role="option"] * {{ color: var(--text) !important; }}
[role="option"][aria-selected="true"], [role="option"]:hover {{ background: var(--accent-soft) !important; }}
[data-testid="stSelectbox"] button svg, [data-testid="stMultiSelect"] button svg {{ fill: var(--text2) !important; color: var(--text2) !important; }}
label:has(input[role="switch"]) > div:first-of-type {{ background: var(--border2) !important; }}
label:has(input[role="switch"]:checked) > div:first-of-type {{ background: var(--accent) !important; }}
label:has(input[role="switch"]) > div:first-of-type > div {{ background: #ffffff !important; box-shadow: 0 1px 3px rgba(0,0,0,.35); }}

/* inputs (legacy selectors) */
.stTextInput input, .stNumberInput input, .stTextArea textarea, [data-baseweb="select"] > div, [data-baseweb="input"] > div {{
  background: var(--card2) !important; color: var(--text) !important; border-color: var(--border2) !important; border-radius: 12px !important; }}
.stSelectbox div[data-baseweb="select"] span, .stMultiSelect span {{ color: var(--text) !important; }}
[data-baseweb="popover"] * {{ color: var(--text); }} [data-baseweb="popover"] ul {{ background: var(--card2) !important; }}
.stButton > button {{ border-radius: 12px; border:1px solid var(--border2); background: var(--card2); color: var(--text); font-weight:500; padding:.45rem 1rem; }}
.stButton > button:hover {{ border-color: var(--accent); color: var(--text); }}
.stButton > button[kind="primary"] {{ background: linear-gradient(135deg,{T['accent']},{T['accent2']}); color:#04110b; border:none; font-weight:600; }}
.stDownloadButton > button {{ border-radius:12px; border:1px solid var(--border2); background:var(--card2); color:var(--text); font-weight:500; }}
.stDownloadButton > button:hover {{ border-color:var(--accent); color:var(--text); }}
[data-testid="stFileUploaderDropzone"] {{ background: var(--card2); border:1.5px dashed var(--border2); border-radius:16px; }}
[data-testid="stFileUploaderDropzone"] * {{ color: var(--text2) !important; }}
.stTabs [data-baseweb="tab-list"] {{ gap:6px; border-bottom:1px solid var(--border); }}
.stTabs [data-baseweb="tab"] {{ background:transparent; border-radius:10px 10px 0 0; color:var(--text2); padding:8px 14px; }}
.stTabs [aria-selected="true"] {{ color:var(--text) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: var(--accent); }}
.stSlider [data-baseweb="slider"] div[role="slider"] {{ background: var(--accent); }}
[data-testid="stExpander"] {{ border:1px solid var(--border); border-radius:14px; background:var(--card); }}
[data-testid="stExpander"] summary p {{ color:var(--text); font-weight:500; }}
[data-testid="stMetric"] {{ background:var(--card2); border:1px solid var(--border); border-radius:14px; padding:10px 14px; }}
[data-testid="stMetricValue"] {{ color:var(--text); }} [data-testid="stMetricLabel"] p {{ color:var(--text2); }}
.stAlert {{ border-radius:14px; }}
div[data-testid="stDataFrame"] {{ border-radius:14px; overflow:hidden; border:1px solid var(--border); }}

/* html tables */
.tbl-wrap {{ overflow:auto; max-height:560px; border:1px solid var(--border); border-radius:14px; }}
table.fin {{ border-collapse:separate; border-spacing:0; width:100%; font-size:12.5px; font-variant-numeric:tabular-nums; }}
table.fin th {{ position:sticky; top:0; background:var(--card2); color:var(--text2); font-weight:600; padding:9px 12px; text-align:right; border-bottom:1px solid var(--border2); z-index:2; white-space:nowrap; }}
table.fin th:first-child, table.fin td:first-child {{ text-align:left; position:sticky; left:0; background:var(--card); z-index:1; min-width:210px; }}
table.fin th:first-child {{ background:var(--card2); z-index:3; }}
table.fin td {{ padding:7px 12px; text-align:right; border-bottom:1px solid var(--border); color:var(--text); white-space:nowrap; }}
table.fin td {{ background-color:var(--card); }}
table.fin tr.tot td {{ font-weight:600; background-color:var(--card); background-image:linear-gradient({'rgba(34,197,139,.06)' if dark else 'rgba(15,157,106,.06)'},{'rgba(34,197,139,.06)' if dark else 'rgba(15,157,106,.06)'}); }}
table.fin tr:hover td {{ background-color:var(--card2); background-image:none; }}
table.fin td.neg {{ color:var(--neg); }} table.fin td.proj, table.fin th.proj {{ color:var(--accent); }}
@media (max-width: 900px) {{ .kpi-value {{ font-size:24px; }} .block-container {{ padding-left:1rem; padding-right:1rem; }} }}
</style>
"""


def card(name: str | None = None):
    """A themed card container (CSS keys off the 'card' prefix)."""
    return st.container(key=f"card_{name or ''}{next(_counter)}")


def pill(value, suffix="%", good_up=True, decimals=1) -> str:
    if is_nan(value):
        return "<span class='pill flat'>–</span>"
    if abs(value) < 0.05:
        return f"<span class='pill flat'>→ {value:+.{decimals}f}{suffix}</span>"
    up = value > 0
    good = up == good_up
    cls = "up" if good else "down"
    arrow = "↗" if up else "↘"
    return f"<span class='pill {cls}'>{arrow} {abs(value):.{decimals}f}{suffix}</span>"


def kpi_head(label: str, value: str, delta_html: str, sub: str = ""):
    st.markdown(f"<div class='card-title'><span>{html.escape(label)}</span><span class='dots'>···</span></div>"
                f"<div class='kpi-value'>{value}</div><div>{delta_html} <span class='card-sub'>{html.escape(sub)}</span></div>", unsafe_allow_html=True)


def card_title(title: str, sub: str = "", right: str = ""):
    st.markdown(f"<div class='card-title'><span style='color:var(--text);font-weight:600;font-size:15px'>{html.escape(title)}</span>"
                f"<span style='color:var(--muted);font-size:12px'>{right}</span></div>"
                + (f"<div class='card-sub'>{html.escape(sub)}</div>" if sub else ""), unsafe_allow_html=True)


def html_table(df: pd.DataFrame, d: int = 1, total_rows: tuple = ("total", "net profit", "profit before", "sales", "revenue", "ebitda", "pat"),
               proj_cols: tuple = (), pct_rows: tuple = ()) -> str:
    cols = list(df.columns)
    head = "<tr><th></th>" + "".join(f"<th class='{'proj' if c in proj_cols else ''}'>{html.escape(str(c))}</th>" for c in cols) + "</tr>"
    body = []
    for idx in df.index:
        is_tot = str(idx).lower().startswith(total_rows)
        cells = []
        for c in cols:
            v = df.loc[idx, c]
            if is_nan(v) or v == "":
                cells.append("<td>–</td>")
                continue
            if isinstance(v, str):
                cells.append(f"<td>{html.escape(v)}</td>")
                continue
            if abs(v) < 0.005:
                v = 0.0
            neg = "neg" if v < 0 else ""
            dd = 2 if (abs(v) < 20 and not float(v).is_integer() and str(idx) not in pct_rows) else d
            suffix = "%" if "%" in str(idx) else "x" if any(t in str(idx) for t in ("/ ", "Coverage", "Turnover", "Multiplier")) else ""
            cells.append(f"<td class='{neg} {'proj' if c in proj_cols else ''}'>{v:,.{dd}f}{suffix}</td>")
        body.append(f"<tr class='{'tot' if is_tot else ''}'><td>{html.escape(str(idx))}</td>{''.join(cells)}</tr>")
    return f"<div class='tbl-wrap'><table class='fin'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>"


def list_rows(rows: list[tuple[str, str, str, str]]) -> str:
    """(icon, title, subtitle, value) -> 'Recent activity' style list."""
    return "".join(f"<div class='row-item'><div class='row-ic'>{ic}</div><div class='row-main'><b>{html.escape(t)}</b><small>{html.escape(s)}</small></div>"
                   f"<div class='row-val'>{v}</div></div>" for ic, t, s, v in rows)


def check_rows(checks: list[dict]) -> str:
    out = []
    for c in checks:
        cls, ic = ("ok", "✓") if c["pass"] is True else ("no", "✕") if c["pass"] is False else ("na", "–")
        out.append(f"<div class='check'><div class='ic {cls}'>{ic}</div><div>{html.escape(c['check'])}<small>{html.escape(c['detail'])}</small></div></div>")
    return "".join(out)


PLOT_CFG = {"displayModeBar": False, "responsive": True}
