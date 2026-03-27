# input_handler.py
import streamlit as st
import pandas as pd
import numpy as np

def render_all_sidebar_inputs():
    """
    Renders sidebar inputs for RC Beam Analysis.
    Features: Standardized units (m, mm, kN), DL/LL Case, Partial UDL, and Error Handling.
    Added: Auto-conversion from Thai engineer units (ksc, kg) to SI units (MPa, kN)
    """
    st.sidebar.markdown("### 1. Material & Section")
    
    # --- 1. Parameters (Material & Section) ---
    col1, col2 = st.sidebar.columns(2)
    with col1:
        # 🛠️ FIX 1: ปรับ UI ให้รับค่า fc เป็น ksc และเปลี่ยนค่า Default ให้สมจริง
        fc_ksc = st.number_input("f'c (ksc)", 100.0, 800.0, 240.0, step=10.0)
        b = st.number_input("Width b (mm)", 100.0, 1000.0, 200.0, step=50.0)
    with col2:
        # 🛠️ FIX 2: ปรับ UI ให้รับค่า fy เป็น ksc
        fy_ksc = st.number_input("fy (ksc)", 2000.0, 6000.0, 4000.0, step=100.0)
        h = st.number_input("Depth h (mm)", 200.0, 2000.0, 400.0, step=50.0)
        
    # 💥 THE MAGIC: แปลงหน่วยกลับเป็น SI (MPa) ก่อนส่งไปคำนวณ (1 ksc ≈ 0.0980665 MPa)
    fc_mpa = fc_ksc * 0.0980665
    fy_mpa = fy_ksc * 0.0980665
        
    # คำนวณ E_c โดยใช้ fc ในหน่วย MPa 
    # ผลลัพธ์เดิมคือ MPa (N/mm^2) นำไปคูณ 1000 เพื่อแปลงเป็น kN/m^2 (kPa) สำหรับ Solver
    E_c = 4700 * np.sqrt(fc_mpa) * 1000  
    
    # คำนวณ I_g โดยแปลง b, h เป็นเมตรก่อน เพื่อให้ได้หน่วย m^4
    b_m = b / 1000.0
    h_m = h / 1000.0
    I_g = (b_m * h_m**3) / 12.0
    
    # ส่ง b, h (mm) ไปวาดรูป และส่ง fc, fy (MPa), E (kPa), I (m^4) ไปคำนวณ
    params = {'fc': fc_mpa, 'fy': fy_mpa, 'b': b, 'h': h, 'E': E_c, 'I': I_g}

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
    
    if 'load_list' not in st.session_state:
        st.session_state.load_list = []

    with st.sidebar.expander("➕ Add New Load", expanded=True):
        l_case = st.radio("Load Case", ["DL (Dead)", "LL (Live)"], horizontal=True)
        l_type = st.selectbox("Load Type", ["Point Load (P)", "Uniform Load (U)"])
        
        span_opts = [f"Span {i+1}" for i in range(n_spans)]
        l_span_idx = span_opts.index(st.selectbox("Select Span", span_opts))
        max_l = spans[l_span_idx]
        
        # 🛠️ FIX 3: ปรับ UI รับโหลดเป็น kg หรือ kg/m
        l_mag_kg = st.number_input("Magnitude (kg or kg/m)", 0.0, 100000.0, 1000.0, step=100.0)
        
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
                "mag_kg": l_mag_kg,                                # เก็บค่า kg ไว้โชว์ในตาราง UI
                "mag": l_mag_kg * 0.00980665,                      # 💥 THE MAGIC: แปลง kg เป็น kN สำหรับ Solver ทันที
                "d_start": d_start,
                "d_end": d_end,
                "dist": d_end - d_start 
            })

    # --- 5. Data Visualization & Cleanup ---
    loads_df = pd.DataFrame(st.session_state.load_list)
    
    # เช็คคอลัมน์ใหม่ (รวมถึง mag_kg และ mag) เพื่อกัน Error จาก Session State เดิมค้าง
    required_cols_check = ['case', 'type', 'span_index', 'mag_kg', 'mag', 'd_start', 'd_end']
    display_cols = ['case', 'type', 'span_index', 'mag_kg', 'd_start', 'd_end'] # ให้ UI โชว์แค่ mag_kg
    
    if not loads_df.empty:
        if all(col in loads_df.columns for col in required_cols_check):
            st.sidebar.markdown("#### Active Load List")
            # โชว์เฉพาะคอลัมน์ที่ตั้งใจให้เห็น (ซ่อน mag ที่เป็น kN ไว้)
            st.sidebar.dataframe(loads_df[display_cols], hide_index=True)
        else:
            # ล้างข้อมูลเก่าทิ้งทันทีถ้า Data Structure ไม่ตรง (เช่น ตอนเพิ่งรันโค้ดใหม่)
            st.sidebar.warning("Updating Data Structure. Clearing table...")
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
    
    return params, n_spans, spans, sup_df, loads_df, stable
