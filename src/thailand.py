"""Reproducible Thailand retail facts: supply-constrained sales -> receipts -> marts."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
CONFIG={'seed':20261120,'start':'2025-01-01','end':'2026-10-31','currency':'THB','sku_per_category':30,'categories':['TOOLS','HOUSEHOLD','CLEANING','ELECTRICAL','STATIONERY','LIFESTYLE'],'effects':{'weekend':1.15,'songkran':1.12,'school':1.10,'rain_cleaning':1.12,'year_end':1.18}}

def build():
 rng=np.random.default_rng(CONFIG['seed']);out=ROOT/'data';out.mkdir(exist_ok=True);supply=out/'supply';supply.mkdir(exist_ok=True)
 dates=pd.date_range(CONFIG['start'],CONFIG['end']); cats=CONFIG['categories']
 places={'North':['Chiang Mai','Chiang Rai','Lampang'],'Northeast':['Nakhon Ratchasima','Khon Kaen','Udon Thani'],'Central':['Bangkok','Nonthaburi','Pathum Thani'],'East':['Chonburi','Rayong','Chachoengsao'],'West':['Nakhon Pathom','Kanchanaburi','Ratchaburi'],'South':['Surat Thani','Phuket','Songkhla']}
 branches=[]
 for region,provinces in places.items():
  for province in provinces:
   i=len(branches);opened=['2025-04-01','2025-07-01','2025-10-01','2026-01-01','2026-04-01','2026-07-01'][i//3] if i%3==2 else '2022-01-01'
   branches.append(dict(store_id=f'TH{i+1:03}',region_id=region,province=province,opened_date=opened,provenance='Synthetic Thailand retail data'))
 branches=pd.DataFrame(branches);branches.to_csv(out/'branches.csv',index=False)
 catalog=[]
 for ci,cat in enumerate(cats):
  for j in range(30): catalog.append(dict(item_id=f'{cat}_{j+1:03}',cat_id=cat,dept_id=f'{cat}_{1+j//15}',price=float(rng.choice([29,49,79,99,149,199,299,499,799])),cost_ratio=float(np.clip(rng.normal([.65,.60,.62,.68,.55,.58][ci],.04),.45,.8))))
 catalog=pd.DataFrame(catalog);catalog.to_csv(out/'products.csv',index=False)
 suppliers=pd.DataFrame([dict(supplier_id=f'SUP{i+1:02}',supplier_name=f'Mock {c.title()} Supply',cat_id=c,promised_lead_days=3+i%4) for i,c in enumerate(cats)]);suppliers.to_csv(supply/'suppliers.csv',index=False)
 snapshots=[];orders=[];receipt_parts=[]
 for branch in branches.itertuples():
  live=dates[dates>=branch.opened_date];n=len(live);scale=rng.uniform(.65,1.4);pending={};balances=rng.integers(12,35,len(catalog));initial=balances.copy();outstanding=np.zeros(len(catalog),int)
  for di,date in enumerate(live):
   opening=balances.copy();received=np.zeros(len(catalog),int)
   for j,qty,order in pending.pop(date,[]):
    balances[j]+=qty;received[j]+=qty;outstanding[j]-=order['ordered_units'];order['actual_receipt_date']=date.strftime('%Y-%m-%d');order['received_units']=qty;order['short_closed_units']=order['ordered_units']-qty;order['status']='Received'
   seasonal=CONFIG['effects']['weekend'] if date.dayofweek>=5 else 1
   if date.month==4 and 10<=date.day<=16:seasonal*=CONFIG['effects']['songkran']
   if date.month in [11,12]:seasonal*=CONFIG['effects']['year_end']
   ramp=min(1,.6+di/180*.4)
   lam=np.full(len(catalog),1.6*scale*seasonal*ramp)
   if date.month in [5,6]:lam[catalog.cat_id.eq('STATIONERY')]*=CONFIG['effects']['school']
   if date.month in [6,7,8,9,10]:lam[catalog.cat_id.eq('CLEANING')]*=CONFIG['effects']['rain_cleaning']
   demand=rng.poisson(lam);sold=np.minimum(demand,balances);balances-=sold
   shrink=np.minimum(balances,(rng.random(len(catalog))<.002).astype(int));balances-=shrink
   for j in range(len(catalog)):
    snapshots.append((date.strftime('%Y-%m-%d'),branch.store_id,catalog.item_id[j],catalog.cat_id[j],int(opening[j]),int(received[j]),0,int(sold[j]),int(shrink[j]),int(balances[j]),int(demand[j]-sold[j]),int(initial[j]) if di==0 else 0))
    position=balances[j]+outstanding[j]
    lead=int(suppliers.promised_lead_days[j//30])
    if position<lam[j]*(lead+3):
     qty=max(1,int(np.ceil(lam[j]*18-position)));promised=date+pd.Timedelta(days=lead);delay=0 if rng.random()<.88 else int(rng.choice([1,2,4]));arrival=promised+pd.Timedelta(days=delay)
     order=dict(po_line_id=f'PO{len(orders)+1:08}',supplier_id=suppliers.supplier_id[j//30],store_id=branch.store_id,item_id=catalog.item_id[j],cat_id=catalog.cat_id[j],order_date=date.strftime('%Y-%m-%d'),promised_date=promised.strftime('%Y-%m-%d'),ordered_units=qty,actual_receipt_date=None,received_units=0,short_closed_units=0,status='Open');orders.append(order);outstanding[j]+=qty;pending.setdefault(arrival,[]).append((j,max(1,int(qty*rng.uniform(.92,1))),order))
   item_indices=np.repeat(np.arange(len(catalog)),sold)
   if len(item_indices):
    nr=max(1,int(len(item_indices)/2.8));receipt_ids=rng.integers(0,nr,len(item_indices));unique=np.unique(receipt_ids);mapping=dict(zip(unique,range(len(unique))))
    frame=pd.DataFrame({'receipt_no':receipt_ids,'j':item_indices}).groupby(['receipt_no','j']).size().reset_index(name='units')
    frame['receipt_id']=[f'{branch.store_id}-{date:%Y%m%d}-{mapping[i]:04}' for i in frame.receipt_no];frame['date']=date.strftime('%Y-%m-%d');frame['month']=date.strftime('%Y-%m');frame['store_id']=branch.store_id;frame['item_id']=catalog.item_id.to_numpy()[frame.j];frame['cat_id']=catalog.cat_id.to_numpy()[frame.j];frame['dept_id']=catalog.dept_id.to_numpy()[frame.j];frame['region_id']=branch.region_id
    frame['unit_price']=catalog.price.to_numpy()[frame.j]*(1-rng.choice([0,.05,.10],len(frame),p=[.85,.1,.05]));frame['revenue']=frame.units*frame.unit_price
    frame['cost_of_goods']=frame.units*catalog.price.to_numpy()[frame.j]*catalog.cost_ratio.to_numpy()[frame.j]*(1+(int(branch.store_id[-3:])%5-2)*.015)
    receipt_parts.append(frame.drop(columns=['receipt_no','j']))
  print(branch.store_id,'generated',flush=True)
 lines=pd.concat(receipt_parts,ignore_index=True);lines.to_parquet(out/'sales_lines.parquet',index=False)
 stock=pd.DataFrame(snapshots,columns=['date','store_id','item_id','cat_id','opening_units','receipt_units','emergency_units','sold_units','shrink_units','closing_units','unmet_demand_units','initial_units']);stock.to_parquet(supply/'daily_inventory.parquet',index=False)
 movements=[]
 for field,kind,sign in [('initial_units','OPENING',1),('receipt_units','PO_RECEIPT',1),('sold_units','SALE',-1),('shrink_units','SHRINK',-1)]:
  f=stock[stock[field]>0][['date','store_id','item_id',field]].rename(columns={field:'units_signed'});f.units_signed*=sign;f['movement_type']=kind;movements.append(f)
 ledger=pd.concat(movements,ignore_index=True);ledger['movement_id']=[f'MOV{i:09}' for i in range(len(ledger))]
 po=pd.DataFrame(orders);lookup=po[po.status.eq('Received')][['actual_receipt_date','store_id','item_id','po_line_id']].rename(columns={'actual_receipt_date':'date'})
 ledger=ledger[ledger.movement_type.ne('PO_RECEIPT')].copy();ledger['po_line_id']=''
 receipts=po[po.status.eq('Received')][['actual_receipt_date','store_id','item_id','received_units','po_line_id']].rename(columns={'actual_receipt_date':'date','received_units':'units_signed'});receipts['movement_type']='PO_RECEIPT'
 ledger=pd.concat([ledger.drop(columns='movement_id'),receipts],ignore_index=True);ledger['movement_id']=[f'MOV{i:09}' for i in range(len(ledger))];ledger.to_parquet(supply/'stock_movements.parquet',index=False);po.to_csv(supply/'purchase_order_lines.csv',index=False)

 group=['month','store_id','region_id','item_id','dept_id','cat_id'];product=lines.groupby(group,as_index=False).agg(units=('units','sum'),revenue=('revenue','sum'),cost_of_goods=('cost_of_goods','sum'))
 stock['month']=stock.date.str[:7];coverage=stock.groupby(['month','store_id']).agg(observed_days=('date','nunique'),period_start=('date','min'),period_end=('date','max')).reset_index();product=product.merge(coverage,on=['month','store_id'],validate='many_to_one');product['priced_units']=product.units;product['avg_sell_price']=product.revenue/product.units
 inv=stock.groupby(['month','store_id','item_id']).agg(avg_units=('closing_units','mean'),stockout_item_days=('closing_units',lambda s:s.eq(0).sum()),item_days=('date','count')).reset_index();product=product.merge(inv,on=['month','store_id','item_id'],validate='one_to_one');product['inventory_cost']=product.avg_units*(product.cost_of_goods/product.units);product.to_csv(out/'monthly_product.csv',index=False)
 category=product.groupby(['month','store_id','region_id','cat_id'],as_index=False).agg(units=('units','sum'),priced_units=('priced_units','sum'),revenue=('revenue','sum'),cost_of_goods=('cost_of_goods','sum'),inventory_cost=('inventory_cost','sum'),stockout_item_days=('stockout_item_days','sum'),item_days=('item_days','sum'),observed_days=('observed_days','first'),period_start=('period_start','first'),period_end=('period_end','first'));category.to_csv(out/'monthly_category.csv',index=False)
 store=category.groupby(['month','store_id','region_id'],as_index=False).agg(revenue=('revenue','sum'),observed_days=('observed_days','first'));trans=lines.groupby(['month','store_id']).receipt_id.nunique();store['transactions']=[trans.loc[(r.month,r.store_id)] for r in store.itertuples()];store['traffic']=(store.transactions/.62).round().astype(int)
 for col,rate in [('variable_logistics',.025),('variable_selling',.015),('variable_labor',.02)]:store[col]=store.revenue*rate
 base={branch:180*1.6*catalog.price.mean()*.99*(.75+(int(branch[-3:])%7)*.1) for branch in branches.store_id};rate=dict(zip(branches.store_id,np.linspace(.12,.30,18)))
 for col,fraction in [('fixed_rent',.4),('fixed_salaries',.45),('fixed_overhead',.15)]:store[col]=store.store_id.map(base)*store.store_id.map(rate)*store.observed_days*fraction
 store['operating_expenses']=store[['variable_logistics','variable_selling','variable_labor','fixed_rent','fixed_salaries','fixed_overhead']].sum(axis=1);store.to_csv(out/'monthly_store_mock.csv',index=False)
 rc=lines.groupby(['receipt_id','month','store_id','cat_id'],as_index=False)[['units','revenue','cost_of_goods']].sum();rc=rc.merge(store[['month','store_id','revenue','variable_logistics','variable_selling','variable_labor','fixed_rent','fixed_salaries','fixed_overhead']],on=['month','store_id'],suffixes=('','_store'),validate='many_to_one');rc['variable_opex']=rc.revenue/rc.revenue_store*(rc.variable_logistics+rc.variable_selling+rc.variable_labor);rc['allocated_fixed_cost']=rc.revenue/rc.revenue_store*(rc.fixed_rent+rc.fixed_salaries+rc.fixed_overhead)
 receipt_dir=out/'receipts';receipt_dir.mkdir(exist_ok=True)
 for (month,branch),f in rc.groupby(['month','store_id']):f[['receipt_id','month','store_id','cat_id','units','revenue','cost_of_goods','variable_opex','allocated_fixed_cost']].to_parquet(receipt_dir/f'{month}_{branch}.parquet',index=False)
 rc.groupby(['month','store_id','cat_id'],as_index=False).agg(receipts=('receipt_id','nunique'),units=('units','sum'),revenue=('revenue','sum'),cost_of_goods=('cost_of_goods','sum'),variable_opex=('variable_opex','sum'),allocated_fixed_cost=('allocated_fixed_cost','sum')).to_csv(out/'receipt_category_month.csv',index=False)
 manifest=dict(seed=CONFIG['seed'],receipts=int(lines.receipt_id.nunique()),receipt_category_rows=len(rc),partitions=len(store),currency='THB',provenance='Synthetic Thailand retail data');(out/'receipt_manifest.json').write_text(json.dumps(manifest,indent=2))
 sm=dict(seed=CONFIG['seed'],as_of=CONFIG['end'],sample_items=180,sku_store_pairs=3240,inventory_rows=len(stock),movements=len(ledger),po_lines=len(po),provenance='Synthetic Thailand retail data');(supply/'manifest.json').write_text(json.dumps(sm,indent=2));(out/'generation_config.json').write_text(json.dumps(CONFIG,indent=2))
 budget=[]
 for r in store.itertuples():
  target=180*1.6*catalog.price.mean()*.99*(.75+(int(r.store_id[-3:])%7)*.1)*r.observed_days
  for col in ['revenue','cost_of_goods','variable_logistics','variable_selling','variable_labor','fixed_rent','fixed_salaries','fixed_overhead']:
   amount=target if col=='revenue' else target*.64 if col=='cost_of_goods' else target*dict(variable_logistics=.024,variable_selling=.014,variable_labor=.019)[col] if col.startswith('variable') else target*.21*dict(fixed_rent=.4,fixed_salaries=.45,fixed_overhead=.15)[col]
   budget.append(dict(plan_version='TH_PLAN_V1',month=r.month,store_id=r.store_id,line=col,budget_amount=amount,observed_days=r.observed_days))
 pd.DataFrame(budget).to_csv(out/'budget_lines.csv',index=False)
 print(manifest,flush=True)
if __name__=='__main__':build()
