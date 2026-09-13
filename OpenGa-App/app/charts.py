"""
Altair chart builders.

Palette is the validated three-slot categorical set (blue / orange / aqua),
which clears the all-pairs colour-vision and normal-vision floors on the light
surface. Aqua sits below 3:1 against the surface, so every chart that uses it
ships a legend AND the underlying table, which is the relief that WARN
requires.

House rules followed here: one y-axis per chart, never two; categorical hues
assigned in fixed order and never cycled; thin marks with a 2px gap between
stacked segments; recessive grid; a tooltip on every mark.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
DIVERGE_POS = "#e34948"
DIVERGE_NEG = "#2a78d6"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e6e5e1"

_BASE = {
    "config": {
        "view": {"stroke": "transparent"},
        "axis": {"labelColor": INK2, "titleColor": INK2, "gridColor": GRID,
                 "domainColor": GRID, "tickColor": GRID, "labelFontSize": 11,
                 "titleFontSize": 11, "titleFontWeight": "normal"},
        "legend": {"labelColor": INK2, "titleColor": INK2, "labelFontSize": 11,
                   "titleFontSize": 11, "titleFontWeight": "normal"},
        "title": {"color": INK, "fontSize": 13, "fontWeight": 600, "anchor": "start"},
    }
}


def _cfg(c: alt.Chart) -> alt.Chart:
    return c.configure_view(stroke="transparent").configure_axis(
        labelColor=INK2, titleColor=INK2, gridColor=GRID, domainColor=GRID,
        tickColor=GRID, labelFontSize=11, titleFontSize=11, titleFontWeight="normal"
    ).configure_legend(
        labelColor=INK2, titleColor=INK2, labelFontSize=11, titleFontSize=11,
        titleFontWeight="normal", orient="top", direction="horizontal", offset=6
    ).configure_title(color=INK, fontSize=13, fontWeight=600, anchor="start")


def stacked_by_unit(df: pd.DataFrame, value_cols: list[str], title: str,
                    y_title: str, order: list[str] | None = None) -> alt.Chart:
    """Stacked column by unit operation. Segments carry a 2px surface gap so
    adjacent fills never touch."""
    long = df.melt(id_vars="unit", value_vars=value_cols,
                   var_name="component", value_name="value")
    ch = (alt.Chart(long, title=title)
          .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                    stroke="#fcfcfb", strokeWidth=2)
          .encode(
              x=alt.X("unit:N", sort=order or list(df["unit"]), title=None,
                      axis=alt.Axis(labelAngle=0)),
              y=alt.Y("value:Q", title=y_title, stack="zero"),
              color=alt.Color("component:N",
                              scale=alt.Scale(domain=value_cols, range=SERIES[:len(value_cols)]),
                              title=None),
              order=alt.Order("component:N"),
              tooltip=[alt.Tooltip("unit:N", title="Unit"),
                       alt.Tooltip("component:N", title="Component"),
                       alt.Tooltip("value:Q", title=y_title, format=",.3f")])
          .properties(height=300))
    return _cfg(ch)


def tornado(rows: list[dict], base: float, title: str, x_title: str) -> alt.Chart:
    """Swing about the base case. Diverging pair: blue below, red above."""
    recs = []
    for r in rows:
        for side, v in (("low", r["low"]), ("high", r["high"])):
            recs.append({"label": r["label"], "side": side, "value": v,
                         "delta": v - base, "swing": r["swing"],
                         "input": r["low_input"] if side == "low" else r["high_input"]})
    df = pd.DataFrame(recs)
    order = [r["label"] for r in rows]
    ch = (alt.Chart(df, title=title)
          .mark_bar(cornerRadius=4, height=16, stroke="#fcfcfb", strokeWidth=2)
          .encode(
              y=alt.Y("label:N", sort=order, title=None),
              x=alt.X("delta:Q", title=x_title),
              color=alt.Color("side:N",
                              scale=alt.Scale(domain=["low", "high"],
                                              range=[DIVERGE_NEG, DIVERGE_POS]),
                              legend=alt.Legend(title=None,
                                                labelExpr="datum.label == 'low' "
                                                          "? 'Low input' : 'High input'")),
              tooltip=[alt.Tooltip("label:N", title="Input"),
                       alt.Tooltip("input:Q", title="Input value", format=",.4g"),
                       alt.Tooltip("value:Q", title="Result", format=",.2f"),
                       alt.Tooltip("delta:Q", title="Change vs base", format="+,.2f")])
          .properties(height=max(220, 26 * len(rows))))
    rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(
        color=INK2, strokeWidth=1).encode(x="x:Q")
    return _cfg(ch + rule)


def histogram(bins: list[dict], title: str, x_title: str,
              markers: dict[str, float] | None = None) -> alt.Chart:
    df = pd.DataFrame(bins)
    ch = (alt.Chart(df, title=title)
          .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                    stroke="#fcfcfb", strokeWidth=2, color=SERIES[0])
          .encode(
              x=alt.X("mid:Q", title=x_title, bin="binned",
                      scale=alt.Scale(zero=False)),
              x2="to:Q",
              y=alt.Y("count:Q", title="Trials"),
              tooltip=[alt.Tooltip("from:Q", title="From", format=",.0f"),
                       alt.Tooltip("to:Q", title="To", format=",.0f"),
                       alt.Tooltip("count:Q", title="Trials"),
                       alt.Tooltip("share:Q", title="Share", format=".1%")])
          .properties(height=300))
    layers = [ch]
    if markers:
        md = pd.DataFrame([{"x": v, "label": k} for k, v in markers.items()])
        layers.append(alt.Chart(md).mark_rule(color=INK, strokeWidth=2,
                                              strokeDash=[4, 3])
                      .encode(x="x:Q",
                              tooltip=[alt.Tooltip("label:N"),
                                       alt.Tooltip("x:Q", format=",.1f")]))
        layers.append(alt.Chart(md).mark_text(align="left", dx=5, dy=-6,
                                              color=INK, fontSize=11)
                      .encode(x="x:Q", y=alt.value(0), text="label:N"))
    return _cfg(alt.layer(*layers))


def line(df: pd.DataFrame, x: str, y: str, title: str, x_title: str, y_title: str,
         point_col: str | None = None, marker_x: float | None = None) -> alt.Chart:
    ch = (alt.Chart(df, title=title)
          .mark_line(strokeWidth=2, color=SERIES[0], point=alt.OverlayMarkDef(
              color=SERIES[0], size=60, stroke="#fcfcfb", strokeWidth=2))
          .encode(
              x=alt.X(f"{x}:Q", title=x_title, scale=alt.Scale(zero=False)),
              y=alt.Y(f"{y}:Q", title=y_title, scale=alt.Scale(zero=False)),
              tooltip=[alt.Tooltip(f"{x}:Q", title=x_title, format=",.0f"),
                       alt.Tooltip(f"{y}:Q", title=y_title, format=",.2f")])
          .properties(height=320))
    layers = [ch]
    if marker_x is not None:
        md = pd.DataFrame({"x": [marker_x], "label": ["base case"]})
        layers.append(alt.Chart(md).mark_rule(color=INK2, strokeWidth=1,
                                              strokeDash=[4, 3]).encode(x="x:Q"))
        layers.append(alt.Chart(md).mark_text(align="left", dx=5, dy=-140,
                                              color=INK2, fontSize=11)
                      .encode(x="x:Q", text="label:N"))
    return _cfg(alt.layer(*layers))


def simple_bar(df: pd.DataFrame, x: str, y: str, title: str, x_title: str,
               y_title: str, horizontal: bool = True, fmt: str = ",.2f") -> alt.Chart:
    if horizontal:
        enc = dict(y=alt.Y(f"{x}:N", sort="-x", title=None),
                   x=alt.X(f"{y}:Q", title=y_title))
        h = max(200, 24 * len(df))
    else:
        enc = dict(x=alt.X(f"{x}:N", sort=None, title=None,
                           axis=alt.Axis(labelAngle=0)),
                   y=alt.Y(f"{y}:Q", title=y_title))
        h = 300
    ch = (alt.Chart(df, title=title)
          .mark_bar(cornerRadius=4, color=SERIES[0], stroke="#fcfcfb", strokeWidth=2)
          .encode(tooltip=[alt.Tooltip(f"{x}:N", title=x_title),
                           alt.Tooltip(f"{y}:Q", title=y_title, format=fmt)],
                  **enc)
          .properties(height=h))
    return _cfg(ch)


def grouped_bar(df: pd.DataFrame, cat: str, series: str, value: str, title: str,
                y_title: str, domain: list[str]) -> alt.Chart:
    ch = (alt.Chart(df, title=title)
          .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                    stroke="#fcfcfb", strokeWidth=2)
          .encode(
              x=alt.X(f"{cat}:N", title=None, axis=alt.Axis(labelAngle=0)),
              y=alt.Y(f"{value}:Q", title=y_title),
              xOffset=alt.XOffset(f"{series}:N", sort=domain),
              color=alt.Color(f"{series}:N",
                              scale=alt.Scale(domain=domain, range=SERIES[:len(domain)]),
                              title=None),
              tooltip=[alt.Tooltip(f"{cat}:N"), alt.Tooltip(f"{series}:N"),
                       alt.Tooltip(f"{value}:Q", title=y_title, format=",.2f")])
          .properties(height=300))
    return _cfg(ch)


def waterfall(steps: list[dict], title: str, y_title: str) -> alt.Chart:
    """Policy contribution bridge."""
    df = pd.DataFrame(steps)
    ch = (alt.Chart(df, title=title)
          .mark_bar(cornerRadius=4, stroke="#fcfcfb", strokeWidth=2)
          .encode(
              x=alt.X("label:N", sort=list(df["label"]), title=None,
                      axis=alt.Axis(labelAngle=-20)),
              y=alt.Y("start:Q", title=y_title, scale=alt.Scale(zero=False)),
              y2="end:Q",
              color=alt.Color("kind:N",
                              scale=alt.Scale(domain=["level", "reduction"],
                                              range=[SERIES[0], SERIES[2]]),
                              title=None),
              tooltip=[alt.Tooltip("label:N", title="Step"),
                       alt.Tooltip("value:Q", title=y_title, format=",.2f")])
          .properties(height=320))
    return _cfg(ch)
