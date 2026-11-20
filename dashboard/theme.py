"""The blue design shared by navigation, page headings and interactive figures."""

import streamlit as st

BLUE = "#2166b5"
NAVY = "#12365b"
PALETTE = [BLUE, "#79a9d7", "#15545d", "#8b6e35", "#7a608e"]


def apply_theme():
    # Use native Streamlit navigation and controls; CSS only tunes the presentation.
    st.html("""
    <style>
      .stMainBlockContainer {max-width:1240px;padding-top:2.1rem;padding-bottom:2rem;}
      h1,h2,h3 {color:#12365b;letter-spacing:-.025em;}
      h1 {font-size:2rem!important;}
      [data-testid="stSidebar"] {border-right:1px solid #dce5ef;}
      [data-testid="stSidebarNav"] a[aria-current="page"] {
        background:#2166b5;color:white;border-radius:7px;
      }
      [data-testid="stSidebarNav"] a[aria-current="page"] span {color:white;}
      [data-testid="stSidebarNav"] a {padding:.55rem .75rem;}
      [data-testid="stSidebarNav"] ul {padding-top:.4rem;}
      .reservoir-brand {color:#12365b;font-size:1.15rem;font-weight:600;
        padding:.2rem 0 1.2rem;line-height:1.25;}
      .area-label {display:inline-block;color:#12365b;background:#eaf2fc;
        padding:.35rem .7rem;border-radius:6px;margin-bottom:.8rem;}
      .home-intro {color:#566a7f;margin-bottom:1.4rem;max-width:620px;}
      .st-key-home_controls, .st-key-home_controls [data-testid="stVerticalBlock"] {gap:.55rem;}
      [data-testid="stVerticalBlockBorderWrapper"] {border-radius:10px;}
      [data-testid="stPageLink"] a {color:#2166b5;font-weight:600;}
      @media(max-width:640px) {.stMainBlockContainer {padding:1.4rem 1rem;}}
    </style>
    """)


def style_figure(figure, *, height=390, y_title=None):
    """Keep charts readable and preserve each measurement's own units."""
    figure.update_layout(
        template="plotly_white", colorway=PALETTE, height=height,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Source Sans Pro, sans-serif", color="#20344b", size=13),
        margin=dict(l=30, r=20, t=35, b=35), hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=0),
    )
    figure.update_xaxes(showgrid=False, title=None)
    figure.update_yaxes(gridcolor="#e1e9f2", zerolinecolor="#c4d4e5")
    if y_title:
        figure.update_yaxes(title=y_title)
    return figure
