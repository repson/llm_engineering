# Product Tracker — Implementation Notes

Added on top of the existing **"The Price is Right"** deal-hunting framework.  
The feature lets users manually add Amazon product URLs and receive alerts when
the price drops or reaches a target value.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Files Changed](#3-files-changed)
   - [New: `agents/product_tracker_agent.py`](#31-new-agentsproduct_tracker_agentpy)
   - [Modified: `agents/deals.py`](#32-modified-agentsdealpyy)
   - [Modified: `deal_agent_framework.py`](#33-modified-deal_agent_frameworkpy)
   - [Modified: `price_is_right_final.py`](#34-modified-price_is_right_finalpy)
4. [Data Model](#4-data-model)
5. [Alert Conditions](#5-alert-conditions)
6. [Amazon Scraping Strategy](#6-amazon-scraping-strategy)
7. [Persistence](#7-persistence)
8. [Usage](#8-usage)
9. [Known Limitations](#9-known-limitations)

---

## 1. Overview

The **Product Tracker** is a new feature that coexists with the autonomous deal
hunter. While the deal hunter *discovers* random deals from RSS feeds, the
tracker lets the user *choose* specific products and follow their prices over
time.

**Workflow:**

```
User enters Amazon URL
        │
        ▼
ProductTrackerAgent scrapes the page (title, price, availability, image)
        │
        ▼
TrackedProduct saved to tracked_products.json
        │
        ▼
Every "Check Prices Now" (or future scheduled run)
        │
        ├─▶ Price ≤ target price?          → 🎯 Alert
        ├─▶ Price dropped ≥ X% from start? → 📉 Alert
        └─▶ Low stock keywords detected?   → ⚠️  Alert
                │
                ▼
        Alerts shown in UI + Pushover push notification
```

---

## 2. Architecture

The new feature follows the same **agent pattern** already used in the project:
a dedicated `Agent` subclass handles all external I/O (HTTP scraping), while the
`DealAgentFramework` owns the data lifecycle (persistence, CRUD, scheduling).

```
DealAgentFramework
    ├── PlanningAgent          (existing — RSS deal hunter)
    └── ProductTrackerAgent    (new — Amazon price monitor)
            └── requests + BeautifulSoup  (HTML scraping)
```

The Gradio UI is split into two tabs so both features are independently
accessible without any interference.

---

## 3. Files Changed

### 3.1 New: `agents/product_tracker_agent.py`

A new `Agent` subclass responsible for all Amazon scraping and alert logic.

#### Key design decisions

| Decision | Rationale |
|---|---|
| Multiple CSS price selectors with fallback chain | Amazon A/B-tests its page layout frequently; a single selector breaks silently |
| `requests.Session` reuse | Keeps TCP connections alive across multiple product checks, reducing latency |
| 1.5 s polite delay between requests | Avoids triggering Amazon's bot-detection rate limits |
| Alert logic separated into `_check_alerts()` | Makes unit testing straightforward without needing a live HTTP call |

#### Price selector chain

```python
PRICE_SELECTORS = [
    ("span", {"id": "priceblock_ourprice"}),    # classic layout
    ("span", {"id": "priceblock_dealprice"}),   # deal price
    ("span", {"id": "priceblock_saleprice"}),   # sale price
    ("span", {"class": "a-price-whole"}),       # modern layout (whole part)
    ("span", {"class": "a-offscreen"}),         # screen-reader accessible price
]
```

If none of these match, a final fallback reads the `a-price-whole` +
`a-price-fraction` pair.

#### Public API

```python
# Check a single product, return (updated_product, alerts)
agent.check_product(product: TrackedProduct) -> Tuple[TrackedProduct, List[str]]

# Check all products in a list
agent.check_all(products: List[TrackedProduct]) -> Tuple[List[TrackedProduct], List[str]]
```

---

### 3.2 Modified: `agents/deals.py`

Added the `TrackedProduct` Pydantic model and updated the `Optional` import.

#### New model

```python
class TrackedProduct(BaseModel):
    url: str
    title: str = "Pending..."
    image_url: Optional[str] = None
    current_price: Optional[float] = None
    target_price: Optional[float] = None
    alert_threshold_pct: float = 10.0   # % drop from initial price to trigger an alert
    price_history: List[Dict] = []      # [{"timestamp": "ISO-str", "price": float}, ...]
    last_checked: Optional[str] = None
    added_at: str = ""
    scrape_error: Optional[str] = None  # Last error from ProductTrackerAgent, if any
```

`price_history` is an ordered list (oldest first). The initial price recorded at
`add_tracked_product()` time is always `price_history[0]`, which is the
baseline for percentage-drop alerts.

---

### 3.3 Modified: `deal_agent_framework.py`

Three groups of changes:

#### a) New imports and instance variables

```python
from datetime import datetime
from agents.deals import Opportunity, TrackedProduct   # TrackedProduct added

# In __init__:
self.tracker = None                                    # lazy-initialised
self.tracked_products = self.read_tracked_products()  # loaded at startup
```

#### b) Tracker initialisation (lazy)

`ProductTrackerAgent` is only instantiated on first use — identical pattern to
`PlanningAgent` — so the scraping library is not loaded unless the tab is used.

```python
def init_tracker_as_needed(self):
    if not self.tracker:
        from agents.product_tracker_agent import ProductTrackerAgent
        self.tracker = ProductTrackerAgent()
```

#### c) New public methods

| Method | Purpose |
|---|---|
| `read_tracked_products()` | Deserialise `tracked_products.json` into `List[TrackedProduct]` |
| `write_tracked_products()` | Serialise current list back to JSON |
| `add_tracked_product(url, target_price, alert_threshold_pct)` | Create a `TrackedProduct`, perform an initial scrape, persist |
| `remove_tracked_product(url)` | Filter out the product by URL and persist |
| `check_tracked_products()` | Refresh all products, persist, fire Pushover alerts |
| `get_tracker_table()` | Return a list-of-lists ready for the Gradio `Dataframe` |

##### `get_tracker_table()` column layout

```
[Product title (60 chars), Current Price, Target Price, Alert %, Price History summary, Last Checked, Scrape Status, URL]
```

The **Price History** cell shows `↓$MIN ↑$MAX (N readings)` so the user can see
the price range at a glance without expanding the row.

---

### 3.4 Modified: `price_is_right_final.py`

The single-page Gradio layout was reorganised into a **tabbed interface**:

```
gr.Tabs()
  ├── 🔍 Deal Hunter    (all original content, unchanged behaviour)
  └── 🎯 Product Tracker  (new)
```

#### Product Tracker tab layout

```
┌─────────────────────────────────────────────────────────────┐
│ Amazon URL field │ Target Price ($) │ Alert % slider │ ➕ Track│
├─────────────────────────────────────────────────────────────┤
│ Status message (✅ Added / ⚠️ Warning / ❌ Error)           │
├─────────────────────────────────────────────────────────────┤
│ Tracked Products table (8 columns)                          │
│  • Product | Current $ | Target $ | Alert % |              │
│    History | Last Checked | Status | URL                   │
├─────────────────────────────────────────────────────────────┤
│ [ 🔄 Check Prices Now ]  [ 🗑️ Remove Selected ]           │
├─────────────────────────────────────────────────────────────┤
│ Alert panel (red highlighted boxes, one per alert)         │
└─────────────────────────────────────────────────────────────┘
```

#### Gradio event wiring

| Event | Handler | Outputs |
|---|---|---|
| `add_btn.click` | `add_product()` | table, status markdown |
| `refresh_btn.click` | `check_prices()` | table, alerts HTML |
| `tracked_table.select` | `on_row_select()` | selected row index (State) |
| `remove_btn.click` | `remove_product()` | table, clear selection State |
| `ui.load` | `load_tracker_table()` | table (populate on first render) |

---

## 4. Data Model

### `TrackedProduct` field reference

| Field | Type | Description |
|---|---|---|
| `url` | `str` | Amazon product URL (primary key for removal) |
| `title` | `str` | Product title (scraped from `#productTitle`) |
| `image_url` | `Optional[str]` | Product image src |
| `current_price` | `Optional[float]` | Most recently scraped price |
| `target_price` | `Optional[float]` | User-defined price goal; triggers 🎯 alert |
| `alert_threshold_pct` | `float` | % drop from initial price to trigger 📉 alert |
| `price_history` | `List[Dict]` | `[{"timestamp": str, "price": float}]` ordered list |
| `last_checked` | `Optional[str]` | ISO timestamp of last successful check |
| `added_at` | `str` | ISO timestamp when user added the product |
| `scrape_error` | `Optional[str]` | Last scrape error message, `None` if OK |

### `tracked_products.json` example

```json
[
  {
    "url": "https://www.amazon.com/dp/B09XY123AB",
    "title": "Sony WH-1000XM5 Wireless Noise Canceling Headphones",
    "image_url": "https://m.media-amazon.com/images/I/...",
    "current_price": 279.99,
    "target_price": 250.00,
    "alert_threshold_pct": 10.0,
    "price_history": [
      {"timestamp": "2026-02-25T21:55:00", "price": 299.99},
      {"timestamp": "2026-02-26T21:55:00", "price": 279.99}
    ],
    "last_checked": "2026-02-26T21:55:00",
    "added_at": "2026-02-25T21:55:00",
    "scrape_error": null
  }
]
```

---

## 5. Alert Conditions

Three independent conditions are evaluated on every check:

### 🎯 Target Price Reached

```python
if product.target_price and current_price <= product.target_price:
    # Fire alert
```

Triggers when the scraped price is at or below the user's goal price.

### 📉 Percentage Drop

```python
initial_price = product.price_history[0]["price"]
drop_pct = (initial_price - current_price) / initial_price * 100
if drop_pct >= product.alert_threshold_pct:
    # Fire alert
```

The baseline is always the **first recorded price** (when the product was added),
not the previous check. This prevents "alert fatigue" from small oscillations.

### ⚠️ Limited Stock

```python
LOW_STOCK_KEYWORDS = [
    "only", "left in stock", "few left", "order soon",
    "limited availability", "1 left", "2 left", "3 left",
]
if any(kw in availability.lower() for kw in LOW_STOCK_KEYWORDS):
    # Fire alert
```

Parsed from the `#availability` div on the Amazon product page.

---

## 6. Amazon Scraping Strategy

Amazon actively blocks automated traffic. The implementation uses several
mitigations:

| Mitigation | Implementation |
|---|---|
| Realistic `User-Agent` header | Chrome on macOS UA string |
| `Accept`, `Accept-Language`, `DNT` headers | Match a real browser profile |
| `requests.Session` | Persistent connection pool, looks more like a browser |
| 1.5 s delay between products | `time.sleep(1.5)` in `check_all()` |
| Multiple price selector fallbacks | Graceful handling of Amazon layout A/B tests |
| Non-zero price guard | `if price and price > 0` before recording |

> **Note:** For high-volume or reliable scraping, a dedicated service such as
> [Keepa API](https://keepa.com/#!api) or
> [RainforestAPI](https://www.rainforestapi.com/) should be used instead.

---

## 7. Persistence

| File | Content | When written |
|---|---|---|
| `memory.json` | Deal hunter results (existing) | After each deal-hunter run |
| `tracked_products.json` | All tracked products with full price history | After add, remove, or check |

Both files are plain JSON, human-readable, and can be edited manually or backed
up to version control (excluding sensitive data).

---

## 8. Usage

### Adding a product

1. Open the **🎯 Product Tracker** tab.
2. Paste an Amazon product URL (e.g. `https://www.amazon.com/dp/B09XY123AB`).
3. Optionally set a **Target Price** (the price you're willing to pay).
4. Adjust the **Alert %** slider (default: 10 — alert if price drops 10% from today).
5. Click **➕ Track**.

The system performs an immediate scrape and shows the product title and current
price in the status line.

### Checking prices manually

Click **🔄 Check Prices Now**. All tracked products are re-scraped sequentially.
Any alerts appear in the red panel below the table and are also sent as
Pushover push notifications (if configured).

### Removing a product

Click any row in the table to select it (the row highlights), then click
**🗑️ Remove Selected**.

### Automated daily checks

The existing `gr.Timer` in the Deal Hunter tab runs every 5 minutes. To add
automatic tracker checks, the `timer.tick` event can be extended:

```python
# Example: check both deal hunter and tracker every 5 minutes
timer.tick(
    lambda ld: (*run_with_logging(ld), check_prices()),
    ...
)
```

---

## 9. Known Limitations

| Limitation | Impact | Possible fix |
|---|---|---|
| Amazon bot detection | Scrape may fail on some pages | Use Keepa / RainforestAPI |
| No JavaScript rendering | Prices loaded via JS won't be seen | Use Playwright or Selenium |
| Single-currency (USD) | Price parsing assumes `$` format | Extend `_parse_price()` |
| No deduplication check on add | Same URL can be added twice | Check `url in [p.url for p in tracked_products]` before inserting |
| Alerts only on manual "Check Now" | No true background scheduling | Add APScheduler or extend WorkManager |

---

*Document written on 2026-02-25 — The Price is Right · week8/exercise*
