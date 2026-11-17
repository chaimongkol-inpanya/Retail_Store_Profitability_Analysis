"""Class-based, NumPy/Polars raw mock generator. No dashboard transformations here."""

from datetime import date, timedelta
from pathlib import Path
import json
import numpy as np
import polars as pl
import pyarrow.parquet as pq


class ThailandMockGenerator:
    DEFAULT = {
        "seed": 20261120,
        "start": "2025-01-01",
        "end": "2026-10-31",
        "currency": "THB",
        "branch_limit": 18,
        "effects": {
            "weekend": 1.15,
            "songkran": 1.12,
            "school": 1.10,
            "rain_cleaning": 1.12,
            "year_end": 1.18,
        },
    }
    CATEGORIES = [
        "TOOLS",
        "HOUSEHOLD",
        "CLEANING",
        "ELECTRICAL",
        "STATIONERY",
        "LIFESTYLE",
    ]
    PLACES = {
        "North": ["Chiang Mai", "Chiang Rai", "Lampang"],
        "Northeast": ["Nakhon Ratchasima", "Khon Kaen", "Udon Thani"],
        "Central": ["Bangkok", "Nonthaburi", "Pathum Thani"],
        "East": ["Chonburi", "Rayong", "Chachoengsao"],
        "West": ["Nakhon Pathom", "Kanchanaburi", "Ratchaburi"],
        "South": ["Surat Thani", "Phuket", "Songkhla"],
    }

    def __init__(self, root=None, config=None):
        self.root = Path(root or Path(__file__).resolve().parents[1])
        self.raw = self.root / "raw_data"
        self.config = self.DEFAULT | (config or {})
        self.rng = np.random.default_rng(self.config["seed"])
        self.po_counter = 0
        self.movement_counter = 0
        self.config["effects"] = self.DEFAULT["effects"] | (config or {}).get(
            "effects", {}
        )
        if (
            self.config["branch_limit"] not in range(1, 19)
            or self.config["end"] < self.config["start"]
        ):
            raise ValueError(
                "Use 1-18 branches and an end date on or after the start date"
            )

    def dimensions(self):
        branches = []
        for region, provinces in self.PLACES.items():
            for province in provinces:
                i = len(branches)
                opened = (
                    [
                        "2025-04-01",
                        "2025-07-01",
                        "2025-10-01",
                        "2026-01-01",
                        "2026-04-01",
                        "2026-07-01",
                    ][i // 3]
                    if i % 3 == 2
                    else "2022-01-01"
                )
                branches.append(
                    dict(
                        store_id=f"TH{i + 1:03}",
                        region_id=region,
                        province=province,
                        opened_date=opened,
                        provenance="Mock data augmented by AI",
                    )
                )
        catalog = []
        for i, cat in enumerate(self.CATEGORIES):
            for j in range(30):
                catalog.append(
                    dict(
                        item_id=f"{cat}_{j + 1:03}",
                        cat_id=cat,
                        dept_id=f"{cat}_{1 + j // 15}",
                        price=float(
                            self.rng.choice([29, 49, 79, 99, 149, 199, 299, 499, 799])
                        ),
                        cost_ratio=float(
                            np.clip(
                                self.rng.normal(
                                    [0.65, 0.60, 0.62, 0.68, 0.55, 0.58][i], 0.04
                                ),
                                0.45,
                                0.8,
                            )
                        ),
                    )
                )
        return branches[: self.config["branch_limit"]], catalog

    def generate(self):
        self.raw.mkdir(parents=True, exist_ok=True)
        supply = self.raw / "supply"
        supply.mkdir(exist_ok=True)
        branches, catalog = self.dimensions()
        pl.DataFrame(branches).write_csv(self.raw / "branches.csv")
        pl.DataFrame(catalog).write_csv(self.raw / "products.csv")
        suppliers = [
            dict(
                supplier_id=f"SUP{i + 1:02}",
                supplier_name=f"Mock {cat.title()} Supply",
                cat_id=cat,
                promised_lead_days=3 + i % 4,
            )
            for i, cat in enumerate(self.CATEGORIES)
        ]
        pl.DataFrame(suppliers).write_csv(supply / "suppliers.csv")
        start = date.fromisoformat(self.config["start"])
        end = date.fromisoformat(self.config["end"])
        writers = {}
        all_orders = []
        inputs = []
        budgets = []
        counts = {"inventory_rows": 0, "movements": 0, "po_lines": 0}
        prices = np.array([r["price"] for r in catalog])
        ratios = np.array([r["cost_ratio"] for r in catalog])
        cats = np.array([r["cat_id"] for r in catalog])
        itemids = np.array([r["item_id"] for r in catalog])
        deptids = np.array([r["dept_id"] for r in catalog])

        def append(name, frame, path):
            if frame.is_empty():
                return
            if name not in writers:
                writers[name] = pq.ParquetWriter(
                    path, frame.to_arrow().schema, compression="zstd"
                )
            writers[name].write_table(frame.to_arrow())

        try:
            for bi, branch in enumerate(branches):
                first = max(start, date.fromisoformat(branch["opened_date"]))
                if first > end:
                    continue
                pending = {}
                scale = self.rng.uniform(0.65, 1.4)
                balance = self.rng.integers(12, 35, 180)
                initial = balance.copy()
                outstanding = np.zeros(180, int)
                snapshots = []
                sales = []
                orders = []
                coverage = {}
                for di in range((end - first).days + 1):
                    day = first + timedelta(days=di)
                    ds = day.isoformat()
                    month = ds[:7]
                    coverage[month] = coverage.get(month, 0) + 1
                    opening = balance.copy()
                    received = np.zeros(180, int)
                    for j, qty, order in pending.pop(day, []):
                        balance[j] += qty
                        received[j] += qty
                        outstanding[j] -= order["ordered_units"]
                        order.update(
                            actual_receipt_date=ds,
                            received_units=qty,
                            short_closed_units=order["ordered_units"] - qty,
                            status="Received",
                        )
                    ef = self.config["effects"]
                    season = ef["weekend"] if day.weekday() >= 5 else 1
                    if day.month == 4 and 10 <= day.day <= 16:
                        season *= ef["songkran"]
                    if day.month in [11, 12]:
                        season *= ef["year_end"]
                    lam = np.full(
                        180, 1.6 * scale * season * min(1, 0.6 + di / 180 * 0.4)
                    )
                    if day.month in [5, 6]:
                        lam[cats == "STATIONERY"] *= ef["school"]
                    if day.month in [6, 7, 8, 9, 10]:
                        lam[cats == "CLEANING"] *= ef["rain_cleaning"]
                    demand = self.rng.poisson(lam)
                    sold = np.minimum(demand, balance)
                    balance -= sold
                    shrink = np.minimum(
                        balance, (self.rng.random(180) < 0.002).astype(int)
                    )
                    balance -= shrink
                    for j in range(180):
                        snapshots.append(
                            (
                                ds,
                                branch["store_id"],
                                itemids[j],
                                cats[j],
                                int(opening[j]),
                                int(received[j]),
                                0,
                                int(sold[j]),
                                int(shrink[j]),
                                int(balance[j]),
                                int(demand[j] - sold[j]),
                                int(initial[j]) if di == 0 else 0,
                            )
                        )
                        position = balance[j] + outstanding[j]
                        lead = suppliers[j // 30]["promised_lead_days"]
                        if position < lam[j] * (lead + 3):
                            qty = max(1, int(np.ceil(lam[j] * 18 - position)))
                            promised = day + timedelta(days=lead)
                            arrival = promised + timedelta(
                                days=0
                                if self.rng.random() < 0.88
                                else int(self.rng.choice([1, 2, 4]))
                            )
                            self.po_counter += 1
                            order = dict(
                                po_line_id=f"PO{self.po_counter:08}",
                                supplier_id=suppliers[j // 30]["supplier_id"],
                                store_id=branch["store_id"],
                                item_id=itemids[j],
                                cat_id=cats[j],
                                order_date=ds,
                                promised_date=promised.isoformat(),
                                ordered_units=qty,
                                actual_receipt_date=None,
                                received_units=0,
                                short_closed_units=0,
                                status="Open",
                            )
                            orders.append(order)
                            outstanding[j] += qty
                            pending.setdefault(arrival, []).append(
                                (j, max(1, int(qty * self.rng.uniform(0.92, 1))), order)
                            )
                    indices = np.repeat(np.arange(180), sold)
                    if len(indices):
                        receipt = self.rng.integers(
                            0, max(1, int(len(indices) / 2.8)), len(indices)
                        )
                        pairs, unitcount = np.unique(
                            np.stack([receipt, indices], axis=1),
                            axis=0,
                            return_counts=True,
                        )
                        rids, jj = pairs[:, 0], pairs[:, 1]
                        mapping = {k: i for i, k in enumerate(np.unique(rids))}
                        net = prices[jj] * (
                            1
                            - self.rng.choice(
                                [0, 0.05, 0.1], len(jj), p=[0.85, 0.1, 0.05]
                            )
                        )
                        factor = 1 + (int(branch["store_id"][-3:]) % 5 - 2) * 0.015
                        for k, j, u, price in zip(rids, jj, unitcount, net):
                            sales.append(
                                (
                                    f"{branch['store_id']}-{day:%Y%m%d}-{mapping[k]:04}",
                                    ds,
                                    month,
                                    branch["store_id"],
                                    itemids[j],
                                    cats[j],
                                    deptids[j],
                                    branch["region_id"],
                                    int(u),
                                    float(price),
                                    float(u * price),
                                    float(u * prices[j] * ratios[j] * factor),
                                )
                            )
                stock = pl.DataFrame(
                    snapshots,
                    schema=[
                        "date",
                        "store_id",
                        "item_id",
                        "cat_id",
                        "opening_units",
                        "receipt_units",
                        "emergency_units",
                        "sold_units",
                        "shrink_units",
                        "closing_units",
                        "unmet_demand_units",
                        "initial_units",
                    ],
                    orient="row",
                )
                lines = pl.DataFrame(
                    sales,
                    schema=[
                        "receipt_id",
                        "date",
                        "month",
                        "store_id",
                        "item_id",
                        "cat_id",
                        "dept_id",
                        "region_id",
                        "units",
                        "unit_price",
                        "revenue",
                        "cost_of_goods",
                    ],
                    orient="row",
                )
                append("stock", stock, supply / "daily_inventory.parquet")
                append("sales", lines, self.raw / "sales_lines.parquet")
                counts["inventory_rows"] += stock.height
                parts = []
                for field, kind, sign in [
                    ("initial_units", "OPENING", 1),
                    ("sold_units", "SALE", -1),
                    ("shrink_units", "SHRINK", -1),
                ]:
                    parts.append(
                        stock.filter(pl.col(field) > 0).select(
                            "date",
                            "store_id",
                            "item_id",
                            (pl.col(field) * sign).alias("units_signed"),
                            pl.lit(kind).alias("movement_type"),
                            pl.lit("").alias("po_line_id"),
                        )
                    )
                pos = (
                    pl.DataFrame(
                        orders, schema_overrides={"actual_receipt_date": pl.String}
                    )
                    if orders
                    else None
                )
                if pos is not None:
                    parts.append(
                        pos.filter(pl.col("status") == "Received").select(
                            pl.col("actual_receipt_date").alias("date"),
                            "store_id",
                            "item_id",
                            pl.col("received_units").alias("units_signed"),
                            pl.lit("PO_RECEIPT").alias("movement_type"),
                            "po_line_id",
                        )
                    )
                    all_orders.extend(orders)
                ledger = pl.concat(parts).with_columns(
                    pl.Series(
                        "movement_id",
                        [
                            f"MOV{i:09}"
                            for i in range(
                                self.movement_counter,
                                self.movement_counter + sum(f.height for f in parts),
                            )
                        ],
                    )
                )
                self.movement_counter += ledger.height
                append("ledger", ledger, supply / "stock_movements.parquet")
                counts["movements"] += ledger.height
                planned = (
                    180
                    * 1.6
                    * prices.mean()
                    * 0.99
                    * (0.75 + (int(branch["store_id"][-3:]) % 7) * 0.1)
                )
                fixed_rate = 0.12 + bi / 17 * 0.18
                for month, days in coverage.items():
                    traffic = int(
                        np.rint(
                            lines.filter(pl.col("month") == month)[
                                "receipt_id"
                            ].n_unique()
                            / 0.62
                        )
                    )
                    record = dict(
                        month=month,
                        store_id=branch["store_id"],
                        traffic=traffic,
                        **{
                            k: planned * fixed_rate * days * f
                            for k, f in [
                                ("fixed_rent", 0.4),
                                ("fixed_salaries", 0.45),
                                ("fixed_overhead", 0.15),
                            ]
                        },
                    )
                    inputs.append(record)
                    target = planned * days
                    for line, amount in dict(
                        revenue=target,
                        cost_of_goods=target * 0.64,
                        variable_logistics=target * 0.024,
                        variable_selling=target * 0.014,
                        variable_labor=target * 0.019,
                        fixed_rent=target * 0.21 * 0.4,
                        fixed_salaries=target * 0.21 * 0.45,
                        fixed_overhead=target * 0.21 * 0.15,
                    ).items():
                        budgets.append(
                            dict(
                                plan_version="TH_PLAN_V1",
                                month=month,
                                store_id=branch["store_id"],
                                line=line,
                                budget_amount=amount,
                                observed_days=days,
                            )
                        )
                print(branch["store_id"], "raw records generated", flush=True)
        finally:
            for writer in writers.values():
                writer.close()
        order_schema = {
            key: pl.String
            for key in [
                "po_line_id",
                "supplier_id",
                "store_id",
                "item_id",
                "cat_id",
                "order_date",
                "promised_date",
                "actual_receipt_date",
                "status",
            ]
        }
        order_schema.update(
            {
                key: pl.Int64
                for key in ["ordered_units", "received_units", "short_closed_units"]
            }
        )
        pl.DataFrame(all_orders, schema=order_schema).write_csv(
            supply / "purchase_order_lines.csv"
        )
        pl.DataFrame(inputs).write_csv(self.raw / "branch_operating_inputs.csv")
        pl.DataFrame(budgets).write_csv(self.raw / "budget_lines.csv")
        counts["po_lines"] = len(all_orders)
        (self.raw / "generation_config.json").write_text(
            json.dumps(self.config, indent=2), encoding="utf-8"
        )
        (supply / "manifest.json").write_text(
            json.dumps(
                counts
                | {"as_of": end.isoformat(), "provenance": "Mock data augmented by AI"},
                indent=2,
            ),
            encoding="utf-8",
        )
        return counts


if __name__ == "__main__":
    print(ThailandMockGenerator().generate())
