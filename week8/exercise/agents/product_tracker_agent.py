import re
import time
import logging
import requests
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from bs4 import BeautifulSoup
from agents.agent import Agent


class ProductTrackerAgent(Agent):
    """
    Agent that scrapes Amazon product pages to track prices and generate
    alerts when:
      - The price drops by a configurable % from the initial price
      - The price reaches or falls below a user-defined target price
      - Limited stock is detected on the page
    """

    name = "Product Tracker Agent"
    color = Agent.GREEN

    # Rotate through a few common UA strings to reduce bot-detection rate
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
    }

    # Price CSS selectors tried in order of priority
    PRICE_SELECTORS = [
        ("span", {"id": "priceblock_ourprice"}),
        ("span", {"id": "priceblock_dealprice"}),
        ("span", {"id": "priceblock_saleprice"}),
        ("span", {"class": "a-price-whole"}),   # paired with a-price-fraction
        ("span", {"class": "a-offscreen"}),      # hidden accessible price
    ]

    # Keywords that suggest limited stock
    LOW_STOCK_KEYWORDS = [
        "only", "left in stock", "few left", "order soon",
        "limited availability", "1 left", "2 left", "3 left",
    ]

    def __init__(self):
        self.log("Initializing Product Tracker Agent")
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.log("Product Tracker Agent ready")

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------

    def scrape_amazon(self, url: str) -> Dict:
        """
        Fetch and parse an Amazon product page.
        Returns a dict with keys: title, price, availability, image_url, error.
        """
        self.log(f"Scraping: {url[:80]}...")
        try:
            response = self.session.get(url, timeout=20, allow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            title = self._extract_title(soup)
            price = self._extract_price(soup)
            availability = self._extract_availability(soup)
            image_url = self._extract_image(soup)

            self.log(
                f"Scraped OK — title={title[:40]}... | "
                f"price=${price} | stock={availability[:40]}"
            )
            return {
                "title": title,
                "price": price,
                "availability": availability,
                "image_url": image_url,
                "error": None,
            }
        except requests.exceptions.HTTPError as e:
            msg = f"HTTP {e.response.status_code} for {url}"
            self.log(f"Scrape error: {msg}")
            return {"title": "Error", "price": None, "availability": "", "image_url": None, "error": msg}
        except Exception as e:
            self.log(f"Scrape exception: {e}")
            return {"title": "Error", "price": None, "availability": "", "image_url": None, "error": str(e)}

    def _extract_title(self, soup: BeautifulSoup) -> str:
        el = soup.find("span", {"id": "productTitle"})
        return el.get_text(strip=True) if el else "Unknown product"

    def _extract_price(self, soup: BeautifulSoup) -> Optional[float]:
        for tag, attrs in self.PRICE_SELECTORS:
            el = soup.find(tag, attrs)
            if el:
                price = self._parse_price(el.get_text(strip=True))
                if price and price > 0:
                    return price

        # Fallback: look for a-price block (whole + fraction)
        whole = soup.find("span", {"class": "a-price-whole"})
        fraction = soup.find("span", {"class": "a-price-fraction"})
        if whole:
            text = whole.get_text(strip=True).replace(",", "").replace(".", "")
            frac = fraction.get_text(strip=True) if fraction else "00"
            try:
                return float(f"{text}.{frac}")
            except ValueError:
                pass
        return None

    def _extract_availability(self, soup: BeautifulSoup) -> str:
        el = soup.find("div", {"id": "availability"})
        if el:
            return el.get_text(separator=" ", strip=True)
        el = soup.find("span", {"class": "a-color-price"})
        return el.get_text(strip=True) if el else ""

    def _extract_image(self, soup: BeautifulSoup) -> Optional[str]:
        for img_id in ("landingImage", "imgBlkFront", "main-image"):
            img = soup.find("img", {"id": img_id})
            if img:
                return img.get("src") or img.get("data-src")
        return None

    def _parse_price(self, text: str) -> Optional[float]:
        text = text.replace(",", "").replace("$", "").strip()
        match = re.search(r"\d+\.\d+|\d+", text)
        return float(match.group()) if match else None

    # ------------------------------------------------------------------
    # Alert logic
    # ------------------------------------------------------------------

    def _check_alerts(self, product, current_price: float, availability: str) -> List[str]:
        """
        Given the freshly-scraped price and availability, return a list of
        human-readable alert strings (empty if nothing notable).
        """
        alerts = []

        # Alert 1 — target price reached
        if product.target_price and current_price <= product.target_price:
            alerts.append(
                f"🎯 TARGET REACHED! «{product.title[:45]}» "
                f"is now ${current_price:.2f} "
                f"(target ${product.target_price:.2f})"
            )

        # Alert 2 — price dropped X% from initial price
        if product.price_history:
            initial_price = product.price_history[0]["price"]
            if initial_price and initial_price > 0:
                drop_pct = (initial_price - current_price) / initial_price * 100
                if drop_pct >= product.alert_threshold_pct:
                    alerts.append(
                        f"📉 PRICE DROP {drop_pct:.1f}%! «{product.title[:45]}» "
                        f"${initial_price:.2f} → ${current_price:.2f}"
                    )

        # Alert 3 — limited stock
        avail_lower = availability.lower()
        if any(kw in avail_lower for kw in self.LOW_STOCK_KEYWORDS):
            alerts.append(
                f"⚠️ LIMITED STOCK: «{product.title[:45]}» — {availability[:60]}"
            )

        return alerts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_product(self, product) -> Tuple[object, List[str]]:
        """
        Scrape the product page, update its price history, and return
        (updated_product, alerts).
        """
        data = self.scrape_amazon(product.url)
        now = datetime.now().isoformat()
        alerts = []

        current_price = data.get("price")

        # Always update metadata
        if data.get("title") and data["title"] not in ("Error", "Unknown product"):
            product.title = data["title"]
        if data.get("image_url"):
            product.image_url = data["image_url"]
        product.last_checked = now
        product.scrape_error = data.get("error")

        if current_price is None:
            self.log(f"Could not determine price for '{product.title}'")
            return product, alerts

        # Record the price
        product.price_history.append({"timestamp": now, "price": current_price})
        product.current_price = current_price

        alerts = self._check_alerts(product, current_price, data.get("availability", ""))
        return product, alerts

    def check_all(self, products: List) -> Tuple[List, List[str]]:
        """
        Check all tracked products. Returns (updated_products, all_alerts).
        """
        self.log(f"Checking {len(products)} tracked products…")
        all_alerts: List[str] = []
        updated = []

        for product in products:
            p, alerts = self.check_product(product)
            updated.append(p)
            all_alerts.extend(alerts)
            time.sleep(1.5)   # Polite delay between requests

        self.log(f"Done. {len(all_alerts)} alert(s) generated.")
        return updated, all_alerts
