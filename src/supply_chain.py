"""As-of supply analytics for synthetic Thailand retail records."""
import pandas as pd

def supply_period(stock, orders, period, selected, cutoff):
    """Date-consistent snapshots and promised-date PO cohort; future receipts remain invisible."""
    start = max(pd.Period(period[0]).start_time.strftime('%Y-%m-%d'), stock.date.min())
    end = min(pd.Period(period[1]).end_time.strftime('%Y-%m-%d'), cutoff)
    inventory = stock[stock.date.between(start, end) & stock.store_id.isin(selected)].copy()
    cohort = orders[orders.promised_date.between(start, end) & orders.store_id.isin(selected)].copy()
    receipt = pd.to_datetime(cohort.actual_receipt_date)
    promised = pd.to_datetime(cohort.promised_date)
    visible = receipt.notna() & receipt.le(pd.Timestamp(end))
    cohort['received_as_of'] = visible
    cohort['on_time'] = visible & receipt.le(promised)
    cohort['received_units_as_of'] = cohort.received_units.where(visible, 0)
    cohort['late_days_as_of'] = ((receipt.where(visible, pd.Timestamp(end)) - promised).dt.days).clip(lower=0)
    return inventory, cohort


