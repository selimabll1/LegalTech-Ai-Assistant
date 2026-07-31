import streamlit as st

from modules.ugfs_desktop_ui_v21 import render_ugfs_desktop_app_v21


st.set_page_config(
    page_title="Système de Veille LegalTech",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_ugfs_desktop_app_v21()
