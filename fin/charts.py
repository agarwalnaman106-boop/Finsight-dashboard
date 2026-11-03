"""Plotly figure builders. All take a theme token dict `T` (see theme.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .utils import money, pct


def _base(fig: go.Figure, T: dict, height=320, legend=True, title=None) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=34 if title else 12, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, system-ui, sans-serif", color=T["text2"], size=12),
        title=dict(text=title, x=0, font=dict(size=14, color=T["text"])) if title else None,
        legend=dict(orientation="h", y=-0.14, x=0, font=dict(size=11), bgcolor="rgba(0,0,0,0)") if legend else None,
        showlegend=legend, hovermode="x unified",
        hoverlabel=dict(bgcolor=T["card2"], bordercolor=T["border2"], font=dict(color=T["text"], size=12)),
        bargap=0.34,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=T["border"], tickfont=dict(size=11, color=T["text2"]), automargin=True)
    fig.update_yaxes(gridcolor=T["grid"], zeroline=False, linecolor="rgba(0,0,0,0)", tickfont=dict(size=11, color=T["text2"]), automargin=True)
    return fig


def _spark_fill(color: str, a=0.16) -> str:
    c = color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


def sparkline(values, T, up=True, height=46) -> go.Figure:
    v = [x for x in values if pd.notna(x)]
    col = T["pos"] if up else T["neg"]
    fig = go.Figure(go.Scatter(y=v, mode="lines", line=dict(color=col, width=2, shape="spline"), fill="tozeroy" if min(v, default=0) >= 0 else None,
                               fillcolor=_spark_fill(col, 0.12), hoverinfo="skip"))
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(visible=False), yaxis=dict(visible=False, range=[min(v) - (max(v) - min(v)) * 0.15, max(v) * 1.02]), showlegend=False)
    return fig


def bars_with_line(df: pd.DataFrame, bar_cols: list, line_col: str | None, T: dict, title=None, line_name=None, height=330, unit="") -> go.Figure:
    """Grouped bars (absolute) + a % line on a separate small panel below (one axis per panel — no dual axis)."""
    rows = 2 if line_col else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.72, 0.28] if line_col else [1])
    for i, c in enumerate(bar_cols):
        fig.add_trace(go.Bar(x=df.index, y=df[c], name=c, marker=dict(color=T["cat"][i % 6], cornerradius=4),
                             hovertemplate=f"{c}: %{{y:,.0f}}{unit}<extra></extra>"), row=1, col=1)
    if line_col:
        fig.add_trace(go.Scatter(x=df.index, y=df[line_col], name=line_name or line_col, mode="lines+markers",
                                 line=dict(color=T["lime"], width=2.2), marker=dict(size=7, line=dict(color=T["card"], width=2)),
                                 hovertemplate=f"{line_name or line_col}: %{{y:.1f}}%<extra></extra>"), row=2, col=1)
    _base(fig, T, height=height, title=title)
    fig.update_yaxes(gridcolor=T["grid"], zeroline=False)
    if line_col:
        fig.update_yaxes(nticks=3, row=2, col=1)
    fig.update_layout(barmode="group")
    return fig


def area_line(df: pd.DataFrame, cols: list, T: dict, title=None, height=300, suffix="%", fill_first=True) -> go.Figure:
    fig = go.Figure()
    for i, c in enumerate(cols):
        col = T["cat"][i % 6] if i else T["accent"]
        fig.add_trace(go.Scatter(x=df.index, y=df[c], name=c, mode="lines+markers", line=dict(color=col, width=2.4, shape="spline", smoothing=0.6),
                                 marker=dict(size=6, line=dict(color=T["card"], width=2)),
                                 fill="tozeroy" if (i == 0 and fill_first) else None, fillcolor=_spark_fill(col, 0.12),
                                 hovertemplate=f"{c}: %{{y:,.1f}}{suffix}<extra></extra>"))
    return _base(fig, T, height=height, title=title)


def cashflow_chart(df: pd.DataFrame, T: dict, height=340) -> go.Figure:
    """Tall focus chart like the reference image: smooth area + comparison line, with a dashed 'now' marker."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["CFO"], name="Operating cash flow", mode="lines", line=dict(color=T["accent"], width=2.6, shape="spline"),
                             fill="tozeroy", fillcolor=_spark_fill(T["accent"], 0.14), hovertemplate="Operating: %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=df.index, y=df["FCF"], name="Free cash flow", mode="lines", line=dict(color=T["lime"], width=2.4, shape="spline"),
                             hovertemplate="Free cash flow: %{y:,.0f}<extra></extra>"))
    if len(df):
        last = df.index[-1]
        fig.add_vline(x=last, line=dict(color=T["accent"], width=1.4, dash="dash"))
        fig.add_trace(go.Scatter(x=[last], y=[df["FCF"].iloc[-1]], mode="markers", marker=dict(color=T["lime"], size=11, line=dict(color=T["card"], width=3)),
                                 showlegend=False, hoverinfo="skip"))
    return _base(fig, T, height=height)


