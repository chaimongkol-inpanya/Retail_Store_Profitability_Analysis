"""Polars-backed dashboard views. Plotly consumes Polars directly through Narwhals."""

import polars as pl
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.analytics import RetailAnalytics, MetricFormatter
from src.visuals import ChartFactory, CATEGORY_COLORS
from src.cards import KpiCard


class DashboardView:
    def __init__(self, tables):
        self.tables = tables
        self.analytics = RetailAnalytics()
        self.charts = ChartFactory()

    def plot(self, fig, height=480):
        if fig.layout.legend.title.text == "cat_id":
            fig.update_layout(legend_title_text="Category")
        for axis in [fig.layout.xaxis, fig.layout.yaxis]:
            if axis.title.text in {"store_id", "cat_id", "supplier_name"}:
                axis.title.text = {
                    "store_id": "Branch",
                    "cat_id": "Category",
                    "supplier_name": "Supplier",
                }[axis.title.text]
        for trace in fig.data:
            if trace.type == "bar":
                percent_axis = fig.layout.xaxis.title.text == "On-time (%)"
                trace.update(
                    text=[
                        f"{value:.1f}%"
                        if percent_axis
                        else f"{value:.3f}"
                        if fig.layout.xaxis.title.text == "THB million"
                        else f"{value:.2f}"
                        for value in trace.x
                    ],
                    texttemplate="%{text}",
                    textposition="outside",
                    cliponaxis=False,
                )
        if (
            any(trace.type == "bar" for trace in fig.data)
            and fig.layout.xaxis.range is None
        ):
            values = [v for trace in fig.data if trace.type == "bar" for v in trace.x]
            extent = max(max(map(abs, values), default=0), 0.01)
            fig.update_layout(
                xaxis_range=[
                    min(0, min(values, default=0)) - 0.12 * extent,
                    max(0, max(values, default=0)) + 0.18 * extent,
                ]
            )
        fig.update_layout(
            height=height,
            margin=dict(l=95, r=65, t=60, b=55),
            legend=dict(orientation="h", y=1.17),
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    def executive(self, c, s, p):
        b = self.analytics.branch_pl(c, s)
        t = b.select(pl.selectors.numeric().sum()).row(0, named=True)
        cols = st.columns(5)
        for col, label, key, tone in zip(
            cols,
            [
                "Revenue",
                "Variable costs",
                "Contribution margin",
                "Fixed costs",
                "Operating profit",
            ],
            [
                "revenue",
                "variable_costs",
                "contribution",
                "fixed_costs",
                "operating_profit",
            ],
            [
                "blue",
                "amber",
                "teal",
                "slate",
                "teal" if t["operating_profit"] >= 0 else "red",
            ],
        ):
            KpiCard.render(
                col,
                label.upper() + " (THB million)",
                f"{t[key] / 1e6:,.2f}",
                key=key,
                tone=tone,
            )
        st.caption(
            "Mock data augmented by AI | Fictional Thailand retail scenario | All financial values exclude VAT."
        )
        active = b.filter("active").height
        profitable = b.filter(pl.col("status") == "Profitable").height
        loss = b.filter(pl.col("status") == "Loss-making").height
        cols = st.columns(5)
        for col, label, value, key, tone in zip(
            cols,
            [
                "ACTIVE BRANCHES",
                "PROFITABLE",
                "LOSS-MAKING",
                "PROFITABLE SHARE",
                "CONTRIBUTION MARGIN",
            ],
            [
                active,
                profitable,
                loss,
                MetricFormatter.percent(profitable / active if active else None),
                MetricFormatter.percent(
                    t["contribution"] / t["revenue"] if t["revenue"] else None
                ),
            ],
            ["active", "profitable", "loss", "share", "cm"],
            ["navy", "teal", "red" if loss else "slate", "teal", "blue"],
        ):
            KpiCard.render(col, label, value, key=key, tone=tone)
        left, right = st.columns(2)
        with left:
            st.subheader("Operating P&L")
            keys = [
                "revenue",
                "cogs",
                "variable_logistics",
                "variable_selling",
                "variable_labor",
                "contribution",
                "fixed_rent",
                "fixed_salaries",
                "fixed_overhead",
                "operating_profit",
            ]
            vals = [
                t[k]
                / 1e6
                * (1 if k in ["revenue", "contribution", "operating_profit"] else -1)
                for k in keys
            ]
            fig = go.Figure(
                go.Waterfall(
                    orientation="h",
                    y=[k.replace("_", " ").title() for k in keys],
                    x=vals,
                    measure=["absolute"]
                    + ["relative"] * 4
                    + ["total"]
                    + ["relative"] * 3
                    + ["total"],
                    text=[f"{v:,.2f}" for v in vals],
                    textposition="outside",
                    cliponaxis=False,
                    totals=dict(marker=dict(color="#173E58")),
                    decreasing=dict(marker=dict(color="#D55E00")),
                )
            )
            fig.update_layout(
                yaxis_autorange="reversed",
                xaxis_title="THB million",
                xaxis_range=[-t["revenue"] / 1e7, t["revenue"] / 1e6 * 1.15],
            )
            self.plot(fig)
        with right:
            st.subheader("Store performance matrix")
            self.plot(self.charts.performance_matrix(b))
            st.caption(
                "Median revenue and contribution-margin boundaries are relative benchmarks, not targets."
            )
        self.planning(c, s)
        st.subheader("Where revenue comes from")
        st.caption(
            "Two independent views of the same revenue. Bars show share of parent; amounts are THB million."
        )
        for view, title in [
            ("geography", "Branch maturity, region and branch"),
            ("assortment", "Category and department"),
        ]:
            st.markdown("**" + title + "**")
            fig = self.charts.decomposition_tree(p, view)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption(
            "New branches are under 365 days old at the selected period end. Both trees represent the same sales; do not add their totals."
        )
        keys = c.select("month", "store_id").unique()
        r = self.tables["receipt_mart"].join(keys, on=["month", "store_id"], how="semi")
        cat = (
            r.group_by("cat_id")
            .agg(
                pl.col(
                    "receipts",
                    "revenue",
                    "cost_of_goods",
                    "variable_opex",
                    "allocated_fixed_cost",
                ).sum()
            )
            .with_columns(
                pl.sum_horizontal(
                    "cost_of_goods", "variable_opex", "allocated_fixed_cost"
                ).alias("cost")
            )
            .with_columns((pl.col("revenue") - pl.col("cost")).alias("profit"))
            .with_columns(
                [
                    (pl.col(k) / pl.col("receipts")).alias(k + "_per_receipt")
                    for k in ["revenue", "cost", "profit"]
                ]
            )
        )
        left, right = st.columns(2)
        with left:
            st.subheader("Category economics per receipt")
            long = cat.unpivot(
                on=["revenue_per_receipt", "cost_per_receipt", "profit_per_receipt"],
                index="cat_id",
                variable_name="Measure",
                value_name="THB per receipt",
            ).with_columns(
                pl.col("Measure").replace(
                    {
                        "revenue_per_receipt": "Revenue",
                        "cost_per_receipt": "Allocated cost",
                        "profit_per_receipt": "Operating profit",
                    }
                )
            )
            self.plot(
                px.bar(
                    long,
                    y="cat_id",
                    x="THB per receipt",
                    color="Measure",
                    barmode="group",
                    orientation="h",
                    text_auto=".2f",
                    color_discrete_map={
                        "Revenue": "#0072B2",
                        "Allocated cost": "#E69F00",
                        "Operating profit": "#009E73",
                    },
                    labels={"cat_id": "Category"},
                )
            )
            st.caption(
                "Containing receipt counts overlap across categories. Cost includes allocated fixed cost."
            )
        with right:
            st.subheader("Category revenue mix")
            fig = px.pie(
                cat,
                names="cat_id",
                values="revenue",
                color="cat_id",
                color_discrete_map=CATEGORY_COLORS,
                hole=0.65,
            )
            fig.update_traces(textinfo="label+percent", textposition="outside")
            fig.update_layout(showlegend=False)
            self.plot(fig)
        left, right = st.columns(2)
        with left:
            st.subheader("Category sales trend")
            trend = (
                c.group_by("month", "cat_id")
                .agg(
                    pl.col("revenue").sum(), pl.col("observed_days").max().alias("days")
                )
                .with_columns(
                    (pl.col("revenue") / pl.col("days") / 1000).alias(
                        "THB thousand per day"
                    )
                )
                .sort("month")
            )
            self.plot(
                px.line(
                    trend,
                    x="month",
                    y="THB thousand per day",
                    color="cat_id",
                    color_discrete_map=CATEGORY_COLORS,
                ),
                max(480, b.height * 26 + 90),
            )
        with right:
            st.subheader("Branch operating P&L")
            rank = b.with_columns(
                (pl.col("operating_profit") / 1e6).alias("THB million")
            ).sort("operating_profit")
            fig = px.bar(
                rank,
                x="THB million",
                y="store_id",
                color="status",
                orientation="h",
                text_auto=".2f",
                color_discrete_map={
                    "Profitable": "#009E73",
                    "Loss-making": "#D55E00",
                    "Break-even": "#777",
                    "Inactive": "#999",
                },
            )
            self.plot(fig, max(480, b.height * 26 + 90))
            st.download_button(
                "Download branch P&L", b.write_csv(), "branch_pl_thb.csv", "text/csv"
            )
        with st.expander("Data pipeline, provenance & reconciliation"):
            st.markdown(
                "**Mock data augmented by AI.** Raw records -> Polars lazy ingestion -> validated transformations -> versioned Parquet marts -> dashboard. All branches, prices, demand and financial results are fictional."
            )
            st.download_button(
                "Download receipt-category mart",
                r.write_csv(),
                "receipt_mart_thb.csv",
                "text/csv",
            )
            st.download_button(
                "Download raw sales sample",
                self.tables["receipt_sample"].write_csv(),
                "sales_sample_thb.csv",
                "text/csv",
            )

    def planning(self, c, s):
        f = self.analytics.budget(c, s, self.tables["budgets"])
        b = f.group_by("store_id").agg(
            pl.col(
                "revenue",
                "budget_revenue",
                "actual_profit",
                "budget_profit",
                "profit_gap",
            ).sum()
        )
        target = f["budget_revenue"].sum()
        actual = f["revenue"].sum()
        gap = f["profit_gap"].sum()
        alerts = b.filter(
            (pl.col("revenue") < pl.col("budget_revenue") * 0.95)
            | (pl.col("actual_profit") < 0)
            | (
                pl.col("profit_gap")
                < -0.1 * pl.col("budget_profit").abs().clip(lower_bound=1)
            )
        )
        st.subheader("Budget & performance alerts")
        cols = st.columns(4)
        for col, label, value, key, tone in zip(
            cols,
            [
                "TARGET (THB million)",
                "ATTAINMENT",
                "PROFIT GAP (THB million)",
                "BRANCHES FLAGGED",
            ],
            [
                f"{target / 1e6:,.2f}",
                MetricFormatter.percent(actual / target if target else None),
                f"{gap / 1e6:+,.2f}",
                f"{alerts.height} / {b.height}",
            ],
            ["target", "attain", "gap", "alerts"],
            [
                "blue",
                "teal" if actual >= target else "amber",
                "teal" if gap >= 0 else "red",
                "amber" if alerts.height else "teal",
            ],
        ):
            KpiCard.render(col, label, value, key=key, tone=tone)
        left, right = st.columns(2)
        height = max(390, b.height * 26 + 90)
        with left:
            st.markdown("**Daily revenue against target**")
            trend = (
                f.group_by("month")
                .agg(pl.col("revenue", "budget_revenue").sum())
                .join(
                    c.group_by("month").agg(
                        pl.col("observed_days").max().alias("days")
                    ),
                    on="month",
                )
                .sort("month")
            )
            fig = go.Figure()
            for field, label, color in [
                ("revenue", "Actual", "#0072B2"),
                ("budget_revenue", "Target", "#E69F00"),
            ]:
                fig.add_trace(
                    go.Scatter(
                        x=trend["month"].to_list(),
                        y=(trend[field] / trend["days"] / 1000).to_list(),
                        name=label,
                        mode="lines+markers",
                        line=dict(color=color),
                    )
                )
            fig.update_layout(yaxis_title="THB thousand / observed day")
            self.plot(fig, height)
        with right:
            st.markdown("**Operating profit variance by branch**")
            b = b.with_columns(
                (pl.col("profit_gap") / 1e6).alias("THB million"),
                pl.when(pl.col("profit_gap") >= 0)
                .then(pl.lit("Favorable"))
                .otherwise(pl.lit("Unfavorable"))
                .alias("Variance"),
            ).sort("profit_gap")
            fig = px.bar(
                b,
                x="THB million",
                y="store_id",
                color="Variance",
                orientation="h",
                text_auto=".3f",
                color_discrete_map={"Favorable": "#009E73", "Unfavorable": "#D55E00"},
            )
            self.plot(fig, height)
        st.caption(
            "Review: sales below 95% of target, operating loss or profit gap worse than 10% of absolute target. Budgets are synthetic scenarios."
        )
        st.download_button(
            "Download actual vs budget",
            f.write_csv(),
            "budget_variance_thb.csv",
            "text/csv",
        )

    def supply(self, c):
        inventory, cohort = self.analytics.supply(
            self.tables["stock"],
            self.tables["orders"],
            (c["month"].min(), c["month"].max()),
            c["store_id"].unique().to_list(),
        )
        st.subheader("Stock control & supplier reliability")
        st.caption(
            "Mock data augmented by AI | Full 180-SKU catalog | Fulfilled sales are constrained by inventory."
        )
        if inventory.is_empty():
            st.info("No inventory data for this selection.")
            return
        due = cohort.height
        rate = cohort["on_time"].mean() if due else None
        late = cohort.filter(~pl.col("received_as_of")).height
        unmet = inventory["unmet_demand_units"].sum()
        zero = inventory["closing_units"].eq(0).mean()
        cols = st.columns(5)
        for col, label, value, key, tone in zip(
            cols,
            [
                "ON-TIME DELIVERY",
                "PO LINES DUE",
                "OVERDUE / UNRECEIVED",
                "UNMET DEMAND (units)",
                "ZERO CLOSING STOCK",
            ],
            [
                MetricFormatter.percent(rate),
                f"{due:,}",
                late,
                f"{unmet:,}",
                MetricFormatter.percent(zero),
            ],
            ["ontime", "due", "overdue", "unmet", "zero"],
            [
                "teal" if rate is not None and rate >= 0.9 else "amber",
                "blue",
                "red" if late else "teal",
                "amber" if unmet else "teal",
                "amber" if zero else "teal",
            ],
        ):
            KpiCard.render(col, label, value, key=key, tone=tone)
        left, right = st.columns(2)
        with left:
            st.markdown("**Average daily closing inventory**")
            daily = (
                inventory.group_by("date", "cat_id")
                .agg(pl.col("closing_units").sum())
                .with_columns(
                    pl.col("date").str.to_date().dt.truncate("1w").alias("week")
                )
            )
            weekly = (
                daily.group_by("week", "cat_id")
                .agg((pl.col("closing_units").mean() / 1000).alias("Thousand units"))
                .sort("week")
            )
            self.plot(
                px.line(
                    weekly,
                    x="week",
                    y="Thousand units",
                    color="cat_id",
                    color_discrete_map=CATEGORY_COLORS,
                ),
                390,
            )
        with right:
            st.markdown("**Delivery reliability by supplier**")
            if due:
                rates = (
                    cohort.group_by("supplier_id")
                    .agg(
                        (pl.col("on_time").mean() * 100).alias("On-time (%)"),
                        pl.len().alias("Due lines"),
                    )
                    .join(self.tables["suppliers"], on="supplier_id", validate="1:1")
                )
                fig = px.bar(
                    rates,
                    x="On-time (%)",
                    y="supplier_name",
                    color="cat_id",
                    color_discrete_map=CATEGORY_COLORS,
                    orientation="h",
                    text_auto=".1f",
                )
                fig.update_layout(xaxis_range=[0, 105])
                self.plot(fig, 390)
            else:
                st.info("No orders due in this period.")
        st.caption(
            "Due-date cohort evaluated at selected period end. Future receipts remain hidden; zero closing stock is end-of-day exposure, not observed lost sales."
        )
        export = cohort.drop(
            "actual_receipt_date", "received_units", "short_closed_units", "status"
        ).with_columns(
            pl.when("received_as_of")
            .then("receipt_date_as_of")
            .otherwise(pl.lit(None))
            .alias("receipt_date_as_of")
        )
        st.download_button(
            "Download supplier delivery analysis",
            export.write_csv(),
            "supplier_delivery.csv",
            "text/csv",
        )
