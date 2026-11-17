"""Reproducible planning scenarios and period-end branch maturity."""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PLAN_LINES = ['revenue', 'cost_of_goods', 'variable_logistics', 'variable_selling',
              'variable_labor', 'fixed_rent', 'fixed_salaries', 'fixed_overhead']


def classify_branches(dimension, as_of):
    result = dimension.copy()
    result['age_days'] = (pd.Timestamp(as_of) - pd.to_datetime(result.opened_date)).dt.days
    result['branch_type'] = np.where(result.age_days < 365, 'New branch', 'Established branch')
    return result


def budget_performance(category, stores, budget_lines):
    keys = category[['month', 'store_id']].drop_duplicates()
    plan = budget_lines.merge(keys, on=['month', 'store_id'], validate='many_to_one')
    plan = plan.pivot(index=['month', 'store_id'], columns='line', values='budget_amount').reset_index()
    plan['budget_profit'] = plan.revenue - plan[[c for c in PLAN_LINES if c != 'revenue']].sum(axis=1)
    actual = category.groupby(['month', 'store_id'], as_index=False).agg(revenue=('revenue', 'sum'), cogs=('cost_of_goods', 'sum'))
    actual = actual.merge(stores[['month', 'store_id', 'operating_expenses']], on=['month', 'store_id'], validate='one_to_one')
    actual['actual_profit'] = actual.revenue - actual.cogs - actual.operating_expenses
    result = actual.merge(plan[['month', 'store_id', 'revenue', 'budget_profit']].rename(columns={'revenue': 'budget_revenue'}), on=['month', 'store_id'], validate='one_to_one')
    result['revenue_gap'] = result.revenue - result.budget_revenue
    result['profit_gap'] = result.actual_profit - result.budget_profit
    return result