def donut(labels, values, T, title=None, height=300, center=None, colors=None) -> go.Figure:
    tot = float(sum(values)) or 1.0
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.64, sort=False, direction="clockwise",
                           marker=dict(colors=(colors or (T["cat"] + ["#6b7973", "#4b5853"]))[: len(values)], line=dict(color=T["card"], width=3)),
                           text=[f"{v / tot * 100:.0f}%" if v / tot >= 0.07 else "" for v in values], textinfo="text", textposition="inside",
                           textfont=dict(color="#ffffff", size=11), insidetextorientation="horizontal",
                           hovertemplate="%{label}: %{value:,.0f} (%{percent})<extra></extra>"))
    _base(fig, T, height=height, title=title)
    fig.update_layout(legend=dict(orientation="h", x=0, y=-0.02, yanchor="top", font=dict(size=10.5)), hovermode="closest",
                      margin=dict(l=4, r=4, t=34 if title else 4, b=4))
    if center:
        fig.add_annotation(text=center, x=0.5, y=0.5, showarrow=False, font=dict(size=15, color=T["text"]), xref="paper", yref="paper")
    return fig


def waterfall(items: list, T: dict, title=None, height=330) -> go.Figure:
    """items: [(label, value, kind)] kind in absolute|relative|total"""
    run, texts = 0.0, []
    for _, v, k in items:
        run = v if k == "absolute" else run + v if k == "relative" else run
        texts.append(f"{(v if k != 'total' else run):,.0f}")
    fig = go.Figure(go.Waterfall(
        x=[i[0] for i in items], y=[i[1] for i in items], measure=[i[2] for i in items],
        connector=dict(line=dict(color=T["border2"], width=1)),
        increasing=dict(marker=dict(color=T["accent"])), decreasing=dict(marker=dict(color=T["neg"])),
        totals=dict(marker=dict(color=T["cat"][2])), text=texts, textposition="outside", textfont=dict(size=10, color=T["text2"]),
        hovertemplate="%{x}: %{text}<extra></extra>"))
    _base(fig, T, height=height, legend=False, title=title).update_layout(hovermode="closest")
    fig.update_xaxes(tickangle=-35, tickfont=dict(size=10))
    return fig


def stacked(df: pd.DataFrame, cols: list, T: dict, title=None, height=320, percent=False) -> go.Figure:
    fig = go.Figure()
    d = df[cols].copy()
    if percent:
        d = d.div(d.sum(axis=1), axis=0) * 100
    for i, c in enumerate(cols):
        fig.add_trace(go.Bar(x=d.index, y=d[c], name=c, marker=dict(color=T["cat"][i % 6] if i < 6 else "#6b7973", line=dict(color=T["card"], width=1.5)),
                             hovertemplate=f"{c}: %{{y:,.1f}}{'%' if percent else ''}<extra></extra>"))
    _base(fig, T, height=height, title=title)
    fig.update_layout(barmode="stack", bargap=0.28)
    return fig


