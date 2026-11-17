from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

def validate_data(category, store, products=None):
    required={'month','store_id','region_id','cat_id','units','priced_units','revenue','observed_days','period_start','period_end','item_days','cost_of_goods','inventory_cost','stockout_item_days'}
    for frame,cols,keys in [(category,required,['month','store_id','cat_id']),(store,{'month','store_id','region_id','transactions','traffic','operating_expenses','variable_logistics','variable_selling','variable_labor','fixed_rent','fixed_salaries','fixed_overhead'},['month','store_id'])]:
        if cols-set(frame.columns): raise ValueError(f'Missing fields {sorted(cols-set(frame.columns))}. Rebuild prepared data.')
        if frame[list(cols)].isna().any().any() or frame.duplicated(keys).any(): raise ValueError('Missing values or duplicate keys in prepared data.')
        nums=frame.select_dtypes(include='number')
        if not np.isfinite(nums).all().all() or (nums<0).any().any(): raise ValueError('Prepared data has invalid numeric values.')
    if products is not None:
        pcols={'month','store_id','item_id','dept_id','cat_id','units','priced_units','revenue','avg_sell_price','cost_of_goods','inventory_cost','stockout_item_days','item_days'}
        if pcols-set(products.columns): raise ValueError('Product table schema is incomplete.')
        if products.duplicated(['month','store_id','item_id']).any(): raise ValueError('Duplicate product-month keys.')
        if (products.stockout_item_days>products.item_days).any(): raise ValueError('Invalid simulated stockout exposure.')
        if (products.priced_units>products.units).any(): raise ValueError('Price coverage exceeds sales.')
    if (category.priced_units>category.units).any() or (category.stockout_item_days>category.item_days).any(): raise ValueError('Invalid category ratios.')
    if (store.transactions>store.traffic).any(): raise ValueError('Transactions exceed traffic.')
    if (category.observed_days<=0).any(): raise ValueError('Observation periods must be positive.')
    if set(map(tuple,category[['month','store_id']].values))!=set(map(tuple,store[['month','store_id']].values)): raise ValueError('Store/category keys do not match.')

@st.cache_data
def _load_data(*versions):
    category=pd.read_csv(ROOT/'data/monthly_category.csv')
    store=pd.read_csv(ROOT/'data/monthly_store_mock.csv')
    products=pd.read_csv(ROOT/'data/monthly_product.csv')
    validate_data(category,store,products)
    return category,store,products

def load_data():
    files=[ROOT/f'data/{name}' for name in ['monthly_category.csv','monthly_store_mock.csv','monthly_product.csv']]
    return _load_data(*(p.stat().st_mtime_ns for p in files))

def filter_data(category, store, period, selected):
    return tuple(frame[frame.month.between(*period) & frame.store_id.isin(selected)].copy() for frame in (category, store))
