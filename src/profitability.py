"""Reproducible illustrative branch operating costs, for the Thailand scenario."""
import numpy as np

def branch_pl(category, stores):
    branch=category.groupby('store_id').agg(revenue=('revenue','sum'),cogs=('cost_of_goods','sum'),units=('units','sum'))
    fields=['variable_logistics','variable_selling','variable_labor','fixed_rent','fixed_salaries','fixed_overhead']
    branch=branch.join(stores.groupby('store_id')[fields].sum(),validate='one_to_one')
    branch['variable_costs']=branch.cogs+branch[fields[:3]].sum(axis=1)
    branch['contribution']=branch.revenue-branch.variable_costs
    branch['fixed_costs']=branch[fields[3:]].sum(axis=1)
    branch['operating_profit']=branch.contribution-branch.fixed_costs
    branch['active']=branch.units.gt(0)
    rounded=branch.operating_profit.round(2)
    branch['status']=np.select([~branch.active,rounded.gt(0),rounded.lt(0)],['Inactive','Profitable','Loss-making'],default='Break-even')
    return branch.reset_index()
