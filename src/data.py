"""Cached class-based loading of published dashboard marts."""

import streamlit as st
from src.data_loader import DashboardLoader


class DashboardRepository:
    def __init__(self):
        self.loader = DashboardLoader()

    def load(self):
        return self._cached(self.loader.manifest()["generation"])

    @staticmethod
    @st.cache_data
    def _cached(generation):
        loader = DashboardLoader()
        return {
            name: loader.load(name, generation)
            for name in [
                "products",
                "category",
                "stores",
                "receipt_mart",
                "receipt_sample",
                "budgets",
                "branches",
                "stock",
                "orders",
                "suppliers",
            ]
        }
