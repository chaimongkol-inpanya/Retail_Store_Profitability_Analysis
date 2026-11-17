from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class Metrics:
    revenue: float
    gross_profit: float
    margin: float | None
    basket: float | None
    operating_profit: float
    stockout_rate: float | None
    stock_days: float | None
    coverage: float | None

def ratio(numerator, denominator):
    return numerator / denominator if denominator else None

def calculate(category, stores):
    revenue = category.revenue.sum()
    cost = category.cost_of_goods.sum()
    monthly = category.groupby('month').agg(inventory=('inventory_cost','sum'), days=('observed_days','first'))
    days = monthly.days.sum()
    average_inventory = (monthly.inventory * monthly.days).sum() / days if days else 0
    return Metrics(revenue, revenue-cost, ratio(revenue-cost, revenue),
                   ratio(revenue, stores.transactions.sum()),
                   revenue-cost-stores.operating_expenses.sum(),
                   ratio(category.stockout_item_days.sum(), category.item_days.sum()),
                   ratio(average_inventory, ratio(cost, days) or 0),
                   ratio(category.priced_units.sum(), category.units.sum()))

def money(value):
    return f'{value:,.0f} THB' if value is not None else 'N/A'

def percent(value):
    return f'{value:.1%}' if value is not None else 'N/A'
