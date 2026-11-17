"""Executive visuals built from filtered analytical facts."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

CATEGORY_COLORS={'TOOLS':'#0072B2','HOUSEHOLD':'#009E73','CLEANING':'#56B4E9','ELECTRICAL':'#D55E00','STATIONERY':'#8064A2','LIFESTYLE':'#B28500'}
STATUS_COLORS={'Profitable':'#009E73','Loss-making':'#D55E00','Break-even':'#757575'}

def performance_matrix(branches):
    b=branches[branches.active & branches.revenue.gt(0)].copy()
    if b.empty:
        return go.Figure().add_annotation(text='No active branches with revenue in this selection',showarrow=False).update_layout(height=440)
    b['cm_pct']=100*b.contribution/b.revenue
    b['revenue_m']=b.revenue/1e6
    xmid=float(b.revenue_m.median()); ymid=float(b.cm_pct.median())
    xpad=max(float(b.revenue_m.max()-b.revenue_m.min())*.25,.1)
    ypad=max(float(b.cm_pct.max()-b.cm_pct.min())*.35,.15)
    xmin=max(0,float(b.revenue_m.min())-xpad); xmax=float(b.revenue_m.max())+xpad
    ymin=float(b.cm_pct.min())-ypad; ymax=float(b.cm_pct.max())+ypad
    b['Position']=np.select([(b.revenue_m>=xmid)&(b.cm_pct>=ymid),(b.revenue_m<xmid)&(b.cm_pct>=ymid),(b.revenue_m>=xmid)&(b.cm_pct<ymid)],['Star stores','High margin / low sales','High sales / low margin'],default='Underperform')
    palette={'Star stores':'#0072B2','High margin / low sales':'#009E73','High sales / low margin':'#E69F00','Underperform':'#D55E00'}
    fig=px.scatter(b,x='revenue_m',y='cm_pct',text='store_id',color='Position',color_discrete_map=palette,hover_data={'revenue_m':':.3f','cm_pct':':.2f','operating_profit':':,.0f'},labels={'revenue_m':'Revenue (THB million)','cm_pct':'Contribution margin (%)'})
    for x0,x1,y0,y1,color in [(xmin,xmid,ymid,ymax,'#009E73'),(xmid,xmax,ymid,ymax,'#0072B2'),(xmin,xmid,ymin,ymid,'#D55E00'),(xmid,xmax,ymin,ymid,'#E69F00')]:
        fig.add_shape(type='rect',x0=x0,x1=x1,y0=y0,y1=y1,fillcolor=color,opacity=.09,line_width=0,layer='below')
    fig.add_vline(x=xmid,line_dash='dash',line_color='#8B98A5');fig.add_hline(y=ymid,line_dash='dash',line_color='#8B98A5')
    for x,y,label in [(xmin+xpad*.12,ymax,'High margin / low sales'),(xmax-xpad*.12,ymax,'Star stores'),(xmin+xpad*.12,ymin,'Underperform'),(xmax-xpad*.12,ymin,'High sales / low margin')]:
        fig.add_annotation(x=x,y=y,text=label,showarrow=False,xanchor='left' if x<xmid else 'right',yanchor='top' if y==ymax else 'bottom',font_size=13)
    fig.update_traces(marker={'size':19,'line':{'color':'white','width':2}},textposition='top center',textfont_size=13)
    # Spread labels around nearby points without depending on particular branch IDs.
    label_positions={}
    occupied=[]
    candidates=[('top center',-22,-29),('middle right',14,-8),('middle left',-60,-8),('bottom center',-22,14),('top right',14,-29),('bottom left',-60,14)]
    points=[((r.revenue_m-xmin)/(xmax-xmin)*600,(ymax-r.cm_pct)/(ymax-ymin)*360,r.store_id) for r in b.itertuples()]
    for x,y,name in points:
        scores=[]
        for pos,dx,dy in candidates:
            rect=(x+dx,y+dy,x+dx+48,y+dy+18)
            overlap=sum(max(0,min(rect[2],q[2])-max(rect[0],q[0]))*max(0,min(rect[3],q[3])-max(rect[1],q[1])) for q in occupied)
            overlap+=sum(300 for px,py,_ in points if rect[0]-5<px<rect[2]+5 and rect[1]-5<py<rect[3]+5)
            scores.append((overlap,pos,rect))
        _,pos,rect=min(scores,key=lambda item:item[0])
        occupied.append(rect);label_positions[name]=pos
    for trace in fig.data:
        trace.textposition=[label_positions.get(label,'top center') for label in trace.text]
    fig.update_layout(height=440,showlegend=False,xaxis=dict(range=[xmin,xmax],tickformat='.1f',showgrid=False),yaxis=dict(range=[ymin,ymax],tickformat='.1f',dtick=2),margin=dict(l=25,r=25,t=25,b=35))
    return fig

def decomposition_tree(products, view='geography'):
    """A prefix-preserving hierarchy; branch maturity can be supplied by the mock dimension."""
    if view == 'geography':
        fields = ['branch_type', 'region_id', 'store_id'] if 'branch_type' in products else ['region_id', 'store_id']
        headings = ['SELECTED REVENUE'] + (['BRANCH MATURITY'] if 'branch_type' in fields else []) + ['REGION', 'BRANCH']
    else:
        fields = ['cat_id', 'dept_id']
        headings = ['SELECTED REVENUE', 'CATEGORY', 'DEPARTMENT']
    fig = go.Figure()
    if products.empty:
        return fig.update_layout(height=620)
    total = float(products.revenue.sum())
    nodes = {(): {'value': total, 'children': []}}
    def populate(path, frame, depth):
        if depth == len(fields):
            return
        field = fields[depth]
        for name, value in frame.groupby(field).revenue.sum().sort_values(ascending=False).items():
            child = path + (name,)
            nodes[path]['children'].append(child)
            nodes[child] = {'value': float(value), 'children': []}
            populate(child, frame[frame[field].eq(name)], depth+1)
    populate((), products, 0)
    leaves = [path for path, node in nodes.items() if not node['children']]
    for path, pos in zip(leaves, np.linspace(.88, .08, len(leaves)) if len(leaves)>1 else [.48]):
        nodes[path]['y'] = float(pos)
    def position(path):
        if nodes[path]['children']:
            nodes[path]['y'] = float(np.mean([position(child) for child in nodes[path]['children']]))
        return nodes[path]['y']
    position(())
    chart_height=max(660,len(leaves)*80+150) if len(fields)==3 else max(570,len(leaves)*76+130)
    xs = np.linspace(.01, .76, len(fields)+1)
    width = .16 if len(fields)==3 else .22
    # Render level-by-level for stable tracing and reconciliation checks.
    for depth in range(len(fields)+1):
        for path, node in nodes.items():
            if len(path) != depth:
                continue
            x, y = float(xs[depth]), node['y']
            parent_value = nodes[path[:-1]]['value'] if path else total
            share = node['value']/parent_value if parent_value else 0
            label = str(path[-1]) if path else 'All selected'
            if path and fields[-1]=='store_id' and depth==len(fields) and 'province' in products:
                label += ' / ' + products.loc[products.store_id.eq(path[-1]),'province'].iloc[0]
            if label in CATEGORY_COLORS:
                label = label.title()
            color = CATEGORY_COLORS.get(path[0] if path else '', '#087E8B')
            if path and path[0]=='New branch': color='#8064A2'
            if not path: color='#173E58'
            fig.add_shape(type='rect', x0=x, x1=x+width, y0=y+.02-4/chart_height, y1=y+.02+4/chart_height, fillcolor='#E7EEF3', line_width=0)
            fig.add_shape(type='rect', x0=x, x1=x+width*share, y0=y+.02-4/chart_height, y1=y+.02+4/chart_height, fillcolor=color, line_width=0)
            fig.add_annotation(x=x, y=y+.02-8/chart_height, text=f'<b>{label}</b><br>{node["value"]/1e6:,.2f} M', showarrow=False, xanchor='left', yanchor='top', align='left', font=dict(size=15, color='#173E58'))
            fig.add_trace(go.Scatter(x=[x+width/2], y=[y+.02], mode='markers', customdata=[[node['value'], parent_value]], marker=dict(size=28, opacity=0), showlegend=False, hovertemplate=f'{label}<br>Revenue: {node["value"]/1e6:,.3f} THB million<br>Share of parent: {share:.1%}<extra></extra>'))
            if path:
                x0, x1 = float(xs[depth-1])+width, x
                y0, y1 = nodes[path[:-1]]['y']+.02, y+.02
                mid=(x0+x1)/2
                fig.add_shape(type='path', path=f'M {x0},{y0} C {mid},{y0} {mid},{y1} {x1},{y1}', line=dict(color='#BDD0DC', width=1.5), layer='below')
    for x, title in zip(xs, headings):
        fig.add_annotation(x=float(x), y=.99, text=title, showarrow=False, xanchor='left', font=dict(size=13,color='#64748B'))
    fig.update_layout(height=chart_height, xaxis=dict(range=[-.015,1.04], visible=False, fixedrange=True), yaxis=dict(range=[-.025,1.04], visible=False, fixedrange=True), showlegend=False, margin=dict(l=10,r=15,t=10,b=10),paper_bgcolor='white',plot_bgcolor='white')
    return fig
