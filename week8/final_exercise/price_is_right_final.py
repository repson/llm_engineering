import logging
import queue
import threading
import time
import gradio as gr
from deal_agent_framework import DealAgentFramework
from agents.deals import Opportunity, Deal
from log_utils import reformat
import plotly.graph_objects as go
import charts as ch


class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))


def html_for(log_data):
    output = '<br>'.join(log_data[-18:])
    return f"""
    <div id="scrollContent" style="height:400px;overflow-y:auto;border:1px solid #ccc;
         background-color:#222229;padding:10px;">
    {output}
    </div>
    """


def alerts_html_for(alerts):
    """Render tracker alert strings as styled HTML cards."""
    if not alerts:
        return ""
    items = "".join(
        f'<div style="margin:6px 0;padding:8px 12px;border-radius:6px;'
        f'background:#2d1f1f;border-left:4px solid #e74c3c;'
        f'font-size:14px;color:#f5c6cb;">{a}</div>'
        for a in alerts
    )
    return (
        '<div style="margin-top:8px;">'
        '<p style="color:#e74c3c;font-weight:bold;margin-bottom:4px;">🔔 Alerts</p>'
        + items + "</div>"
    )


def setup_logging(log_queue):
    handler = QueueHandler(log_queue)
    formatter = logging.Formatter(
        "[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %z",
    )
    handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class App:

    def __init__(self):
        self.agent_framework = None

    def get_agent_framework(self):
        if not self.agent_framework:
            self.agent_framework = DealAgentFramework()
        return self.agent_framework

    def run(self):
        with gr.Blocks(title="El Precio Justo", fill_width=True) as ui:

            log_data = gr.State([])

            # ---------------------------------------------------------------- #
            # Shared helpers                                                    #
            # ---------------------------------------------------------------- #

            def table_for(opps):
                return [
                    [
                        opp.deal.product_description,
                        f"${opp.deal.price:.2f}",
                        f"${opp.estimate:.2f}",
                        f"${opp.discount:.2f}",
                        opp.deal.url,
                    ]
                    for opp in opps
                ]

            def update_output(log_data, log_queue, result_queue):
                initial_result = table_for(self.get_agent_framework().memory)
                final_result = None
                while True:
                    try:
                        message = log_queue.get_nowait()
                        log_data.append(reformat(message))
                        yield log_data, html_for(log_data), final_result or initial_result
                    except queue.Empty:
                        try:
                            final_result = result_queue.get_nowait()
                            yield log_data, html_for(log_data), final_result or initial_result
                        except queue.Empty:
                            if final_result is not None:
                                break
                            time.sleep(0.1)

            def get_plot():
                documents, vectors, colors = DealAgentFramework.get_plot_data(max_datapoints=1000)
                fig = go.Figure(data=[go.Scatter3d(
                    x=vectors[:, 0], y=vectors[:, 1], z=vectors[:, 2],
                    mode='markers',
                    marker=dict(size=2, color=colors, opacity=0.7),
                )])
                fig.update_layout(
                    scene=dict(
                        xaxis_title='x', yaxis_title='y', zaxis_title='z',
                        aspectmode='manual',
                        aspectratio=dict(x=2.2, y=2.2, z=1),
                        camera=dict(eye=dict(x=1.6, y=1.6, z=0.8)),
                    ),
                    height=400, margin=dict(r=5, b=1, l=5, t=2),
                )
                return fig

            def do_run():
                return table_for(self.get_agent_framework().run())

            def run_with_logging(initial_log_data):
                log_queue = queue.Queue()
                result_queue = queue.Queue()
                setup_logging(log_queue)
                thread = threading.Thread(target=lambda: result_queue.put(do_run()))
                thread.start()
                for ld, out, res in update_output(initial_log_data, log_queue, result_queue):
                    yield ld, out, res

            def do_select(selected_index: gr.SelectData):
                opportunities = self.get_agent_framework().memory
                row = selected_index.index[0]
                if row < len(opportunities):
                    self.get_agent_framework().planner.messenger.alert(opportunities[row])

            # ---------------------------------------------------------------- #
            # Header                                                            #
            # ---------------------------------------------------------------- #

            with gr.Row():
                gr.Markdown(
                    '<div style="text-align:center;font-size:24px">'
                    '<strong>The Price is Right</strong>'
                    ' — Autonomous Agent Framework that hunts for deals</div>'
                )
            with gr.Row():
                gr.Markdown(
                    '<div style="text-align:center;font-size:14px">'
                    'A fine-tuned LLM on Modal + RAG pipeline collaborate '
                    'to find and alert on great online deals.</div>'
                )

            # ---------------------------------------------------------------- #
            # Tabs                                                              #
            # ---------------------------------------------------------------- #

            with gr.Tabs():

                # ============================================================ #
                # Tab 1 — Deal Hunter (original)                                #
                # ============================================================ #
                with gr.Tab("Deal Hunter"):
                    with gr.Row():
                        opportunities_dataframe = gr.Dataframe(
                            headers=["Deal", "Price", "Estimate", "Discount", "URL"],
                            wrap=True,
                            column_widths=[6, 1, 1, 1, 3],
                            row_count=10, col_count=5, max_height=400,
                        )
                    with gr.Row():
                        with gr.Column(scale=1):
                            logs = gr.HTML()
                        with gr.Column(scale=1):
                            plot = gr.Plot(value=get_plot(), show_label=False)

                    ui.load(
                        run_with_logging,
                        inputs=[log_data],
                        outputs=[log_data, logs, opportunities_dataframe],
                    )
                    timer = gr.Timer(value=300, active=True)
                    timer.tick(
                        run_with_logging,
                        inputs=[log_data],
                        outputs=[log_data, logs, opportunities_dataframe],
                    )
                    opportunities_dataframe.select(do_select)

                # ============================================================ #
                # Tab 2 — Analytics Dashboard (new)                             #
                # ============================================================ #
                with gr.Tab("Analytics"):

                    with gr.Row():
                        refresh_analytics_btn = gr.Button(
                            "Refresh Dashboard", variant="primary", scale=0
                        )

                    # KPI summary cards
                    analytics_kpi = gr.HTML()

                    # Row 1: Price Distribution | Category Breakdown
                    with gr.Row():
                        with gr.Column(scale=1):
                            chart_price_dist = gr.Plot(show_label=False)
                        with gr.Column(scale=1):
                            chart_category = gr.Plot(show_label=False)

                    # Row 2: Discount Trends | Savings Over Time
                    with gr.Row():
                        with gr.Column(scale=1):
                            chart_discount_trends = gr.Plot(show_label=False)
                        with gr.Column(scale=1):
                            chart_savings = gr.Plot(show_label=False)

                    # Row 3: Radar (full width, centred)
                    with gr.Row():
                        with gr.Column(scale=1):
                            chart_radar = gr.Plot(show_label=False)
                        with gr.Column(scale=1):
                            gr.Markdown(
                                "### How to read the charts\n\n"
                                "**Price Distribution** — Overlapping histograms of deal prices "
                                "(red) vs. the ensemble model's estimated fair value (teal). "
                                "The further right the teal peak is, the better the deals found.\n\n"
                                "**Discount Trends** — Each dot is a deal, coloured by category, "
                                "ordered chronologically. Useful for spotting if deal quality is "
                                "improving or declining over time.\n\n"
                                "**Savings Over Time** — The teal area shows cumulative total saved. "
                                "Red bars show the discount per individual deal.\n\n"
                                "**Category Breakdown** — Donut chart of which RSS categories "
                                "have generated the most deals.\n\n"
                                "**Deal Quality Radar** — Four dimensions normalised to 0–1. "
                                "Red = portfolio average, teal = best single deal."
                            )

                    def load_analytics():
                        mem = self.get_agent_framework().memory
                        return (
                            ch.summary_stats_html(mem),
                            ch.price_distribution(mem),
                            ch.category_breakdown(mem),
                            ch.discount_trends(mem),
                            ch.savings_over_time(mem),
                            ch.deal_quality_radar(mem),
                        )

                    analytics_outputs = [
                        analytics_kpi,
                        chart_price_dist,
                        chart_category,
                        chart_discount_trends,
                        chart_savings,
                        chart_radar,
                    ]

                    ui.load(load_analytics, outputs=analytics_outputs)
                    refresh_analytics_btn.click(load_analytics, outputs=analytics_outputs)

                # ============================================================ #
                # Tab 3 — Product Tracker                                       #
                # ============================================================ #
                with gr.Tab("Product Tracker"):

                    # -- Add product form --
                    gr.Markdown("### Track a new Amazon product")
                    with gr.Row():
                        url_input = gr.Textbox(
                            label="Amazon Product URL",
                            placeholder="https://www.amazon.com/dp/XXXXXXXXXX",
                            scale=4,
                        )
                        target_price_input = gr.Number(
                            label="Target Price ($)", value=None,
                            precision=2, minimum=0, scale=1,
                        )
                        threshold_input = gr.Slider(
                            minimum=1, maximum=50, value=10, step=1,
                            label="Alert on price drop (%)", scale=1,
                        )
                        add_btn = gr.Button("Track", variant="primary", scale=1)

                    add_status = gr.Markdown("")

                    # -- Tracked products table --
                    gr.Markdown("### Tracked Products")
                    tracked_table = gr.Dataframe(
                        headers=[
                            "Product", "Current Price", "Target Price",
                            "Alert %", "Price History", "Last Checked", "Status", "URL",
                        ],
                        wrap=True,
                        column_widths=[5, 1, 1, 1, 2, 2, 1, 3],
                        row_count=10, col_count=8, max_height=380,
                        interactive=False,
                    )

                    with gr.Row():
                        refresh_tracker_btn = gr.Button("Check Prices Now", variant="primary")
                        remove_btn = gr.Button("Remove Selected", variant="stop")

                    tracker_alerts_html = gr.HTML()

                    # -- Price history chart for selected product --
                    gr.Markdown("### Price History (click a row to view)")
                    chart_price_history = gr.Plot(show_label=False)

                    # State
                    selected_tracker_row = gr.State(None)

                    # -- Load on startup --
                    def load_tracker_table():
                        return self.get_agent_framework().get_tracker_table()

                    ui.load(load_tracker_table, outputs=[tracked_table])

                    # -- Add product --
                    def add_product(url, target_price, threshold):
                        url = url.strip()
                        if not url:
                            return (
                                self.get_agent_framework().get_tracker_table(),
                                "Please enter a URL.",
                            )
                        try:
                            fw = self.get_agent_framework()
                            product = fw.add_tracked_product(
                                url=url,
                                target_price=float(target_price) if target_price else None,
                                alert_threshold_pct=float(threshold),
                            )
                            msg = f"**Added**: {product.title[:70]}"
                            if product.current_price:
                                msg += f" — Current price: **${product.current_price:.2f}**"
                            if product.scrape_error:
                                msg = f"Added but scrape had issues: {product.scrape_error}"
                            return fw.get_tracker_table(), msg
                        except Exception as e:
                            return (
                                self.get_agent_framework().get_tracker_table(),
                                f"Error: {e}",
                            )

                    add_btn.click(
                        add_product,
                        inputs=[url_input, target_price_input, threshold_input],
                        outputs=[tracked_table, add_status],
                    )

                    # -- Check prices --
                    def check_prices():
                        fw = self.get_agent_framework()
                        _, alerts = fw.check_tracked_products()
                        return fw.get_tracker_table(), alerts_html_for(alerts)

                    refresh_tracker_btn.click(
                        check_prices,
                        outputs=[tracked_table, tracker_alerts_html],
                    )

                    # -- Select row → show price history chart --
                    def on_row_select(evt: gr.SelectData):
                        row = evt.index[0]
                        fw = self.get_agent_framework()
                        if row < len(fw.tracked_products):
                            product = fw.tracked_products[row]
                            return row, ch.price_history_chart(product)
                        return row, ch.price_history_chart(None) if False else go.Figure()

                    tracked_table.select(
                        on_row_select,
                        outputs=[selected_tracker_row, chart_price_history],
                    )

                    # -- Remove selected --
                    def remove_product(row_index):
                        fw = self.get_agent_framework()
                        if row_index is not None and row_index < len(fw.tracked_products):
                            fw.remove_tracked_product(fw.tracked_products[row_index].url)
                        return fw.get_tracker_table(), None

                    remove_btn.click(
                        remove_product,
                        inputs=[selected_tracker_row],
                        outputs=[tracked_table, selected_tracker_row],
                    )

        ui.launch(share=False, inbrowser=True)


if __name__ == "__main__":
    App().run()