import os
import sys
import logging
import json
from datetime import datetime
from typing import List, Optional
from twilio.rest import Client
from dotenv import load_dotenv
import chromadb
from agents.planning_agent import PlanningAgent
from agents.deals import Opportunity, TrackedProduct
from sklearn.manifold import TSNE
import numpy as np

# Download pkl files:
# https://drive.google.com/drive/folders/1f_IZGybvs9o0J5sb3xmtTEQB3BXllzrW

# Colors for logging
BG_BLUE = '\033[44m'
WHITE = '\033[37m'
RESET = '\033[0m'

# Colors for plot
CATEGORIES = ['Appliances', 'Automotive', 'Cell_Phones_and_Accessories', 'Electronics','Musical_Instruments', 'Office_Products', 'Tools_and_Home_Improvement', 'Toys_and_Games']
COLORS = ['red', 'blue', 'brown', 'orange', 'yellow', 'green' , 'purple', 'cyan']

def init_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] [Agents] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %z",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)

class DealAgentFramework:

    DB = "products_vectorstore"
    MEMORY_FILENAME = "memory.json"
    TRACKER_FILENAME = "tracked_products.json"

    def __init__(self):
        init_logging()
        load_dotenv()
        client = chromadb.PersistentClient(path=self.DB)
        self.memory = self.read_memory()
        self.collection = client.get_or_create_collection('products')
        self.planner = None
        self.tracker = None
        self.tracked_products = self.read_tracked_products()

    def init_agents_as_needed(self):
        if not self.planner:
            self.log("Inicializando el Framework de Agentes")
            self.planner = PlanningAgent(self.collection)
            self.log("El framework de agentes está listo")

    def read_memory(self) -> List[Opportunity]:
        if os.path.exists(self.MEMORY_FILENAME):
            with open(self.MEMORY_FILENAME, "r") as file:
                data = json.load(file)
            opportunities = [Opportunity(**item) for item in data]
            return opportunities
        return []

    def write_memory(self) -> None:
        data = [opportunity.dict() for opportunity in self.memory]
        with open(self.MEMORY_FILENAME, "w") as file:
            json.dump(data, file, indent=2)

    def log(self, message: str):
        text = BG_BLUE + WHITE + "[Framework de Agentes] " + message + RESET
        logging.info(text)

    def run(self) -> List[Opportunity]:
        self.init_agents_as_needed()
        logging.info("Puesta en marcha del agente de planificación")
        result = self.planner.plan(memory=self.memory)
        logging.info(f"La agente de planificación ha completado y regresado: {result}")
        if result:
            self.memory.append(result)
            self.write_memory()
        return self.memory

    # ------------------------------------------------------------------
    # Product Tracker
    # ------------------------------------------------------------------

    def init_tracker_as_needed(self):
        if not self.tracker:
            from agents.product_tracker_agent import ProductTrackerAgent
            self.log("Initializing Product Tracker Agent")
            self.tracker = ProductTrackerAgent()
            self.log("Product Tracker Agent ready")

    def read_tracked_products(self) -> List[TrackedProduct]:
        if os.path.exists(self.TRACKER_FILENAME):
            with open(self.TRACKER_FILENAME, "r") as f:
                data = json.load(f)
            return [TrackedProduct(**item) for item in data]
        return []

    def write_tracked_products(self) -> None:
        data = [p.dict() for p in self.tracked_products]
        with open(self.TRACKER_FILENAME, "w") as f:
            json.dump(data, f, indent=2)

    def add_tracked_product(
        self,
        url: str,
        target_price: Optional[float] = None,
        alert_threshold_pct: float = 10.0,
    ) -> TrackedProduct:
        """
        Add a new product to track. Performs an initial scrape right away
        so the UI can show the title and current price immediately.
        """
        product = TrackedProduct(
            url=url,
            target_price=target_price,
            alert_threshold_pct=alert_threshold_pct,
            added_at=datetime.now().isoformat(),
        )
        self.init_tracker_as_needed()
        product, _ = self.tracker.check_product(product)
        self.tracked_products.append(product)
        self.write_tracked_products()
        return product

    def remove_tracked_product(self, url: str) -> None:
        self.tracked_products = [p for p in self.tracked_products if p.url != url]
        self.write_tracked_products()

    def check_tracked_products(self) -> tuple:
        """
        Re-check prices for all tracked products.
        Returns (updated_products, alert_messages).
        """
        self.init_tracker_as_needed()
        self.tracked_products, alerts = self.tracker.check_all(self.tracked_products)
        self.write_tracked_products()
        # Send push notifications for each alert
        if alerts and self.planner:
            for alert_text in alerts:
                try:
                    self.planner.messenger.push(alert_text)
                except Exception as e:
                    logging.warning(f"Could not send push for tracker alert: {e}")
        return self.tracked_products, alerts

    def get_tracker_table(self) -> List[List]:
        """
        Return a list of rows suitable for display in a Gradio Dataframe.
        """
        rows = []
        for p in self.tracked_products:
            price_str = f"${p.current_price:.2f}" if p.current_price else "N/A"
            target_str = f"${p.target_price:.2f}" if p.target_price else "—"
            readings = len(p.price_history)
            # Simple min/max from history
            if readings >= 2:
                prices = [h["price"] for h in p.price_history]
                history_str = f"↓${min(prices):.0f} ↑${max(prices):.0f} ({readings} readings)"
            else:
                history_str = f"{readings} reading"
            last_checked = (p.last_checked or "Never")[:16].replace("T", " ")
            status = "❌" + p.scrape_error[:25] if p.scrape_error else "✅ OK"
            rows.append([
                p.title[:60],
                price_str,
                target_str,
                f"{p.alert_threshold_pct:.0f}%",
                history_str,
                last_checked,
                status,
                p.url,
            ])
        return rows

    @classmethod
    def get_plot_data(cls, max_datapoints=10000):
        client = chromadb.PersistentClient(path=cls.DB)
        collection = client.get_or_create_collection('products')
        result = collection.get(include=['embeddings', 'documents', 'metadatas'], limit=max_datapoints)
        vectors = np.array(result['embeddings'])
        documents = result['documents']
        categories = [metadata['category'] for metadata in result['metadatas']]
        colors = [COLORS[CATEGORIES.index(c)] for c in categories]
        tsne = TSNE(n_components=3, random_state=42, n_jobs=-1)
        reduced_vectors = tsne.fit_transform(vectors)
        return documents, reduced_vectors, colors


if __name__=="__main__":
    DealAgentFramework().run()