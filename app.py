import streamlit as st
from src.data import load_data, filter_data
from src.metrics import calculate
from src.theme import apply_style
from src.dashboard import executive_dashboard
from src.operating_views import load_operations, supply_section
from src.planning import classify_branches

st.set_page_config(page_title='Retail Performance | Portfolio', layout='wide')
apply_style()
st.markdown('<div class=dashboard-header><span>RETAIL INTELLIGENCE</span><h1>Retail performance</h1><p>Branch profitability &bull; Budget performance &bull; Supply operations</p></div>', unsafe_allow_html=True)
try:
    category, stores, products = load_data()
    operations = load_operations()
except (OSError, ValueError, KeyError) as exc:
    st.error(f'Unable to load the prepared data: {exc}. See README for setup.')
    st.stop()
months = sorted(category.month.unique())
filters = st.columns([2,1])
with filters[0]:
    period = st.select_slider('MONTH RANGE', options=months, value=(months[0],months[-1]))
with filters[1]:
    chosen_stores = st.multiselect('BRANCHES', sorted(category.store_id.unique()), placeholder='All branches')
    selected = chosen_stores or sorted(category.store_id.unique())
d, s = filter_data(category, stores, period, selected)
p = products[products.month.between(*period) & products.store_id.isin(selected)].copy()
if d.empty:
    st.info('No data for this selection.')
    st.stop()
as_of = d.period_end.max()
dimension = classify_branches(operations[1], as_of)
p = p.merge(dimension[['store_id', 'branch_type', 'province']], on='store_id', validate='many_to_one')
m = calculate(d, s)
st.caption(f'{period[0]} to {period[1]} | THB | Complete branch P&L for the selected period')
summary_tab, supply_tab = st.tabs(['Executive summary', 'Stock control & supplier reliability'])
with summary_tab:
    executive_dashboard(d,p,m,s,operations)
with supply_tab:
    supply_section(operations[2], operations[3], operations[4], operations[5], d)
