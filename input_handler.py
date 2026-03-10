import streamlit as st
import pandas as pd
import numpy as np

def render_all_sidebar_inputs():
    """
    Renders sidebar inputs for RC Beam Analysis.
    Features: DL/LL Case, Partial UDL (Start/End), and Error Handling for Session State.
    """
    st.sidebar.markdown("### 1. Material & Section")
    
    # --- 1. Parameters (Material & Section) ---
    col1, col2 = st.sidebar.columns(2)
    with col1:
        fc = st.number_input("f'c (MPa)", 15.0, 50.0, 24.0, step=1.0)
        b = st.number_input("Width b (m)", 0.1, 1.0, 0.20, step=0.05)
    with col2:
        fy = st.number_input("fy (MPa)", 240, 500, 400, step=10)
        h = st.number_input("Depth h (m)", 0.2, 2.0, 0.40, step=0.05)
        
    # E_c calculation in Pa (N/m^2)
    E_c = 4700 * np.sqrt(fc) * 1000  
    I_g = (b * h**3) / 12
    params = {'fc': fc, 'fy': fy, 'b': b, 'h': h, 'E': E_c, 'I': I_g}

    # --- 2. Geometry (Spans) ---
    st.sidebar.markdown("### 2. Geometry")
    n_spans = st.sidebar.number_input("Number of Spans", 1, 10, 1)
    spans = []
    
    st_cols = st.sidebar.columns(min(n_spans, 4))
    for i in range(n_spans):
        with st_cols[i % 4]:
            l_val = st.number_input(f"L{i+1} (m)", 1.0, 20.0, 4.0, key=f"span_{i}")
            spans.append(l_val)

    # --- 3. Supports ---
    st.sidebar.markdown("### 3. Supports")
    node_coords = [0] + list(np.cumsum(spans))
    n_nodes = len(node_coords)
    default_sups = ["Pin"] + ["Roller"] * (n_nodes - 1)
        
    sup_data = []
    for i in range(n_nodes):
        stype = st.sidebar.selectbox(
            f"Node {i} (@{node_coords[i]:.2f}m)", 
            ["None", "Pin", "Roller", "Fixed"], 
            index=["None", "Pin", "Roller", "Fixed"].index(default_sups[i]),
            key=f"sup_{i}"
        )
        if stype != "None":
            sup_data.append({"id": i, "x": node_coords[i], "type": stype})
    sup_df = pd.DataFrame(sup_data)

    # --- 4. Loads Management ---
    st.sidebar.markdown("### 4. Loads")
    
    # Initialize session state with defensive check
    if 'load_list' not in st.session_state:
        st.session_state.load_list = []

    with st.sidebar.expander("➕ Add New Load", expanded=True):
        l_case = st.radio("Load Case", ["DL (Dead)", "LL (Live)"], horizontal=True)
        l_type = st.selectbox("Load Type", ["Point Load (P)", "Uniform Load (U)"])
        
        span_opts = [f"Span {i+1}" for i in range(n_spans)]
        l_span_idx = span_opts.index(st.selectbox("Select Span", span_opts))
        max_l = spans[l_span_idx]
        
        l_mag = st.number_input("Magnitude (kN or kN/m)", 0.0, 5000.0, 10.0)
        
        d_start, d_end = 0.0, max_l
        if l_type == "Point Load (P)":
            d_start = st.slider("Position (m)", 0.0, max_l, max_l/2)
            d_end = d_start
        else:
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                d_start = st.number_input("Start Dist (m)", 0.0, max_l, 0.0)
            with col_d2:
                d_end = st.number_input("End Dist (m)", d_start, max_l, max_l)

        if st.button("Confirm & Add Load"):
            st.session_state.load_list.append({
                "id": len(st.session_state.load_list),
                "case": "DL" if "DL" in l_case else "LL",
                "type": "P" if "Point" in l_type else "U",
                "span_index": l_span_idx,
                "mag": l_mag,
                "d_start": d_start,
                "d_end": d_end,
                "dist": d_end - d_start 
            })

    # --- 5. Data Visualization & Cleanup ---
    loads_df = pd.DataFrame(st.session_state.load_list)
    
    # Defensive check for DataFrame columns (Fixes KeyError)
    required_cols = ['case', 'type', 'span_index', 'mag', 'd_start', 'd_end']
    
    if not loads_df.empty:
        # Check if all required columns exist (for backward compatibility)
        if all(col in loads_df.columns for col in required_cols):
            st.sidebar.markdown("#### Active Load List")
            st.sidebar.dataframe(loads_df[required_cols], hide_index=True)
        else:
            st.sidebar.warning("Old data format detected. Clearing table...")
            st.session_state.load_list = []
            st.rerun()
            
        if st.sidebar.button("🗑️ Clear All Loads"):
            st.session_state.load_list = []
            st.rerun()

    # --- 6. Global Stability Check ---
    fixed_dof = 0
    for s in sup_data:
        if s['type'] == 'Pin': fixed_dof += 2
        elif s['type'] == 'Roller': fixed_dof += 1
        elif s['type'] == 'Fixed': fixed_dof += 3
        
    stable = fixed_dof >= 3
    
    # Returns 6 values to app.py
    return params, n_spans, spans, sup_df, loads_df, stable
