"""Polars transformations and reconciliation gates."""

import polars as pl


class DataTransformer:
    def __init__(self, ingestion):
        self.ingestion = ingestion

    def transform(self):
        scan = self.ingestion.scan
        sales = scan("sales_lines.parquet")
        stock = scan("supply/daily_inventory.parquet").with_columns(
            pl.col("date").str.slice(0, 7).alias("month")
        )
        coverage = stock.group_by("month", "store_id").agg(
            pl.col("date").n_unique().alias("observed_days"),
            pl.col("date").min().alias("period_start"),
            pl.col("date").max().alias("period_end"),
        )
        inv = stock.group_by("month", "store_id", "item_id").agg(
            pl.col("closing_units").mean().alias("avg_units"),
            pl.col("closing_units").eq(0).sum().alias("stockout_item_days"),
            pl.len().alias("item_days"),
        )
        products = (
            sales.group_by(
                "month", "store_id", "region_id", "item_id", "dept_id", "cat_id"
            )
            .agg(pl.col("units", "revenue", "cost_of_goods").sum())
            .join(coverage, on=["month", "store_id"], validate="m:1")
            .join(inv, on=["month", "store_id", "item_id"], validate="1:1")
            .with_columns(
                pl.col("units").alias("priced_units"),
                (pl.col("revenue") / pl.col("units")).alias("avg_sell_price"),
                (pl.col("avg_units") * pl.col("cost_of_goods") / pl.col("units")).alias(
                    "inventory_cost"
                ),
            )
            .collect(engine="streaming")
        )
        category = products.group_by("month", "store_id", "region_id", "cat_id").agg(
            pl.col(
                "units",
                "priced_units",
                "revenue",
                "cost_of_goods",
                "inventory_cost",
                "stockout_item_days",
                "item_days",
            ).sum(),
            pl.col("observed_days", "period_start", "period_end").first(),
        )
        transactions = (
            sales.group_by("month", "store_id")
            .agg(pl.col("receipt_id").n_unique().alias("transactions"))
            .collect(engine="streaming")
        )
        stores = (
            category.group_by("month", "store_id", "region_id")
            .agg(pl.col("revenue").sum(), pl.col("observed_days").first())
            .join(transactions, on=["month", "store_id"], validate="1:1")
            .join(
                scan("branch_operating_inputs.csv").collect(),
                on=["month", "store_id"],
                validate="1:1",
            )
            .with_columns(
                (pl.col("revenue") * 0.025).alias("variable_logistics"),
                (pl.col("revenue") * 0.015).alias("variable_selling"),
                (pl.col("revenue") * 0.02).alias("variable_labor"),
            )
        )
        cost_fields = [
            "variable_logistics",
            "variable_selling",
            "variable_labor",
            "fixed_rent",
            "fixed_salaries",
            "fixed_overhead",
        ]
        stores = stores.with_columns(
            pl.sum_horizontal(cost_fields).alias("operating_expenses")
        )
        receipt = (
            sales.group_by("receipt_id", "month", "store_id", "cat_id")
            .agg(pl.col("units", "revenue", "cost_of_goods").sum())
            .collect(engine="streaming")
        )
        rc = receipt.join(
            stores.select(
                "month",
                "store_id",
                pl.col("revenue").alias("branch_revenue"),
                *cost_fields,
            ),
            on=["month", "store_id"],
            validate="m:1",
        ).with_columns(
            (
                pl.col("revenue")
                / pl.col("branch_revenue")
                * pl.sum_horizontal(cost_fields[:3])
            ).alias("variable_opex"),
            (
                pl.col("revenue")
                / pl.col("branch_revenue")
                * pl.sum_horizontal(cost_fields[3:])
            ).alias("allocated_fixed_cost"),
        )
        mart = rc.group_by("month", "store_id", "cat_id").agg(
            pl.col("receipt_id").n_unique().alias("receipts"),
            pl.col(
                "units",
                "revenue",
                "cost_of_goods",
                "variable_opex",
                "allocated_fixed_cost",
            ).sum(),
        )
        return {
            "products": products,
            "category": category,
            "stores": stores,
            "receipt_mart": mart,
            "receipt_sample": sales.limit(1000).collect(),
            "budgets": scan("budget_lines.csv").collect(),
            "branches": scan("branches.csv").collect(),
            "stock": stock.collect(),
            "orders": scan("supply/purchase_order_lines.csv").collect(),
            "suppliers": scan("supply/suppliers.csv").collect(),
        }


class DataValidator:
    def validate(self, tables):
        for name, keys in {
            "products": ["month", "store_id", "item_id"],
            "category": ["month", "store_id", "cat_id"],
            "stores": ["month", "store_id"],
            "branches": ["store_id"],
            "stock": ["date", "store_id", "item_id"],
            "orders": ["po_line_id"],
            "budgets": ["plan_version", "month", "store_id", "line"],
        }.items():
            f = tables[name]
            if f.select(pl.struct(keys).is_duplicated().any()).item():
                raise ValueError(f"Duplicate keys in {name}")
        stock = tables["stock"]
        if stock.filter(
            (
                pl.col("opening_units")
                + pl.col("receipt_units")
                + pl.col("emergency_units")
                - pl.col("sold_units")
                - pl.col("shrink_units")
                != pl.col("closing_units")
            )
            | (pl.col("closing_units") < 0)
        ).height:
            raise ValueError("Inventory reconciliation failed")
        for field in ["revenue", "cost_of_goods", "units"]:
            a = tables["products"][field].sum()
            b = tables["category"][field].sum()
            c = tables["receipt_mart"][field].sum()
            if abs(a - b) > max(1e-5, abs(a) * 1e-10) or abs(a - c) > max(
                1e-5, abs(a) * 1e-10
            ):
                raise ValueError(f"{field} does not reconcile")
        costs = (
            tables["receipt_mart"]
            .select(pl.sum_horizontal("variable_opex", "allocated_fixed_cost").sum())
            .item()
        )
        if abs(costs - tables["stores"]["operating_expenses"].sum()) > 0.001:
            raise ValueError("Receipt allocated costs do not reconcile")
        if (
            abs(tables["stores"]["revenue"].sum() - tables["category"]["revenue"].sum())
            > 0.001
        ):
            raise ValueError(
                "Store revenues do not reconcile; check operating-input coverage"
            )
        for name in ["category", "products", "stores"]:
            f = tables[name]
            for column, dtype in f.schema.items():
                if (
                    dtype.is_numeric()
                    and f.select(
                        (
                            pl.col(column).is_null()
                            | ~pl.col(column).is_finite()
                            | (pl.col(column) < 0)
                        ).any()
                    ).item()
                ):
                    raise ValueError(f"Invalid numeric value: {name}.{column}")
        expected = tables["stores"].select("month", "store_id").unique()
        covered = tables["budgets"].select("month", "store_id").unique()
        if expected.join(covered, on=["month", "store_id"], how="anti").height:
            raise ValueError("Missing branch/month budgets")