def gauge(value, lo, hi, T, title, height=190, suffix="") -> go.Figure:
    fig = go.Figure(go.Indicator(mode="gauge+number", value=value if pd.notna(value) else 0,
                                 number=dict(suffix=suffix, font=dict(size=24, color=T["text"])),
                                 title=dict(text=title, font=dict(size=12, color=T["text2"])),
                                 gauge=dict(axis=dict(range=[lo, hi], tickfont=dict(size=9, color=T["muted"])), bar=dict(color=T["accent"], thickness=0.28),
                                            bgcolor=T["card2"], borderwidth=0)))
    fig.update_layout(height=height, margin=dict(l=18, r=18, t=36, b=0), paper_bgcolor="rgba(0,0,0,0)", font=dict(color=T["text2"]))
    return fig


def heatmap(grid: pd.DataFrame, T: dict, title=None, height=300, fmt=",.0f", mid=None) -> go.Figure:
    z = grid.values.astype(float)
    fig = go.Figure(go.Heatmap(z=z, x=list(grid.columns), y=list(grid.index), colorscale=[[0, T["seq"][0]], [0.5, T["seq"][2]], [1, T["seq"][3]]],
                               text=[[format(v, fmt) if pd.notna(v) else "" for v in r] for r in z], texttemplate="%{text}", textfont=dict(size=12, color="#ffffff" if T["mode"] == "dark" else "#0d1512"),
                               showscale=False, hovertemplate="WACC %{y} · g %{x}: %{text}<extra></extra>", xgap=3, ygap=3))
    _base(fig, T, height=height, legend=False, title=title).update_layout(hovermode="closest")
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    return fig


def dupont_tree(L: pd.Series, T: dict) -> go.Figure:
    labels = ["ROE", "Net margin", "Asset turnover", "Equity multiplier"]
    vals = [L.get("ROE %"), L.get("Net Margin %"), L.get("Asset Turnover"), L.get("Equity Multiplier")]
    fmt = [f"{vals[0]:.1f}%", f"{vals[1]:.1f}%", f"{vals[2]:.2f}x", f"{vals[3]:.2f}x"]
    fig = go.Figure()
    pos = [(0.5, 0.82), (0.17, 0.2), (0.5, 0.2), (0.83, 0.2)]
    for i in (1, 2, 3):
        fig.add_shape(type="line", x0=pos[0][0], y0=pos[0][1] - 0.1, x1=pos[i][0], y1=pos[i][1] + 0.12, line=dict(color=T["border2"], width=1.5), xref="paper", yref="paper")
    for i, (lab, f) in enumerate(zip(labels, fmt)):
        fig.add_annotation(x=pos[i][0], y=pos[i][1], xref="paper", yref="paper", showarrow=False, align="center",
                           text=f"<span style='font-size:11px;color:{T['muted']}'>{lab}</span><br> <br><b style='font-size:20px;color:{T['text']}'>{f}</b>",
                           bgcolor=T["card2"], bordercolor=T["accent"] if i == 0 else T["border2"], borderwidth=1, borderpad=10)
    fig.add_annotation(x=0.335, y=0.5, xref="paper", yref="paper", text="×", showarrow=False, font=dict(color=T["muted"], size=16))
    fig.add_annotation(x=0.665, y=0.5, xref="paper", yref="paper", text="×", showarrow=False, font=dict(color=T["muted"], size=16))
    fig.update_layout(height=250, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def radar(scores: dict, T: dict, height=300) -> go.Figure:
    cats = list(scores)
    fig = go.Figure(go.Scatterpolar(r=list(scores.values()) + [list(scores.values())[0]], theta=cats + [cats[0]], fill="toself",
                                    line=dict(color=T["accent"], width=2), fillcolor=_spark_fill(T["accent"], 0.2),
                                    hovertemplate="%{theta}: %{r:.0f}/100<extra></extra>"))
    fig.update_layout(height=height, margin=dict(l=36, r=36, t=14, b=14), paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
                      font=dict(color=T["text2"], size=11),
                      polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(range=[0, 100], gridcolor=T["grid"], tickfont=dict(size=8, color=T["muted"]), linecolor=T["grid"]),
                                 angularaxis=dict(gridcolor=T["grid"], linecolor=T["grid"])))
    return fig


