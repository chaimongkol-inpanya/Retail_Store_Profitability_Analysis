import plotly.io as pio
import streamlit as st


class DashboardTheme:
    @staticmethod
    def apply():
        pio.templates.default = "plotly_white"
        template = pio.templates["plotly_white"]
        template.layout.colorway = [
            "#087E8B",
            "#4063A5",
            "#E5A04B",
            "#8064A2",
            "#55A995",
        ]
        template.layout.font = dict(family="Arial", color="#172B4D", size=15)
        template.layout.paper_bgcolor = "rgba(0,0,0,0)"
        template.layout.plot_bgcolor = "rgba(0,0,0,0)"
        template.layout.height = 300
        template.layout.hoverlabel = dict(font_size=14, bgcolor="white")
        template.layout.xaxis = dict(
            gridcolor="#EDF1F5", tickfont_size=13, title_font_size=14
        )
        template.layout.yaxis = dict(
            gridcolor="#EDF1F5", tickfont_size=13, title_font_size=14
        )
        template.layout.margin = dict(l=16, r=16, t=48, b=28)
        st.markdown(
            """<style>
        .dashboard-header {background:#173E58;color:white;border-radius:10px;padding:20px 28px;margin-bottom:14px;border-left:6px solid #13B3C9;}
        .dashboard-header h1 {color:white;margin:4px 0;padding:0;}
        .dashboard-header > span {color:#7CDCE4;font-size:12px;letter-spacing:2px;font-weight:700;}
        .dashboard-header p {color:#C5D9E4;margin:4px 0 0;font-size:13px;}
        .block-container {max-width:1920px;padding-top:4rem;padding-bottom:3rem;}
        h1 {font-size:2.8rem!important;letter-spacing:-1px;}
        h2,h3 {letter-spacing:-.4px;}
        h3 {font-size:1.65rem!important;font-weight:700!important;margin-top:1.2rem;}
        [data-testid="stMarkdownContainer"] strong {font-size:1.05rem;}
        [data-testid="stCaptionContainer"] {color:#53667A;font-size:14px;line-height:1.55;}
        [data-testid="stMetricLabel"] {font-size:13px;min-height:40px;}
        [data-testid="stMetricLabel"] p {white-space:normal!important;text-overflow:clip!important;line-height:1.3!important;}
        [data-testid="stMetric"] {background:white;border:1px solid #E1E7EF;border-radius:12px;padding:14px;box-shadow:0 3px 12px #172b4d05;}
        [data-testid="stMetric"] {min-height:118px;transition:box-shadow .15s ease;}
        [data-testid="stMetric"]:hover {box-shadow:0 5px 18px #172b4d12;}
        [data-testid="stMetricValue"] {font-size:1.7rem;}
        [data-testid="stSidebar"] {border-right:1px solid #E1E7EF;}
        [data-testid="stPlotlyChart"] {border:1px solid #E1E7EF;border-radius:12px;background:white;padding:8px;}
        [data-baseweb="tab-list"] {gap:10px;border-bottom:1px solid #DCE5EE;margin-bottom:18px;}
        [data-baseweb="tab"] {padding:14px 20px;border-radius:9px 9px 0 0;font-size:16px;font-weight:600;}
        [data-baseweb="tab"][aria-selected="true"] {background:#E4F3F5;color:#075D68;}
        </style>""",
            unsafe_allow_html=True,
        )
        colors = {
            "blue": ("#0072B2", "#EDF6FC"),
            "teal": ("#087C68", "#EAF7F1"),
            "amber": ("#946000", "#FFF7E5"),
            "red": ("#B42335", "#FFF0F1"),
            "navy": ("#173E58", "#EAF0F6"),
            "slate": ("#586A7D", "#F0F3F7"),
        }
        rules = []
        for tone, (accent, background) in colors.items():
            scope = f'[class*="st-key-kpi_"][class*="_{tone}"]'
            rules.append(
                f'{scope} [data-testid="stMetric"] {{background:linear-gradient(135deg,{background},white);border-left:4px solid {accent};}}'
            )
            rules.append(
                f'{scope} [data-testid="stMetricValue"] {{color:{accent};font-weight:700;}}'
            )
        st.markdown("<style>" + "".join(rules) + "</style>", unsafe_allow_html=True)
