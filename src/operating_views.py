"""Planning and supply-chain executive charts; all added operational records are mock data."""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.planning import budget_performance
from src.supply_chain import supply_period
from src.visuals import CATEGORY_COLORS
from src.cards import kpi

ROOT = Path(__file__).resolve().parents[1]


@st.cache_data
def _load_operations(versions):
    budget = pd.read_csv(ROOT/'data/budget_lines.csv')
    branches = pd.read_csv(ROOT/'data/branches.csv')
    stock = pd.read_parquet(ROOT/'data/supply/daily_inventory.parquet')
    orders = pd.read_csv(ROOT/'data/supply/purchase_order_lines.csv')
    suppliers = pd.read_csv(ROOT/'data/supply/suppliers.csv')
    manifest = json.loads((ROOT/'data/supply/manifest.json').read_text())
    if budget.duplicated(['plan_version', 'month', 'store_id', 'line']).any():
        raise ValueError('Duplicate budget lines')
    if branches.store_id.duplicated().any() or orders.po_line_id.duplicated().any():
        raise ValueError('Duplicate branch or purchase order keys')
    if stock.duplicated(['date', 'store_id', 'item_id']).any():
        raise ValueError('Duplicate inventory snapshots')
    if not np.array_equal(stock.opening_units+stock.receipt_units+stock.emergency_units-stock.sold_units-stock.shrink_units, stock.closing_units):
        raise ValueError('Inventory movement reconciliation failed')
    if (stock.closing_units < 0).any():
        raise ValueError('Negative inventory balance')
    return budget, branches, stock, orders, suppliers, manifest


def load_operations():
    names = ['budget_lines.csv', 'branches.csv', 'supply/daily_inventory.parquet',
             'supply/purchase_order_lines.csv', 'supply/suppliers.csv', 'supply/manifest.json']
    return _load_operations(tuple((ROOT/'data'/name).stat().st_mtime_ns for name in names))


def chart_layout(fig, x_title=None):
    fig.update_layout(height=390, margin=dict(l=75, r=65, t=55, b=50),
                      legend=dict(orientation='h', y=1.18, font_size=13),
                      xaxis_title=x_title, hovermode='closest')
    return fig


