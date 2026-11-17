"""Polars migration, accounting, pipeline and UI regression checks."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import polars as pl
from streamlit.testing.v1 import AppTest
from src.data import DashboardRepository
from src.analytics import RetailAnalytics
from src.pipeline import RetailPipeline
from src.config import PipelinePaths
from src.thailand import ThailandMockGenerator


class ThailandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = DashboardRepository().load()
        cls.a = RetailAnalytics()

    def test_no_pandas_dependency_in_project(self):
        for path in list(Path("src").glob("*.py")) + [Path("app.py")]:
            text = path.read_text(encoding="utf-8-sig")
            self.assertNotIn("import pandas", text)
            self.assertNotIn("to_pandas(", text)
        self.assertTrue(Path("raw_data").is_dir())
        self.assertFalse(Path("data").exists())

    def test_pre_refactor_totals_preserved(self):
        expected = json.loads(Path("tests/fixtures/pre_polars_totals.json").read_text())
        for table, reference in [
            ("products", "monthly_product"),
            ("category", "monthly_category"),
            ("stores", "stores"),
        ]:
            for col, value in expected[reference].items():
                self.assertAlmostEqual(
                    self.t[table][col].sum(),
                    value,
                    delta=max(0.001, abs(value) * 1e-10),
                )

    def test_sales_reconcile(self):
        raw = (
            pl.scan_parquet("raw_data/sales_lines.parquet")
            .select(
                pl.col("units", "revenue", "cost_of_goods").sum(),
                pl.col("receipt_id").n_unique().alias("transactions"),
            )
            .collect()
        )
        for col in ["units", "revenue", "cost_of_goods"]:
            self.assertAlmostEqual(
                raw[col][0], self.t["category"][col].sum(), delta=0.001
            )
        self.assertEqual(raw["transactions"][0], self.t["stores"]["transactions"].sum())

    def test_inventory_ledger(self):
        stock = self.t["stock"]
        ledger = pl.read_parquet("raw_data/supply/stock_movements.parquet")
        sums = ledger.group_by("store_id", "item_id").agg(pl.col("units_signed").sum())
        closing = (
            stock.sort("date")
            .group_by("store_id", "item_id")
            .agg(pl.col("closing_units").last())
            .join(sums, on=["store_id", "item_id"], validate="1:1")
        )
        self.assertTrue(
            closing.select(
                (pl.col("closing_units") == pl.col("units_signed")).all()
            ).item()
        )
        previous = stock.sort("date").with_columns(
            pl.col("closing_units").shift().over("store_id", "item_id").alias("prior")
        )
        self.assertEqual(
            previous.filter(
                pl.col("prior").is_not_null()
                & (pl.col("opening_units") != pl.col("prior"))
            ).height,
            0,
        )

    def test_po_receipts(self):
        p = self.t["orders"].filter(pl.col("status") == "Received")
        self.assertTrue(
            p.select(
                (
                    pl.col("received_units") + pl.col("short_closed_units")
                    == pl.col("ordered_units")
                ).all()
            ).item()
        )
        ledger = pl.read_parquet("raw_data/supply/stock_movements.parquet").filter(
            pl.col("movement_type") == "PO_RECEIPT"
        )
        linked = p.join(ledger, on="po_line_id", validate="1:1")
        self.assertEqual(linked.height, p.height)
        self.assertTrue(
            linked.select(
                (pl.col("received_units") == pl.col("units_signed")).all()
            ).item()
        )

    def test_budget_and_profit_identities(self):
        c, s = self.t["category"], self.t["stores"]
        p = self.a.branch_pl(c, s)
        self.assertAlmostEqual(
            p["operating_profit"].sum(),
            p["contribution"].sum() - p["fixed_costs"].sum(),
            delta=0.001,
        )
        f = self.a.budget(c, s, self.t["budgets"])
        self.assertEqual(f.height, s.height)
        self.assertAlmostEqual(
            f["profit_gap"].sum(),
            f["actual_profit"].sum() - f["budget_profit"].sum(),
            delta=0.001,
        )

    def test_asof_hides_future(self):
        inventory, cohort = self.a.supply(
            self.t["stock"], self.t["orders"], ("2025-01", "2025-01"), ["TH001"]
        )
        future = cohort.filter(pl.col("actual_receipt_date") > "2025-01-31")
        self.assertGreater(future.height, 0)
        self.assertFalse(future["received_as_of"].any())
        self.assertEqual(future["received_units_as_of"].sum(), 0)

    def test_opening_dates(self):
        stock = self.t["stock"].join(
            self.t["branches"].select("store_id", "opened_date"),
            on="store_id",
            validate="m:1",
        )
        self.assertEqual(stock.filter(pl.col("date") < pl.col("opened_date")).height, 0)
        dim = self.a.maturity(self.t["branches"], "2026-10-31")
        self.assertEqual(set(dim["branch_type"]), {"New branch", "Established branch"})

    def test_generator_and_pipeline_on_small_fixture(self):
        with TemporaryDirectory() as temp:
            ThailandMockGenerator(
                temp, {"end": "2025-01-12", "branch_limit": 1}
            ).generate()
            pipeline = RetailPipeline(PipelinePaths(Path(temp)))
            manifest = pipeline.run()
            self.assertEqual(manifest["rows"]["branches"], 1)
            current = (Path(temp) / "dashboard_data/current.json").read_text()
            # Failed rebuild must not replace the published generation.
            inputs = Path(temp) / "raw_data/branch_operating_inputs.csv"
            f = pl.read_csv(inputs)
            pl.concat([f, f]).write_csv(inputs)
            with self.assertRaises(Exception):
                pipeline.run()
            self.assertEqual(
                (Path(temp) / "dashboard_data/current.json").read_text(), current
            )

    def test_app_filters_and_tabs(self):
        a = AppTest.from_file("app.py").run(timeout=40)
        self.assertFalse(a.exception)
        self.assertEqual(len(a.tabs), 2)
        self.assertEqual(len(a.dataframe), 0)
        a.multiselect[0].set_value(["TH001"]).run(timeout=40)
        self.assertFalse(a.exception)
        expected = (
            self.t["category"].filter(pl.col("store_id") == "TH001")["revenue"].sum()
        )
        self.assertEqual(a.metric[0].value, f"{expected / 1e6:,.2f}")
        a.multiselect[0].set_value(["TH003"])
        a.select_slider[0].set_value(("2025-01", "2025-01"))
        a.run(timeout=40)
        self.assertFalse(a.exception)
        self.assertTrue(a.info)


if __name__ == "__main__":
    unittest.main()
