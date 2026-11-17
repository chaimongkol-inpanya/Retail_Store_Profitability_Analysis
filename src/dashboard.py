from pathlib import Path
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.profitability import branch_pl
from src.operating_views import planning_section
from src.cards import kpi
from src.metrics import percent
from src.visuals import CATEGORY_COLORS, performance_matrix, decomposition_tree

ROOT=Path(__file__).resolve().parents[1]
@st.cache_data
def receipt_summary(version):
    return pd.read_csv(ROOT/'data/receipt_category_month.csv')

def executive_dashboard(data,products,metrics,stores,operations):
    branches=branch_pl(data,stores)
    t=branches.select_dtypes(include='number').sum()
    cards=st.columns(5)
    tones=['blue','amber','teal','slate','teal' if t.operating_profit>=0 else 'red']
    for col,label,value,tone in zip(cards,['Revenue','Variable costs','Contribution margin','Fixed costs','Operating profit'],[t.revenue,t.variable_costs,t.contribution,t.fixed_costs,t.operating_profit],tones):
        kpi(col,f'{label.upper()} (THB million)',f'{value/1e6:,.2f}',key=label.replace(' ','_'),tone=tone)
    st.caption('Synthetic Thailand retail sales | All costs and branch profitability are simulated | Currency appears in headers; no currency conversion applied.')
    active=int(branches.active.sum()); profitable=int(branches.status.eq('Profitable').sum())
    cards=st.columns(5)
    kpi(cards[0],'ACTIVE BRANCHES',active,key='active',tone='navy')
    kpi(cards[1],'PROFITABLE',profitable,key='profitable',tone='teal')
    losses=int(branches.status.eq('Loss-making').sum())
    kpi(cards[2],'LOSS-MAKING',losses,key='losses',tone='red' if losses else 'slate')
    kpi(cards[3],'PROFITABLE SHARE',percent(profitable/active if active else None),key='profitable_share',tone='teal')
    kpi(cards[4],'CONTRIBUTION MARGIN',percent(t.contribution/t.revenue if t.revenue else None),key='margin_ratio',tone='blue')
    st.caption('Active = positive units sold. Profitability uses period operating profit rounded to cents. Break-even branches remain in the active denominator.')
    left,right=st.columns(2)
    with left:
        st.subheader('Operating P&L')
        labels=['Revenue','Goods','Logistics','Selling','Variable labor','Contribution','Rent','Salaries','Overhead','Operating profit']
        amounts=[t.revenue,-t.cogs,-t.variable_logistics,-t.variable_selling,-t.variable_labor,t.contribution,-t.fixed_rent,-t.fixed_salaries,-t.fixed_overhead,t.operating_profit]
        fig=go.Figure(go.Waterfall(orientation='h',y=labels,x=[v/1e6 for v in amounts],measure=['absolute']+['relative']*4+['total']+['relative']*3+['total'],text=[f'{v/1e6:,.2f}' for v in amounts],textposition='outside',hovertemplate='%{y}<br>%{x:.3f} THB million<extra></extra>',increasing={'marker':{'color':'#009E73'}},decreasing={'marker':{'color':'#D55E00'}},totals={'marker':{'color':'#173E58'}},cliponaxis=False, connector={'line':{'color':'#D7E0E7'}}))
        fig.update_layout(height=480,xaxis_title='THB million',showlegend=False,margin=dict(l=125,r=55,t=20,b=50),yaxis=dict(autorange='reversed',tickfont_size=14),xaxis=dict(tickformat='.1f',zeroline=False,range=[-max(t.revenue*.10/1e6,.01),max(t.revenue*1.14/1e6,.01)]),uniformtext_minsize=12)
        st.plotly_chart(fig,width='stretch',config={'displayModeBar':False})
        st.caption('Contribution = revenue - variable costs. Operating profit = contribution - fixed costs.')
    with right:
        st.subheader('Store performance matrix')
        st.plotly_chart(performance_matrix(branches).update_layout(height=480),width='stretch',config={'displayModeBar':False})
        st.caption('Dashed lines = median revenue and median contribution margin of selected active branches. Quadrants are relative positions, not profit/loss classifications. Margin variation comes from the mock cost model.')
    planning_section(data, stores, operations[0])
    st.subheader('Where revenue comes from')
    st.caption('Two views of the same selected revenue. Read left to right. Amounts are THB million; each bar shows its share of its immediate parent. Hover for exact amounts and percentages.')
    st.markdown('**Branch maturity, region and branch**')
    st.plotly_chart(decomposition_tree(products, 'geography'),width='stretch',config={'displayModeBar':False})
    st.caption('Mock maturity as of ' + data.period_end.max() + ': New branch = age under 365 days; Established branch = 365 days or older. Mock opening dates are on or before the first included sale. Classification applies to all selected sales at this period-end date.')
    st.markdown('**Category and department**')
    st.plotly_chart(decomposition_tree(products, 'assortment'),width='stretch',config={'displayModeBar':False})
    st.caption('Both trees reconcile independently to total revenue. These are two views of the same sales; totals must not be added together.')
    receipt=receipt_summary((ROOT/'data/receipt_category_month.csv').stat().st_mtime_ns)
    keys=data[['month','store_id']].drop_duplicates()
    r=receipt.merge(keys,on=['month','store_id'],validate='many_to_one')
    c=r.groupby('cat_id',as_index=False).agg(receipts=('receipts','sum'),revenue=('revenue','sum'),cogs=('cost_of_goods','sum'),variable_opex=('variable_opex','sum'),fixed=('allocated_fixed_cost','sum'))
    c['total_cost']=c.cogs+c.variable_opex+c.fixed;c['profit']=c.revenue-c.total_cost
    for name in ['revenue','total_cost','profit']: c[name+'_per_receipt']=c[name]/c.receipts
    left,right=st.columns(2)
    with left:
        st.subheader('Category economics per receipt')
        long=c.melt(id_vars='cat_id',value_vars=['revenue_per_receipt','total_cost_per_receipt','profit_per_receipt'],var_name='Measure',value_name='THB per receipt')
        long['Measure']=long.Measure.map({'revenue_per_receipt':'Revenue','total_cost_per_receipt':'Allocated cost','profit_per_receipt':'Operating profit'})
        long['Category']=long.cat_id.str.title()
        fig=px.bar(long,y='Category',x='THB per receipt',color='Measure',barmode='group',orientation='h',text_auto='.2f',color_discrete_map={'Revenue':'#0072B2','Allocated cost':'#E69F00','Operating profit':'#009E73'})
        fig.update_traces(textposition='outside',cliponaxis=False,hovertemplate='%{y}<br>%{x:.2f} THB / receipt<extra>%{fullData.name}</extra>')
        fig.update_layout(height=480,legend=dict(orientation='h',y=1.16,font_size=13),margin=dict(l=90,r=60,t=55,b=45),xaxis=dict(zeroline=True,zerolinecolor='#CBD5E1'))
        st.plotly_chart(fig,width='stretch')
        st.caption('Denominator: synthetic receipts containing that category. A receipt can contain multiple categories, so category receipt counts are not additive. Total cost includes variable costs and fixed costs allocated by revenue within branch/month.')
    with right:
        st.subheader('Category revenue mix')
        fig=px.pie(c,names='cat_id',values='revenue',color='cat_id',color_discrete_map=CATEGORY_COLORS,hole=.65)
        fig.update_traces(textinfo='label+percent',textposition='outside',textfont_size=15,marker_line_color='white',marker_line_width=3,hovertemplate='%{label}<br>%{percent}<extra></extra>')
        fig.update_layout(height=480,showlegend=False,margin=dict(l=85,r=85,t=45,b=45),annotations=[dict(text=f'{t.revenue/1e6:,.2f} M<br><span style="font-size:12px">THB revenue</span>',x=.5,y=.5,font_size=23,showarrow=False)])
        st.plotly_chart(fig,width='stretch',config={'displayModeBar':False})
        st.caption('Each of the six categories has a consistent color across charts. Labels identify every segment.')
    trend=data.groupby(['month','cat_id'],as_index=False).agg(revenue=('revenue','sum'),days=('observed_days','first'))
    trend['daily_sales_k']=trend.revenue/trend.days/1000
    left,right=st.columns(2)
    with left:
        st.subheader('Category sales trend')
        fig=px.line(trend,x='month',y='daily_sales_k',color='cat_id',color_discrete_map=CATEGORY_COLORS,markers=True,labels={'month':'Month','daily_sales_k':'THB thousand / observed day','cat_id':'Category'})
        fig.update_traces(line_width=3,marker_size=6)
        fig.update_layout(height=max(480,len(branches)*26+90),legend=dict(orientation='h',y=1.17,font_size=13),margin=dict(l=65,r=20,t=55,b=55),xaxis=dict(tickformat='%b %y',dtick='M2'),yaxis=dict(tickformat=',.0f'),hovermode='x unified')
        st.plotly_chart(fig,width='stretch')
        st.caption('Daily averages avoid artificial drops in partial months. Price coverage: '+percent(metrics.coverage))
    with right:
        st.subheader('Branch operating P&L')
        ranking=branches.sort_values('operating_profit').copy()
        ranking['Operating profit (THB million)']=ranking.operating_profit/1e6
        fig=px.bar(ranking,x='Operating profit (THB million)',y='store_id',color='status',orientation='h',text_auto='.2f',color_discrete_map={'Profitable':'#009E73','Loss-making':'#D55E00','Break-even':'#757575','Inactive':'#A0A0A0'},labels={'store_id':'Branch','status':'Status'})
        fig.update_layout(height=max(480,len(branches)*26+90),legend=dict(orientation='h',y=1.16,font_size=13),margin=dict(l=90,r=60,t=55,b=45),xaxis=dict(zeroline=True,zerolinecolor='#CBD5E1'))
        for trace in fig.data:
            trace.update(text=[f'{v:+.2f}' for v in trace.x],texttemplate='%{text}',textposition='outside',cliponaxis=False)
        profit_limit=max(ranking['Operating profit (THB million)'].abs().max()*1.3,.01)
        fig.update_layout(xaxis_range=[-profit_limit,profit_limit])
        fig.update_layout(yaxis=dict(title='',categoryorder='array',categoryarray=ranking.store_id.tolist()),xaxis_title='Operating profit (THB million)')
        fig.add_vline(x=0,line_color='#64748B',line_width=1)
        st.plotly_chart(fig,width='stretch')
        st.download_button('Download branch P&L',branches.assign(provenance='synthetic Thailand data revenue; simulated costs').to_csv(index=False),'branch_pl_thb.csv','text/csv')
    with st.expander('Data pipeline, provenance & reconciliation'):
        manifest=json.loads((ROOT/'data/receipt_manifest.json').read_text())
        st.markdown('**Synthetic daily demand** → reshape daily item sales → join calendar and weekly prices → aggregate item/store/month → generate operating-cost scenarios → synthesize receipt/category facts → aggregate receipt mart → calculate executive KPIs.')
        st.markdown(f"**{manifest['receipts']:,} synthetic receipts · {manifest['receipt_category_rows']:,} category lines · {manifest['partitions']} branch/month partitions.**")
        st.caption('All receipt item lines are generated from inventory-constrained fulfilled demand and catalog prices after simulated discounts. Their revenue and costs aggregate consistently to category and branch totals. Fixed costs are allocated by revenue share.')
        st.markdown('**Source:** Seeded synthetic Thailand retail generator. See README.md for keys, formulas and assumptions.')
        st.markdown('**Planning pipeline:** branch/month baseline -> seeded budget lines -> matched actual P&L -> variance and alert rules. **Supply pipeline:** sampled synthetic Thailand data daily sales -> simulated PO log -> signed stock movements -> reconciled daily balances -> due-date/as-of supplier analysis.')
        st.caption('All records are synthetic Thailand retail data. Supply-constrained transactions, stock movements and financial totals share the same sales facts.')
        selected_budget = operations[0].merge(keys, on=['month', 'store_id'], validate='many_to_one')
        st.download_button('Download scenario budget lines', selected_budget.to_csv(index=False), 'scenario_budget_lines_thb.csv', 'text/csv')
        st.download_button('Download filtered receipt-category mart',r.assign(provenance='Synthetic receipts; synthetic Thailand data-derived revenue; simulated costs').to_csv(index=False),'receipt_category_mart_thb.csv','text/csv')

        sample_key=keys.sort_values(['month','store_id']).iloc[0]
        sample_path=ROOT/'data/receipts'/f'{sample_key.month}_{sample_key.store_id}.parquet'
        sample=pd.read_parquet(sample_path).head(1000)
        st.markdown(f'**Download synthetic facts:** {sample_key.store_id}, {sample_key.month}. Each row is one receipt/category allocation.')
        st.download_button('Download synthetic fact sample (1,000 rows)',sample.assign(provenance='Synthetic receipt-category facts; allocated costs').to_csv(index=False),'synthetic_receipt_sample_thb.csv','text/csv')