def planning_section(category, stores, budgets):
    perf = budget_performance(category, stores, budgets)
    revenue = perf.revenue.sum(); target = perf.budget_revenue.sum()
    profit_gap = perf.profit_gap.sum()
    branches = perf.groupby('store_id', as_index=False)[['revenue', 'budget_revenue', 'actual_profit', 'budget_profit', 'profit_gap']].sum()
    # Compare at selected-period branch level; no summing of monthly alert flags.
    alerts = branches[(branches.revenue < .95*branches.budget_revenue) | (branches.actual_profit < 0) |
                      (branches.profit_gap < -.10*branches.budget_profit.abs().clip(lower=1))]
    st.subheader('Budget & performance alerts')
    st.caption('Synthetic planning scenario | Targets cover the same observed days as actuals, including partial months. These are scenario budgets set from catalog and branch assumptions.')
    cols = st.columns(4)
    attainment=revenue/target if target else None
    kpi(cols[0],'SALES TARGET (THB million)',f'{target/1e6:,.2f}',key='target',tone='blue')
    kpi(cols[1],'SALES ATTAINMENT',f'{attainment:.1%}' if attainment is not None else 'N/A',key='attainment',tone='slate' if attainment is None else 'teal' if attainment>=1 else 'amber' if attainment>=.95 else 'red')
    kpi(cols[2],'PROFIT GAP (THB million)',f'{profit_gap/1e6:+,.2f}',key='profit_gap',tone='teal' if profit_gap>=0 else 'red')
    kpi(cols[3],'BRANCHES FLAGGED',f'{len(alerts)} / {len(branches)}',key='alerts',tone='amber' if len(alerts) else 'teal')
    left, right = st.columns(2)
    with left:
        st.markdown('**Daily revenue against target**')
        trend = perf.groupby('month', as_index=False)[['revenue', 'budget_revenue']].sum()
        covered = category.groupby('month').observed_days.first()
        trend['days'] = trend.month.map(covered)
        fig = go.Figure()
        for column, name, color, dash in [('revenue', 'Actual (synthetic)', '#0072B2', 'solid'), ('budget_revenue', 'Scenario target', '#E69F00', 'dash')]:
            fig.add_trace(go.Scatter(x=trend.month, y=trend[column]/trend.days/1000, name=name, mode='lines+markers', line=dict(color=color, width=3, dash=dash), hovertemplate='%{x}<br>%{y:,.1f} THB thousand / observed day<extra>%{fullData.name}</extra>'))
        chart_layout(fig, 'Month').update_layout(height=max(390,len(branches)*26+90),yaxis_title='THB thousand / observed day', hovermode='x unified', xaxis=dict(tickformat='%b %y', dtick='M2'))
        st.plotly_chart(fig, width='stretch')
        st.caption('Daily averages normalize partial months. Actual and target use the same observed-day coverage.')
    with right:
        st.markdown('**Operating profit variance by branch**')
        branches['Gap (THB million)'] = branches.profit_gap/1e6
        branches['Variance'] = np.where(branches.profit_gap >= 0, 'Favorable', 'Unfavorable')
        fig = px.bar(branches.sort_values('profit_gap'), x='Gap (THB million)', y='store_id', color='Variance', orientation='h', text_auto='+.2f', color_discrete_map={'Favorable': '#009E73', 'Unfavorable': '#D55E00'}, labels={'store_id': 'Branch'})
        for trace in fig.data:
            trace.update(text=[f'{v:+.3f}' for v in trace.x], texttemplate='%{text}', textposition='outside', cliponaxis=False, textfont_size=12)
        gap_limit = max(branches['Gap (THB million)'].abs().max()*1.45, .01)
        fig.update_layout(xaxis_range=[-gap_limit, gap_limit])
        chart_layout(fig, 'Actual minus target (THB million)').update_layout(height=max(390,len(branches)*26+90)); fig.add_vline(x=0, line_color='#94A3B8')
        st.plotly_chart(fig, width='stretch')
        st.caption('Flags: sales below 95% of target, operating loss, or profit gap worse than 10% of the absolute profit target. Favorable includes beating a loss target.')
    if not alerts.empty:
        st.caption('Review branches: ' + ', '.join(alerts.store_id) + '. These alerts describe the selected period, not independent causal findings.')
    st.download_button('Download actual vs budget', perf.assign(provenance='synthetic Thailand data revenue; simulated actual costs and budget targets').to_csv(index=False), 'branch_budget_variance_thb.csv', 'text/csv')


