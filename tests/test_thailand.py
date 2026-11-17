import unittest
from pathlib import Path
import pandas as pd
import numpy as np
from streamlit.testing.v1 import AppTest
from src.data import load_data
from src.operating_views import load_operations
from src.planning import budget_performance, classify_branches
from src.profitability import branch_pl

class ThailandTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c,cls.s,cls.p=load_data();cls.b,cls.dim,cls.stock,cls.po,cls.sup,cls.man=load_operations()
 def test_dimensions(self):
  self.assertEqual(len(self.dim),18);self.assertEqual(self.p.item_id.nunique(),180);self.assertEqual(self.dim.region_id.nunique(),6)
  self.assertEqual(self.c.month.min(),'2025-01');self.assertEqual(self.c.month.max(),'2026-10')
 def test_dates(self):
  x=self.stock.merge(self.dim[['store_id','opened_date']],on='store_id',validate='many_to_one');self.assertTrue(x.date.ge(x.opened_date).all())
  self.assertEqual(set(classify_branches(self.dim,'2026-10-31').branch_type),{'New branch','Established branch'})
 def test_sales_reconcile(self):
  raw=pd.read_parquet('data/sales_lines.parquet');self.assertFalse(raw.duplicated(['receipt_id','item_id']).any())
  self.assertAlmostEqual(raw.revenue.sum(),self.c.revenue.sum(),places=4)
  self.assertEqual(raw.units.sum(),self.stock.sold_units.sum())
  self.assertEqual(raw.receipt_id.nunique(),self.s.transactions.sum())
  self.assertAlmostEqual(raw.cost_of_goods.sum(),self.c.cost_of_goods.sum(),places=4)
 def test_inventory(self):
  x=self.stock;np.testing.assert_array_equal(x.opening_units+x.receipt_units-x.sold_units-x.shrink_units,x.closing_units);self.assertTrue(x.closing_units.ge(0).all())
  ledger=pd.read_parquet('data/supply/stock_movements.parquet');a=ledger.groupby(['store_id','item_id']).units_signed.sum().sort_index();b=x.sort_values('date').groupby(['store_id','item_id']).closing_units.last().sort_index();np.testing.assert_array_equal(a,b)
 def test_po(self):
  p=self.po.dropna(subset=['actual_receipt_date']);self.assertTrue(p.eval('received_units + short_closed_units == ordered_units').all());self.assertFalse(self.po.po_line_id.duplicated().any())
 def test_budget_and_pl(self):
  f=budget_performance(self.c,self.s,self.b);self.assertEqual(len(f),len(self.s));self.assertAlmostEqual(f.revenue.sum(),self.c.revenue.sum())
  q=branch_pl(self.c,self.s);self.assertAlmostEqual((q.contribution-q.fixed_costs).sum(),q.operating_profit.sum())
 def test_receipt_costs(self):
  r=pd.read_csv('data/receipt_category_month.csv');self.assertAlmostEqual(r.revenue.sum(),self.c.revenue.sum(),places=4);self.assertAlmostEqual((r.variable_opex+r.allocated_fixed_cost).sum(),self.s.operating_expenses.sum(),places=4)
 def test_app(self):
  a=AppTest.from_file('app.py').run(timeout=40);self.assertFalse(a.exception);self.assertEqual(len(a.tabs),2);self.assertEqual(len(a.dataframe),0)
  a.multiselect[0].set_value(['TH001']).run(timeout=40);self.assertFalse(a.exception)
if __name__=='__main__':unittest.main()
