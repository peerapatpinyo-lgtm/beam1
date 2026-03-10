# app_styles.py
import streamlit as st

def apply_custom_css():
    """
    Applies custom CSS styling to the Streamlit app for a professional engineering UI.
    """
    st.markdown("""
    <style>
        .main-header {font-size: 2.5rem; font-weight: bold; color: #1E3A8A; margin-bottom: 0px;}
        .sub-header {font-size: 1.2rem; font-weight: normal; color: #64748B; margin-top: -10px;}
        .stApp {background-color: #F8FAFC;}
        div[data-testid="stMetricValue"] {font-size: 1.5rem; color: #0F172A;}
        .report-box {
            background-color: #ffffff; 
            padding: 20px; 
            border-radius: 10px; 
            border: 1px solid #e2e8f0; 
            font-family: 'Courier New', monospace;
        }
        .pass-tag {
            color: #166534; 
            font-weight: bold; 
            background-color: #DCFCE7; 
            padding: 2px 8px; 
            border-radius: 4px;
        }
        .fail-tag {
            color: #991B1B; 
            font-weight: bold; 
            background-color: #FEE2E2; 
            padding: 2px 8px; 
            border-radius: 4px;
        }
    </style>
    """, unsafe_allow_html=True)
