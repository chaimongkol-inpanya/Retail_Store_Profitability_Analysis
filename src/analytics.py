"""Polars analytical services; no presentation or I/O side effects."""

from datetime import date
import calendar
import polars as pl


class RetailAnalytics:
    VARIABLE = ["variable_logistics", "variable_selling", "variable_labor"]
    FIXED = ["fixed_rent", "fixed_salaries", "fixed_overhead"]

    @staticmethod
    def filter(frame, period, branches):
        return frame.filter(
            pl.col("month").is_between(pl.lit(period[0]), pl.lit(period[1]))
            & pl.col("store_id").is_in(branches)
        )

    @staticmethod
    def maturity(dimension, as_of):
        return dimension.with_columns(
            (pl.lit(date.fromisoformat(as_of)) - pl.col("opened_date").str.to_date())
            .dt.total_days()
            .alias("age_days")
        ).with_columns(
            pl.when(pl.col("age_days") < 365)
            .then(pl.lit("New branch"))
            .otherwise(pl.lit("Established branch"))
            .alias("branch_type")
        )

    def branch_pl(self, category, stores):
        fields = self.VARIABLE + self.FIXED
        f = (
            category.group_by("store_id")
            .agg(
                pl.col("revenue", "units").sum(),
                pl.col("cost_of_goods").sum().alias("cogs"),
            )
            .join(
                stores.group_by("store_id").agg(pl.col(fields).sum()),
                on="store_id",
                validate="1:1",
            )
        )
        f = (
            f.with_columns(
                (pl.col("cogs") + pl.sum_horizontal(self.VARIABLE)).alias(
                    "variable_costs"
                ),
                pl.sum_horizontal(self.FIXED).alias("fixed_costs"),
            )
            .with_columns(
                (pl.col("revenue") - pl.col("variable_costs")).alias("contribution"),
                pl.col("units").gt(0).alias("active"),
            )
            .with_columns(
                (pl.col("contribution") - pl.col("fixed_costs")).alias(
                    "operating_profit"
                )
            )
        )
        return f.with_columns(
            pl.when(~pl.col("active"))
            .then(pl.lit("Inactive"))
            .when(pl.col("operating_profit").round(2) > 0)
            .then(pl.lit("Profitable"))
            .when(pl.col("operating_profit").round(2) < 0)
            .then(pl.lit("Loss-making"))
            .otherwise(pl.lit("Break-even"))
            .alias("status")
        )

    def budget(self, category, stores, budget):
        keys = category.select("month", "store_id").unique()
        plan = budget.join(keys, on=["month", "store_id"], how="semi").pivot(
            on="line", index=["month", "store_id"], values="budget_amount"
        )
        plan = plan.with_columns(
            (
                pl.col("revenue")
                - pl.sum_horizontal(["cost_of_goods"] + self.VARIABLE + self.FIXED)
            ).alias("budget_profit")
        ).select(
            "month",
            "store_id",
            pl.col("revenue").alias("budget_revenue"),
            "budget_profit",
        )
        a = (
            category.group_by("month", "store_id")
            .agg(pl.col("revenue").sum(), pl.col("cost_of_goods").sum().alias("cogs"))
            .join(
                stores.select("month", "store_id", "operating_expenses"),
                on=["month", "store_id"],
                validate="1:1",
            )
            .with_columns(
                (
                    pl.col("revenue") - pl.col("cogs") - pl.col("operating_expenses")
                ).alias("actual_profit")
            )
        )
        return a.join(plan, on=["month", "store_id"], validate="1:1").with_columns(
            (pl.col("revenue") - pl.col("budget_revenue")).alias("revenue_gap"),
            (pl.col("actual_profit") - pl.col("budget_profit")).alias("profit_gap"),
        )

    @staticmethod
    def supply(stock, orders, period, branches):
        start = period[0] + "-01"
        year, month = map(int, period[1].split("-"))
        end = min(
            f"{year}-{month:02}-{calendar.monthrange(year, month)[1]}",
            stock["date"].max(),
        )
        inventory = stock.filter(
            pl.col("date").is_between(pl.lit(start), pl.lit(end))
            & pl.col("store_id").is_in(branches)
        )
        cohort = orders.filter(
            pl.col("promised_date").is_between(pl.lit(start), pl.lit(end))
            & pl.col("store_id").is_in(branches)
        )
        visible = pl.col("actual_receipt_date").is_not_null() & (
            pl.col("actual_receipt_date") <= end
        )
        cohort = (
            cohort.with_columns(
                visible.alias("received_as_of"),
                (visible & (pl.col("actual_receipt_date") <= pl.col("promised_date")))
                .fill_null(False)
                .alias("on_time"),
            )
            .with_columns(
                pl.when("received_as_of")
                .then("received_units")
                .otherwise(0)
                .alias("received_units_as_of"),
                pl.when("received_as_of")
                .then("actual_receipt_date")
                .otherwise(pl.lit(end))
                .alias("receipt_date_as_of"),
            )
            .with_columns(
                (
                    pl.col("receipt_date_as_of").str.to_date()
                    - pl.col("promised_date").str.to_date()
                )
                .dt.total_days()
                .clip(lower_bound=0)
                .alias("late_days_as_of")
            )
        )
        return inventory, cohort


class MetricFormatter:
    @staticmethod
    def percent(value):
        return f"{value:.1%}" if value is not None else "N/A"