def projection_chart(hist: pd.DataFrame, proj_pl: pd.DataFrame, base_label: str, labels: list, T: dict, metric="Revenue", height=320) -> go.Figure:
    fig = go.Figure()
    h = hist[metric].dropna().tail(8)
    fig.add_trace(go.Bar(x=list(h.index), y=h.values, name="Actual", marker=dict(color=T["cat"][0], cornerradius=4), hovertemplate="%{x}: %{y:,.0f}<extra>Actual</extra>"))
    fig.add_trace(go.Bar(x=labels, y=proj_pl.loc[metric, labels].values, name="Projected", marker=dict(color=T["accent"], opacity=0.55, cornerradius=4,
                                                                                                       line=dict(color=T["accent"], width=1.5)),
                         hovertemplate="%{x}: %{y:,.0f}<extra>Projected</extra>"))
    fig.add_vline(x=len(h) - 0.5, line=dict(color=T["muted"], width=1, dash="dot"))
    return _base(fig, T, height=height, title=f"{metric}: actual and projected").update_layout(barmode="overlay")


def scenario_chart(summary: pd.DataFrame, T: dict, price=None, height=300) -> go.Figure:
    vals = summary.loc["Value / share"]
    colors = [T["neg"], T["cat"][2], T["accent"]]
    fig = go.Figure(go.Bar(x=list(vals.index), y=vals.values, marker=dict(color=colors[: len(vals)], cornerradius=6), text=[f"₹{v:,.0f}" for v in vals.values],
                           textposition="outside", textfont=dict(color=T["text"]), hovertemplate="%{x}: ₹%{y:,.0f}<extra></extra>"))
    if price:
        fig.add_hline(y=price, line=dict(color=T["lime"], width=1.6, dash="dash"), annotation_text=f"Market ₹{price:,.0f}", annotation_font=dict(color=T["lime"]), annotation_position="top left")
    return _base(fig, T, height=height, legend=False, title="DCF value per share by scenario").update_layout(hovermode="closest")


def compare_bar(df: pd.DataFrame, metric: str, T: dict, height=300, suffix="") -> go.Figure:
    d = df[metric].dropna().sort_values(ascending=True)
    fig = go.Figure(go.Bar(x=d.values, y=list(d.index), orientation="h", marker=dict(color=[T["accent"] if i == len(d) - 1 else T["cat"][2] for i in range(len(d))], cornerradius=5),
                           text=[f"{v:,.1f}{suffix}" for v in d.values], textposition="outside", textfont=dict(color=T["text"], size=11),
                           hovertemplate="%{y}: %{x:,.2f}<extra></extra>"))
    _base(fig, T, height=height, legend=False, title=metric).update_layout(hovermode="closest")
    fig.update_xaxes(showgrid=True, gridcolor=T["grid"]); fig.update_yaxes(showgrid=False)
    return fig


def compare_lines(series: dict, T: dict, title: str, height=320, rebase=False) -> go.Figure:
    fig = go.Figure()
    for i, (name, s) in enumerate(series.items()):
        s = s.dropna()
        if rebase and len(s):
            s = s / s.iloc[0] * 100
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode="lines+markers", line=dict(color=T["cat"][i % 6], width=2.4),
                                 marker=dict(size=5), hovertemplate=f"{name}: %{{y:,.1f}}<extra></extra>"))
    return _base(fig, T, height=height, title=title)
