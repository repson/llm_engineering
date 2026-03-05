"""
charts.py — Plotly chart factories for the Analytics Dashboard.

All public functions accept the `memory` list (List[Opportunity])
and/or `tracked_products` list (List[TrackedProduct]) and return
a plotly.graph_objects.Figure.  They handle empty-data gracefully.

Note on technology choice:
    Plotly (already a project dependency) is used here rather than
    Plotly Dash or Altair because Gradio's gr.Plot component renders
    Plotly figures natively.  Plotly Dash requires a separate WSGI
    server that cannot be embedded inside a Gradio app.  Altair
    figures would need to be converted to SVG/HTML images, losing
    interactivity.  Plotly gives us the same expressive power with
    zero additional infrastructure.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import List, Optional, TYPE_CHECKING

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --------------------------------------------------------------------------- #
# Theme                                                                        #
# --------------------------------------------------------------------------- #

BG       = "#1a1a2e"
CARD_BG  = "#16213e"
GRID     = "#2a2a4a"
TEXT     = "#eaeaea"
PRIMARY  = "#e94560"
ACCENT   = "#4ECDC4"
ACCENT2  = "#45B7D1"
FONT     = "Inter, system-ui, sans-serif"

CATEGORY_PALETTE = {
    "Electronics":   "#4ECDC4",
    "Computers":     "#45B7D1",
    "Automotive":    "#96CEB4",
    "Smart Home":    "#FFEAA7",
    "Home & Garden": "#DDA0DD",
    "Other":         "#B0B0B0",
}

DEALNEWS_MAP = {
    "c142": "Electronics",
    "Electronics": "Electronics",
    "c39": "Computers",
    "Computers": "Computers",
    "c238": "Automotive",
    "Automotive": "Automotive",
    "f1912": "Smart Home",
    "Smart-Home": "Smart Home",
    "c196": "Home & Garden",
    "Home-Garden": "Home & Garden",
}


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def infer_category(url: str) -> str:
    for key, cat in DEALNEWS_MAP.items():
        if key in url:
            return cat
    return "Other"


def _base(height: int = 360, **kwargs) -> dict:
    """Return a dict of common dark-theme layout properties."""
    return dict(
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(color=TEXT, family=FONT, size=12),
        title_font=dict(size=15, color=TEXT, family=FONT),
        margin=dict(l=45, r=25, t=52, b=42),
        height=height,
        **kwargs,
    )


def _xaxis(title: str = "") -> dict:
    return dict(title=title, gridcolor=GRID, zerolinecolor=GRID, tickfont_color=TEXT)


def _yaxis(title: str = "") -> dict:
    return dict(title=title, gridcolor=GRID, zerolinecolor=GRID, tickfont_color=TEXT)


def _legend() -> dict:
    return dict(bgcolor="rgba(0,0,0,0)", bordercolor=GRID, font_color=TEXT)


def _empty(title: str, msg: str = "No data yet — run the deal hunter first") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=msg, xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=15, color="#666"),
    )
    fig.update_layout(
        **_base(title=title),
        xaxis_visible=False, yaxis_visible=False,
    )
    return fig


def _normalise(values: List[float]) -> List[float]:
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


# =========================================================================== #
# 1. Price Distribution — Overlapping histogram (deal price vs. estimate)      #
# =========================================================================== #

def price_distribution(memory) -> go.Figure:
    """
    Overlapping histogram that compares actual deal prices against the
    ensemble model's estimated fair values.  The gap between the two
    distributions tells us how underpriced the deals are on average.
    """
    if not memory:
        return _empty("Price Distribution")

    prices    = [o.deal.price for o in memory]
    estimates = [o.estimate   for o in memory]
    nbins     = min(25, max(5, len(memory) // 2))

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=prices, name="Deal Price",
        nbinsx=nbins,
        marker_color=PRIMARY, opacity=0.75,
    ))
    fig.add_trace(go.Histogram(
        x=estimates, name="Estimated Value",
        nbinsx=nbins,
        marker_color=ACCENT, opacity=0.65,
    ))

    # Median lines
    for val, color, label in [
        (np.median(prices),    PRIMARY, f"Median price ${np.median(prices):.0f}"),
        (np.median(estimates), ACCENT,  f"Median est.  ${np.median(estimates):.0f}"),
    ]:
        fig.add_vline(
            x=val, line_dash="dash", line_color=color,
            annotation_text=label,
            annotation_font_color=color,
            annotation_position="top right",
        )

    fig.update_layout(
        **_base(title="Price Distribution"),
        barmode="overlay",
        xaxis=_xaxis("Price ($)"),
        yaxis=_yaxis("Number of Deals"),
        legend=_legend(),
    )
    return fig


# =========================================================================== #
# 2. Discount Trends — Scatter + lines, coloured by category                  #
# =========================================================================== #

def discount_trends(memory) -> go.Figure:
    """
    Each deal is plotted on the x-axis in chronological order (by index,
    since we do not always have a timestamp) and the y-axis shows the
    discount in dollars.  Traces are broken out by product category.
    """
    if not memory:
        return _empty("Discount Trends by Category")

    by_cat: dict[str, list] = defaultdict(list)
    for i, opp in enumerate(memory):
        cat = infer_category(opp.deal.url)
        by_cat[cat].append((i + 1, opp.discount, opp.deal.product_description[:40]))

    fig = go.Figure()
    for cat, points in by_cat.items():
        xs     = [p[0] for p in points]
        ys     = [p[1] for p in points]
        labels = [p[2] for p in points]
        color  = CATEGORY_PALETTE.get(cat, "#B0B0B0")
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="lines+markers",
            name=cat,
            text=labels,
            hovertemplate="<b>%{text}</b><br>Deal #%{x} — $%{y:.2f} discount<extra></extra>",
            marker=dict(size=9, color=color, line=dict(width=1, color="#111")),
            line=dict(color=color, width=1.5, dash="dot"),
        ))

    fig.add_hline(
        y=50, line_dash="longdash", line_color="#555",
        annotation_text="$50 threshold",
        annotation_font_color="#555",
    )

    fig.update_layout(
        **_base(title="Discount Trends by Category"),
        xaxis=_xaxis("Deal #"),
        yaxis=_yaxis("Discount ($)"),
        legend=_legend(),
    )
    return fig


# =========================================================================== #
# 3. Deal Quality Radar — Portfolio average vs. best single deal               #
# =========================================================================== #

def deal_quality_radar(memory) -> go.Figure:
    """
    Four normalised quality dimensions for every deal in memory:
        • Affordability  — lower deal price scores higher
        • Discount $     — raw saving in dollars
        • Value Ratio    — estimate / price  (how underpriced it is)
        • Description    — length of product description (proxy for info quality)

    Two traces: the portfolio average and the single best deal.
    """
    if len(memory) < 2:
        return _empty("Deal Quality Radar", "Need at least 2 deals to draw the radar")

    prices    = [o.deal.price   for o in memory]
    discounts = [o.discount     for o in memory]
    estimates = [o.estimate     for o in memory]
    descs     = [len(o.deal.product_description) for o in memory]
    ratios    = [e / max(p, 1) for e, p in zip(estimates, prices)]

    afford_n  = [1 - v for v in _normalise(prices)]
    disc_n    = _normalise(discounts)
    ratio_n   = _normalise(ratios)
    desc_n    = _normalise(descs)

    dims   = ["Affordability", "Discount $", "Value Ratio", "Description Quality"]
    n      = len(memory)

    avg    = [sum(afford_n)/n, sum(disc_n)/n, sum(ratio_n)/n, sum(desc_n)/n]
    best_i = max(range(n), key=lambda i: discounts[i])
    best   = [afford_n[best_i], disc_n[best_i], ratio_n[best_i], desc_n[best_i]]

    # Close the polygon
    theta  = dims + [dims[0]]
    avg   += [avg[0]]
    best  += [best[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=avg, theta=theta, fill="toself", name="Portfolio Avg",
        fillcolor=f"rgba(233,69,96,0.20)",
        line=dict(color=PRIMARY, width=2),
    ))
    fig.add_trace(go.Scatterpolar(
        r=best, theta=theta, fill="toself", name="Best Deal",
        fillcolor=f"rgba(78,205,196,0.15)",
        line=dict(color=ACCENT, width=2),
    ))

    fig.update_layout(
        **_base(title="🎯 Deal Quality Radar"),
        polar=dict(
            bgcolor=CARD_BG,
            radialaxis=dict(
                visible=True, range=[0, 1],
                gridcolor=GRID, tickfont=dict(color=TEXT), showticklabels=False,
            ),
            angularaxis=dict(gridcolor=GRID, tickfont=dict(color=TEXT, size=11)),
        ),
        legend=_legend(),
    )
    return fig


# =========================================================================== #
# 4. Savings Over Time — Cumulative area + per-deal bar (dual axis)            #
# =========================================================================== #

def savings_over_time(memory) -> go.Figure:
    """
    Dual-axis chart:
        • Left  Y — cumulative savings (area trace)
        • Right Y — individual deal discount (bar trace)
    """
    if not memory:
        return _empty("Savings Over Time")

    indices    = list(range(1, len(memory) + 1))
    individual = [max(o.discount, 0) for o in memory]
    cumulative = []
    running    = 0.0
    for d in individual:
        running += d
        cumulative.append(running)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Scatter(
        x=indices, y=cumulative,
        fill="tozeroy",
        fillcolor=f"rgba(78,205,196,0.18)",
        line=dict(color=ACCENT, width=2.5),
        mode="lines+markers",
        marker=dict(size=7, color=ACCENT),
        name="Cumulative ($)",
        hovertemplate="After deal #%{x}: total saved $%{y:.2f}<extra></extra>",
    ), secondary_y=False)

    fig.add_trace(go.Bar(
        x=indices, y=individual,
        name="Per-deal Discount ($)",
        marker_color=PRIMARY, opacity=0.55,
        hovertemplate="Deal #%{x}: $%{y:.2f} saved<extra></extra>",
    ), secondary_y=True)

    fig.update_layout(
        **_base(title="Cumulative Savings Over Time"),
        barmode="overlay",
        xaxis=dict(title="Deal #", gridcolor=GRID, dtick=1, tickfont_color=TEXT),
        legend=_legend(),
    )
    fig.update_yaxes(
        title_text="Cumulative Savings ($)", secondary_y=False,
        gridcolor=GRID, tickfont_color=TEXT,
    )
    fig.update_yaxes(
        title_text="Per-deal Discount ($)", secondary_y=True,
        showgrid=False, tickfont_color=TEXT,
    )
    return fig


# =========================================================================== #
# 5. Category Breakdown — Donut chart with pull-out for top category           #
# =========================================================================== #

def category_breakdown(memory) -> go.Figure:
    """
    Donut chart showing how many deals come from each RSS feed category.
    The top category is pulled out for emphasis.
    """
    if not memory:
        return _empty("Deals by Category")

    counts: dict[str, int] = defaultdict(int)
    for opp in memory:
        counts[infer_category(opp.deal.url)] += 1

    labels = list(counts.keys())
    values = [counts[l] for l in labels]
    colors = [CATEGORY_PALETTE.get(l, "#B0B0B0") for l in labels]
    max_v  = max(values)
    pull   = [0.08 if v == max_v else 0 for v in values]

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="#111", width=1.5)),
        textinfo="label+percent",
        textfont=dict(size=12, color=TEXT),
        hole=0.42,
        pull=pull,
        hovertemplate="<b>%{label}</b><br>%{value} deals (%{percent})<extra></extra>",
    )])

    fig.update_layout(
        **_base(title="Deals by Category"),
        legend=_legend(),
        annotations=[dict(
            text=f"{len(memory)}<br><span style='font-size:10px'>deals</span>",
            x=0.5, y=0.5, font_size=18, showarrow=False, font_color=TEXT,
        )],
    )
    return fig


# =========================================================================== #
# 6. Tracked Product Price History — Standalone line chart                     #
# =========================================================================== #

def price_history_chart(tracked_product) -> go.Figure:
    """
    Line chart of the price history for a single tracked product.
    Shows the target price as a horizontal dashed line.
    """
    history = getattr(tracked_product, "price_history", [])
    if not history:
        return _empty(
            f"{tracked_product.title[:50]}",
            "No price history yet — click 'Check Prices Now'",
        )

    xs = list(range(1, len(history) + 1))
    ys = [h["price"] for h in history]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="lines+markers",
        name="Price",
        line=dict(color=ACCENT, width=2.5),
        marker=dict(size=8, color=ACCENT, line=dict(width=1, color="#111")),
        fill="tozeroy",
        fillcolor="rgba(78,205,196,0.10)",
        hovertemplate="Check #%{x}: $%{y:.2f}<extra></extra>",
    ))

    if tracked_product.target_price:
        fig.add_hline(
            y=tracked_product.target_price,
            line_dash="dash", line_color="#FFEAA7",
            annotation_text=f"Target ${tracked_product.target_price:.2f}",
            annotation_font_color="#FFEAA7",
            annotation_position="bottom right",
        )

    # Annotate min and max
    if len(ys) >= 2:
        min_y, max_y = min(ys), max(ys)
        min_x = ys.index(min_y) + 1
        max_x = ys.index(max_y) + 1
        for xi, yi, label, color in [
            (min_x, min_y, f"Low ${min_y:.2f}", ACCENT),
            (max_x, max_y, f"High ${max_y:.2f}", PRIMARY),
        ]:
            fig.add_annotation(
                x=xi, y=yi, text=label, showarrow=True,
                arrowcolor=color, font=dict(color=color, size=11),
                ax=20, ay=-30,
            )

    title = f"{tracked_product.title[:55]}"
    fig.update_layout(
        **_base(title=title),
        xaxis=_xaxis("Check #"),
        yaxis=_yaxis("Price ($)"),
        legend=_legend(),
    )
    return fig


# =========================================================================== #
# Summary KPI cards (HTML)                                                     #
# =========================================================================== #

def summary_stats_html(memory) -> str:
    if not memory:
        return (
            '<p style="color:#666;text-align:center;padding:20px;">'
            "No deals found yet. Run the Deal Hunter to populate the dashboard.</p>"
        )

    total_savings = sum(max(o.discount, 0) for o in memory)
    avg_discount  = total_savings / len(memory)
    best          = max(memory, key=lambda o: o.discount)
    avg_price     = sum(o.deal.price for o in memory) / len(memory)
    top_cat       = max(
        set(infer_category(o.deal.url) for o in memory),
        key=lambda c: sum(1 for o in memory if infer_category(o.deal.url) == c),
    )

    cards = [
        ("Total Deals",     str(len(memory))),
        ("Total Savings",   f"${total_savings:,.2f}"),
        ("Avg Discount",    f"${avg_discount:.2f}"),
        ("Best Discount",   f"${best.discount:.2f}"),
        ("Avg Deal Price",  f"${avg_price:.2f}"),
        ("Top Category",    top_cat),
    ]

    def card(label, value):
        return f"""
        <div style="
            flex:1; min-width:130px;
            background:{CARD_BG};
            border:1px solid {GRID};
            border-radius:12px;
            padding:16px 14px;
            text-align:center;
        ">
            <div style="font-size:20px;font-weight:700;color:{ACCENT};margin:4px 0;">{value}</div>
            <div style="font-size:11px;color:#666;">{label}</div>
        </div>"""

    inner = "".join(card(l, v) for l, v in cards)
    return f'<div style="display:flex;flex-wrap:wrap;gap:12px;padding:8px 0;">{inner}</div>'
