"""Streamlit application controller using Polars data and class-based services."""

import polars as pl
import streamlit as st
from src.data import DashboardRepository
from src.analytics import RetailAnalytics
from src.dashboard import DashboardView
from src.theme import DashboardTheme


class RetailApplication:
    def run(self):
        st.set_page_config(page_title="Retail Performance | Portfolio", layout="wide")
        DashboardTheme.apply()
        st.markdown(
            '<div class="dashboard-header"><span>RETAIL INTELLIGENCE</span><h1>Retail performance</h1><p>Mock data augmented by AI | Thailand retail scenario</p></div>',
            unsafe_allow_html=True,
        )
        try:
            tables = DashboardRepository().load()
        except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
            st.error(f"{exc}. Run python -m src.pipeline to publish dashboard data.")
            st.stop()
        analytics = RetailAnalytics()
        months = sorted(tables["category"]["month"].unique().to_list())
        cols = st.columns([2, 1])
        with cols[0]:
            period = st.select_slider(
                "MONTH RANGE", options=months, value=(months[0], months[-1])
            )
        with cols[1]:
            selected = (
                st.multiselect(
                    "BRANCHES",
                    sorted(tables["branches"]["store_id"].to_list()),
                    placeholder="All branches",
                )
                or tables["branches"]["store_id"].to_list()
            )
        c = analytics.filter(tables["category"], period, selected)
        s = analytics.filter(tables["stores"], period, selected)
        p = analytics.filter(tables["products"], period, selected)
        if c.is_empty():
            st.info("No data for this selection.")
            st.stop()
        dim = analytics.maturity(tables["branches"], c["period_end"].max())
        p = p.join(
            dim.select("store_id", "branch_type", "province"),
            on="store_id",
            validate="m:1",
        )
        st.caption(f"{period[0]} to {period[1]} | THB | Mock data augmented by AI")
        view = DashboardView(tables)
        summary, supply = st.tabs(
            ["Executive summary", "Stock control & supplier reliability"]
        )
        with summary:
            view.executive(c, s, p)
        with supply:
            view.supply(c)


RetailApplication().run()
