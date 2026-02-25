# Analytics Dashboard — Implementation Notes

Visualisation layer added on top of the existing **"The Price is Right"**
agent framework. Introduces a dedicated `📊 Analytics` tab with five
interactive Plotly charts, a KPI summary panel, and an inline price-history
chart inside the Product Tracker tab.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Technology Decision](#2-technology-decision)
3. [Files Changed](#3-files-changed)
   - [New: `charts.py`](#31-new-chartspy)
   - [Modified: `price_is_right_final.py`](#32-modified-price_is_right_finalpy)
4. [Charts Reference](#4-charts-reference)
   - [Price Distribution](#41-price-distribution)
   - [Discount Trends](#42-discount-trends)
   - [Deal Quality Radar](#43-deal-quality-radar)
   - [Savings Over Time](#44-savings-over-time)
   - [Category Breakdown](#45-category-breakdown)
   - [Price History (Product Tracker)](#46-price-history-product-tracker)
5. [KPI Summary Cards](#5-kpi-summary-cards)
6. [Visual Theme](#6-visual-theme)
7. [Data Flow](#7-data-flow)
8. [Empty-State Handling](#8-empty-state-handling)
9. [UI Layout](#9-ui-layout)
10. [Known Limitations & Future Work](#10-known-limitations--future-work)

---

## 1. Overview

The analytics layer reads the same in-memory `List[Opportunity]` that the
deal hunter already produces — no new data sources, no database changes, no
additional API calls.  All five charts are re-generated on demand when the
user clicks **🔄 Refresh Dashboard** or when Gradio loads the tab for the
first time.

```
memory.json  ──►  DealAgentFramework.memory  ──►  charts.py functions  ──►  gr.Plot
                                                        │
tracked_products.json  ──►  tracked_products[]  ──►  price_history_chart()
```

---

## 2. Technology Decision

| Option | Verdict | Reason |
|---|---|---|
| **Plotly** (`plotly.graph_objects`) | ✅ **Chosen** | Already a project dependency; `gr.Plot` renders Plotly figures natively with full interactivity (zoom, pan, hover tooltips) |
| **Plotly Dash** | ❌ Rejected | Requires a separate WSGI server; cannot be embedded inside a running Gradio app without complex IFrame hacks |
| **Altair** | ❌ Rejected | Produces Vega-Lite specs that Gradio can only render as static SVG images, losing all interactivity |
| **Matplotlib / Seaborn** | ❌ Rejected | Static images, no hover, poor dark-mode support |

**Conclusion:** Plotly provides the same expressive power as Dash or Altair
with zero additional infrastructure, which is the right trade-off for a
Gradio-hosted prototype.

---

## 3. Files Changed

### 3.1 New: `charts.py`

A self-contained module that exposes one function per chart.
All functions share a common dark-theme helper layer and handle the empty-data
case gracefully (no crashes; a friendly placeholder message is shown instead).

#### Module structure

```
charts.py
│
├── Theme constants          BG, CARD_BG, GRID, TEXT, PRIMARY, ACCENT, ...
├── Category helpers         DEALNEWS_MAP, CATEGORY_PALETTE, infer_category()
├── Layout helpers           _base(), _xaxis(), _yaxis(), _legend()
├── Empty-state helper       _empty(title, message)
├── Normalisation helper     _normalise(values) → [0, 1]
│
├── price_distribution()     Chart 1 — Overlapping histogram
├── discount_trends()        Chart 2 — Scatter + lines by category
├── deal_quality_radar()     Chart 3 — Polar radar chart
├── savings_over_time()      Chart 4 — Area + bar dual-axis
├── category_breakdown()     Chart 5 — Donut chart
├── price_history_chart()    Chart 6 — Line chart (Product Tracker)
└── summary_stats_html()     KPI cards as HTML string
```

#### Why a separate module?

`price_is_right_final.py` already handles session state, threading, event
wiring, and logging.  Mixing 300 lines of chart code into it would make it
unmaintainable.  `charts.py` can be imported, tested, and iterated on
independently — calling `charts.price_distribution(memory)` in a REPL or
notebook gives the same figure the UI renders.

---

### 3.2 Modified: `price_is_right_final.py`

Three changes were made:

#### a) New import

```python
import charts as ch
```

#### b) UI restructured from 2 tabs to 3 tabs

```
Before                      After
──────────────────          ─────────────────────────────────
🔍 Deal Hunter              🔍 Deal Hunter   (unchanged)
🎯 Product Tracker          📊 Analytics     (new)
                            🎯 Product Tracker + price history chart (enhanced)
```

#### c) Analytics tab — Gradio event wiring

```python
def load_analytics():
    mem = self.get_agent_framework().memory
    return (
        ch.summary_stats_html(mem),     # gr.HTML  — KPI cards
        ch.price_distribution(mem),     # gr.Plot
        ch.category_breakdown(mem),     # gr.Plot
        ch.discount_trends(mem),        # gr.Plot
        ch.savings_over_time(mem),      # gr.Plot
        ch.deal_quality_radar(mem),     # gr.Plot
    )

ui.load(load_analytics, outputs=analytics_outputs)           # on page load
refresh_analytics_btn.click(load_analytics, outputs=...)     # on button click
```

#### d) Product Tracker — price history chart on row select

```python
def on_row_select(evt: gr.SelectData):
    row = evt.index[0]
    product = fw.tracked_products[row]
    return row, ch.price_history_chart(product)

tracked_table.select(on_row_select, outputs=[selected_tracker_row, chart_price_history])
```

Clicking any row in the tracker table now renders that product's full price
history directly below the table — no page reload required.

---

## 4. Charts Reference

### 4.1 Price Distribution

**Type:** Overlapping histogram (`barmode="overlay"`)  
**Data:** `deal.price` (red) vs `estimate` (teal) across all deals in memory  
**Insight:** How underpriced deals are relative to the model's fair-value estimate.
If the teal (estimate) peak sits to the right of the red (price) peak, the
agent is consistently finding below-market deals.

Additional elements:
- Vertical dashed lines at the median of each distribution
- Annotated with `"Median price $X"` / `"Median est. $X"`

```python
fig.add_vline(x=np.median(prices), line_dash="dash", ...)
fig.add_vline(x=np.median(estimates), line_dash="dash", ...)
```

---

### 4.2 Discount Trends

**Type:** Scatter + dashed connector lines  
**Data:** `discount` per deal, coloured by RSS feed category, ordered by deal index  
**Insight:** Whether deal quality (discount size) is improving or deteriorating
over time, and which categories are the best performers.

Category is inferred from the DealNews URL path:

```python
DEALNEWS_MAP = {
    "c142": "Electronics",   # /c142/ in URL
    "c39":  "Computers",
    "c238": "Automotive",
    "f1912":"Smart Home",
    "c196": "Home & Garden",
}
```

A horizontal reference line at `$50` marks the existing
`PlanningAgent.DEAL_THRESHOLD` so users can visually confirm which deals
would have triggered a notification.

---

### 4.3 Deal Quality Radar

**Type:** `go.Scatterpolar` with `fill="toself"`  
**Data:** Four normalised quality dimensions, two traces  
**Insight:** Multi-dimensional quality comparison between the portfolio average
and the single best deal found.

#### Dimensions

| Dimension | Calculation | Interpretation |
|---|---|---|
| **Affordability** | `1 − normalise(price)` | Lower price → higher score |
| **Discount $** | `normalise(discount)` | Larger discount → higher score |
| **Value Ratio** | `normalise(estimate / price)` | More underpriced → higher score |
| **Description Quality** | `normalise(len(description))` | Longer description → proxy for richer product info |

All scores are min-max normalised to `[0, 1]` across the full deal set:

```python
def _normalise(values):
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]
```

Two traces are drawn:
- **Red** — Portfolio average (mean score across all deals)
- **Teal** — Best deal (the highest-discount deal)

Requires at least **2 deals** in memory; otherwise an empty-state placeholder
is shown.

---

### 4.4 Savings Over Time

**Type:** Dual-axis chart (`plotly.subplots.make_subplots(secondary_y=True)`)  
**Data:** Cumulative savings (left Y, teal area) + per-deal discount (right Y, red bars)  
**Insight:** Both the rate at which savings accumulate and the distribution of
individual deal values.

```
Left  Y  → cumulative total saved ($)   — teal filled area
Right Y  → individual deal discount ($) — red semi-transparent bars
```

Only non-negative discounts contribute to the cumulative total (`max(discount, 0)`)
to avoid the curve dipping when a deal is found with a negative discount
(i.e. the item actually costs more than the model estimated).

---

### 4.5 Category Breakdown

**Type:** Donut chart (`go.Pie` with `hole=0.42`)  
**Data:** Count of deals per RSS category  
**Insight:** Which product categories the scanner focuses on most.

Design choices:
- **Donut style** — centre annotation shows total deal count
- **Pull-out** — the top category is slightly pulled outwards (`pull=0.08`)
  to draw the eye to the dominant category
- **Per-category colour palette** — consistent with the colours used in the
  Discount Trends and the 3D vector store scatter plot

---

### 4.6 Price History (Product Tracker)

**Type:** Filled line chart  
**Data:** `TrackedProduct.price_history` — list of `{"timestamp", "price"}` dicts  
**Trigger:** Rendered when the user clicks a row in the Product Tracker table  

Additional elements:
- **Target price** — horizontal dashed yellow line (only if `target_price` is set)
- **Min / Max annotations** — arrows pointing to the lowest and highest recorded
  prices so the user can see the full range at a glance

```python
if tracked_product.target_price:
    fig.add_hline(y=tracked_product.target_price, line_dash="dash", ...)

# Annotate min and max
fig.add_annotation(x=min_x, y=min_y, text=f"Low ${min_y:.2f}", ...)
fig.add_annotation(x=max_x, y=max_y, text=f"High ${max_y:.2f}", ...)
```

---

## 5. KPI Summary Cards

`summary_stats_html()` returns a flex-box HTML string with six metric cards:

| Card | Value |
|---|---|
| 🏆 Total Deals | `len(memory)` |
| 💰 Total Savings | `sum(max(discount, 0))` |
| 📊 Avg Discount | `total_savings / len(memory)` |
| 🚀 Best Discount | `max(o.discount for o in memory)` |
| 🏷️ Avg Deal Price | `mean(o.deal.price)` |
| 📦 Top Category | Mode of inferred categories |

Cards are rendered as `gr.HTML` (not `gr.Dataframe`) because they need custom
styling — colour, typography, emoji, responsive flex layout — that a Dataframe
does not support.

---

## 6. Visual Theme

All charts share a common dark theme defined by constants at the top of
`charts.py`:

```python
BG      = "#1a1a2e"   # Page / paper background
CARD_BG = "#16213e"   # Chart interior background
GRID    = "#2a2a4a"   # Grid lines and borders
TEXT    = "#eaeaea"   # All axis labels and annotations
PRIMARY = "#e94560"   # Red — deals, prices, "bad" (expensive)
ACCENT  = "#4ECDC4"   # Teal — estimates, savings, "good" (cheap)
FONT    = "Inter, system-ui, sans-serif"
```

The `_base()` helper applies these to every chart so they are visually
consistent with the existing log panel (`background-color: #222229`) and the
3D vector store scatter plot already present in the Deal Hunter tab.

---

## 7. Data Flow

```
                         ┌────────────────────────────────────────┐
                         │              charts.py                  │
                         │                                        │
memory (List[Opp])  ───► │  price_distribution()  → go.Figure    │
                         │  discount_trends()      → go.Figure    │
                         │  deal_quality_radar()   → go.Figure    │
                         │  savings_over_time()    → go.Figure    │
                         │  category_breakdown()   → go.Figure    │
                         │  summary_stats_html()   → str (HTML)   │
                         │                                        │
tracked_products    ───► │  price_history_chart()  → go.Figure    │
                         └────────────────────────────────────────┘
                                         │
                                         ▼
                              gr.Plot / gr.HTML components
                              (Gradio renders Plotly natively)
```

No network calls, no model inference, no disk I/O happen during chart
generation — it is purely a transformation of data already in RAM.

---

## 8. Empty-State Handling

Every chart function checks for sufficient data before attempting to render:

```python
# Example from price_distribution()
if not memory:
    return _empty("💰 Price Distribution")

# Example from deal_quality_radar()
if len(memory) < 2:
    return _empty("🎯 Deal Quality Radar", "Need at least 2 deals to draw the radar")
```

`_empty()` returns a blank `go.Figure` with a centred annotation message,
matching the dark theme. This prevents `ZeroDivisionError`, `IndexError`, and
`ValueError` exceptions that would crash the Gradio event handler and display
an unformatted Python traceback to the user.

---

## 9. UI Layout

```
📊 Analytics tab
│
├── [ 🔄 Refresh Dashboard ]  button
│
├── KPI cards (HTML flex row)
│     🏆 Deals | 💰 Savings | 📊 Avg Discount | 🚀 Best | 🏷️ Avg Price | 📦 Top Cat
│
├── Row 1  ┌──────────────────────┐  ┌──────────────────────┐
│          │ Price Distribution   │  │ Category Breakdown   │
│          │ (Histogram)          │  │ (Donut)              │
│          └──────────────────────┘  └──────────────────────┘
│
├── Row 2  ┌──────────────────────┐  ┌──────────────────────┐
│          │ Discount Trends      │  │ Savings Over Time    │
│          │ (Scatter by cat.)    │  │ (Area + Bar)         │
│          └──────────────────────┘  └──────────────────────┘
│
└── Row 3  ┌──────────────────────┐  ┌──────────────────────┐
           │ Deal Quality Radar   │  │ How to read (guide)  │
           │ (Polar)              │  │ (Markdown)           │
           └──────────────────────┘  └──────────────────────┘

🎯 Product Tracker tab (enhanced)
│
├── [same as before — add form, table, refresh, remove]
│
└── Price History chart  ← appears when a row is clicked
      (Line + target line + min/max annotations)
```

---

## 10. Known Limitations & Future Work

| Limitation | Impact | Suggested fix |
|---|---|---|
| No timestamps on `Opportunity` objects | X-axis shows deal index, not date/time | Add `timestamp: Optional[str]` field to `Opportunity`; set it in `DealAgentFramework.run()` |
| Category inferred from DealNews URL | Breaks if feed URLs change; always "Other" for non-DealNews sources | Store category in `Deal` model; populate in `ScannerAgent` response |
| `deal_quality_radar` "Description Quality" dimension | Longer description ≠ necessarily better deal | Use an LLM quality score or structured product attributes |
| No real-time chart updates during a hunt | Charts only update after full run completes | Stream partial results into a `gr.State` and refresh charts incrementally |
| Plotly figures are not responsive on small screens | Layout can overflow on narrow viewports | Use `autosize=True` and percentage-based margins |

---

*Document written on 2026-02-25 — The Price is Right · week8/exercise*
