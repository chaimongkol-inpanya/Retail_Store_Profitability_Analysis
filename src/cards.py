"""Semantic KPI colors with native Streamlit metrics for accessibility and testing."""

import streamlit as st


class KpiCard:
    @staticmethod
    def render(column, label, value, *, key, tone="blue"):
        if tone not in {"blue", "teal", "amber", "red", "navy", "slate"}:
            raise ValueError(f"Unknown KPI tone: {tone}")
        with column.container(key=f"kpi_{key}_{tone}"):
            st.metric(label, value)