def supply_section(stock, orders, suppliers, manifest, category):
    period = (category.month.min(), category.month.max())
    inventory, cohort = supply_period(stock, orders, period, category.store_id.unique(), manifest['as_of'])
    st.subheader('Stock control & supplier reliability')
    st.caption(f"Synthetic Thailand supply chain: {manifest['sample_items']} SKUs (all catalog items), {inventory.store_id.nunique()} selected branches. Sales are fulfilled from simulated on-hand inventory. All catalog SKUs are included; unmet demand is recorded separately.")
    if inventory.empty:
        st.info('No inventory observations for this selection.'); return
    keys = ['store_id', 'item_id']
    ordered = inventory.sort_values('date')
    opening = ordered.groupby(keys).opening_units.first().sum()
    closing = ordered.groupby(keys).closing_units.last().sum()
    end = inventory.date.max()
    due = len(cohort)
    transfers = inventory.emergency_units.sum()
    cols = st.columns(5)
    rate=cohort.on_time.mean() if due else None
    overdue=int((~cohort.received_as_of).sum())
    zero_stock=inventory.closing_units.eq(0).mean()
    kpi(cols[0],'ON-TIME DELIVERY',f'{rate:.1%}' if rate is not None else 'N/A',key='on_time',tone='slate' if rate is None else 'teal' if rate>=.90 else 'amber' if rate>=.80 else 'red')
    kpi(cols[1],'PO LINES DUE',f'{due:,}',key='po_due',tone='blue')
    kpi(cols[2],'OVERDUE / UNRECEIVED',f'{overdue:,}',key='overdue',tone='red' if overdue else 'teal')
    unmet=inventory.unmet_demand_units.sum()
    kpi(cols[3],'UNMET DEMAND (units)',f'{unmet:,.0f}',key='unmet',tone='amber' if unmet else 'teal')
    kpi(cols[4],'ZERO CLOSING STOCK',f'{zero_stock:.1%}',key='zero_stock',tone='amber' if zero_stock else 'teal')
    sample_share = inventory.sold_units.sum()/category.units.sum() if category.units.sum() else 0
    st.caption(f'The inventory ledger covers {sample_share:.1%} of selected unit sales. Zero closing stock is the share of SKU/store/days with no end-of-day units, a simulation exposure metric; unmet demand is generated separately.')
    left, right = st.columns(2)
    with left:
        st.markdown('**Average daily closing inventory**')
        daily = inventory.groupby(['date', 'cat_id'], as_index=False).closing_units.sum()
        daily['week'] = pd.to_datetime(daily.date).dt.to_period('W-SUN').dt.start_time
        weekly = daily.groupby(['week', 'cat_id'], as_index=False).closing_units.mean()
        weekly['Thousand units'] = weekly.closing_units/1000
        fig = px.line(weekly, x='week', y='Thousand units', color='cat_id', color_discrete_map=CATEGORY_COLORS, labels={'week':'Week', 'cat_id':'Category'})
        fig.update_traces(line_width=2.5)
        chart_layout(fig, 'Week').update_layout(hovermode='x unified', yaxis_title='Average daily closing stock (thousand units)')
        st.plotly_chart(fig, width='stretch')
        residual = opening+inventory.receipt_units.sum()+transfers-inventory.sold_units.sum()-inventory.shrink_units.sum()-closing
        st.caption(f'Weekly mean of daily category closing balances, including partial weeks. Movement reconciliation residual: {residual:,.0f} units. Download details to audit opening + receipts + emergency transfers - sales - shrink = closing.')
    with right:
        st.markdown('**Delivery reliability by supplier**')
        if cohort.empty:
            st.info('No purchase orders were due in this period.')
        else:
            rates = cohort.groupby('supplier_id', as_index=False).agg(on_time=('on_time', 'sum'), due=('po_line_id', 'count'), delay=('late_days_as_of', 'mean'))
            rates = rates.merge(suppliers[['supplier_id', 'supplier_name', 'cat_id']], on='supplier_id', validate='one_to_one')
            rates['On-time delivery (%)'] = rates.on_time/rates.due*100
            fig = px.bar(rates, x='On-time delivery (%)', y='supplier_name', orientation='h', text_auto='.1f', hover_data={'due': True, 'delay': ':.1f'}, color='cat_id', color_discrete_map=CATEGORY_COLORS, labels={'supplier_name': 'Supplier','cat_id':'Category'})
            for trace in fig.data:
                trace.update(text=[f'{v:.1f}%' for v in trace.x], texttemplate='%{text}', textposition='outside', cliponaxis=False)
            chart_layout(fig, 'On-time lines / due lines (%)').update_layout(xaxis_range=[0, 105], xaxis_tickvals=[0,20,40,60,80,100], margin_l=155)
            st.plotly_chart(fig, width='stretch')
        st.caption(f'Due-date cohort for selected months; evaluated as of {end}. Future receipts are hidden. Late-day hover includes days overdue for unreceived orders. Short-closed quantities remain visible in the download.')
    export = cohort.drop(columns=['actual_receipt_date', 'received_units', 'short_closed_units', 'status']).copy()
    export['receipt_date_as_of'] = cohort.actual_receipt_date.where(cohort.received_as_of, '')
    export['short_closed_units_as_of'] = cohort.short_closed_units.where(cohort.received_as_of, 0)
    export['provenance'] = 'Synthetic PO due-date cohort, evaluated at selected period end'
    st.download_button('Download supplier delivery analysis', export.to_csv(index=False), 'supplier_delivery_analysis.csv', 'text/csv')
