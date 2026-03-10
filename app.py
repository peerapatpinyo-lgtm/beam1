import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import streamlit.components.v1 as components

# --- 1. IMPORT CUSTOM MODULES ---
import input_handler
import solver
import design_view
import section_plotter
import reporter
import rc_utils
import rc_design_engine
import rc_load_processor
import app_styles

# --- 2. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Pro RC Beam Design",
    layout="wide",
    page_icon="🏗️"
)

# Apply Custom CSS if available
try:
    app_styles.apply_custom_css()
except Exception:
    pass

# --- HELPER FUNCTIONS ---
def get_rebar_weight(d_mm):
    """Calculate rebar weight in kg/m"""
    return (d_mm ** 2) / 162.0

def plot_cross_section_fixed(b, h, cover, top_layers, bot_layers, shear_res):
    """
    Generate a Matplotlib figure for the cross-section.
    """
    fig, ax = plt.subplots(figsize=(4, 5))
    
    # Concrete Section
    rect = patches.Rectangle((0, 0), b, h, linewidth=2, edgecolor='black', facecolor='#f0f2f6')
    ax.add_patch(rect)
    
    # Stirrup
    stirrup_rect = patches.Rectangle(
        (cover, cover), b - 2*cover, h - 2*cover, 
        linewidth=1.5, edgecolor='#34495e', facecolor='none', linestyle='--'
    )
    ax.add_patch(stirrup_rect)
    
    # Helper to draw bars
    def draw_layer(layers, is_top):
        if not layers: return
        n_bars = sum(l['n'] for l in layers)
        if n_bars == 0: return
        
        dia = layers[0]['db']
        y_pos = h - cover - dia/2 if is_top else cover + dia/2
        color = '#c0392b' if is_top else '#27ae60'
        
        start_x = cover + dia/2
        end_x = b - cover - dia/2
        
        if n_bars > 1:
            gap = (end_x - start_x) / (n_bars - 1)
            for i in range(n_bars):
                circle = patches.Circle((start_x + i*gap, y_pos), radius=dia/2, color=color, zorder=10)
                ax.add_patch(circle)
        else:
            # Single bar centered
            circle = patches.Circle((b/2, y_pos), radius=dia/2, color=color, zorder=10)
            ax.add_patch(circle)

    # Draw Rebars
    draw_layer(top_layers, is_top=True)
    draw_layer(bot_layers, is_top=False)

    # Annotations
    text_x = b + (b * 0.1)
    
    # Count total bars
    n_top = sum(l['n'] for l in top_layers)
    n_bot = sum(l['n'] for l in bot_layers)
    d_top = top_layers[0]['db'] if top_layers else 0
    d_bot = bot_layers[0]['db'] if bot_layers else 0

    ax.text(text_x, h - cover, f"Top: {n_top}-DB{int(d_top)}", color='#c0392b', fontsize=10, fontweight='bold', va='center')
    ax.text(text_x, cover + d_bot, f"Bot: {n_bot}-DB{int(d_bot)}", color='#27ae60', fontsize=10, fontweight='bold', va='center')
    ax.text(text_x, h/2, f"Stir: RB{int(shear_res['db'])}@{int(shear_res['s'])}", color='#2c3e50', fontsize=9, va='center')

    ax.set_title(f"Section {int(b)}x{int(h)} mm", fontsize=12, fontweight='bold', pad=15)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_xlim(-50, b + 250) 
    ax.set_ylim(-50, h + 50)
    plt.tight_layout()
    return fig

# --- 4. MAIN HEADER ---
st.markdown('<div class="main-header">🏗️ RC Beam Analysis & Design Pro</div>', unsafe_allow_html=True)

# --- 5. SIDEBAR INPUTS ---
with st.sidebar:
    # Get raw user inputs from input_handler module
    params, n_spans, spans, sup_df, raw_user_loads_df, stable = input_handler.render_all_sidebar_inputs()

    # ==========================================================
    # 🛠️ SMART UNIT FIXER (ระบบแก้หน่วยอัตโนมัติ)
    # ==========================================================
    # เช็คว่า user เผลอกรอกหน่วย "เมตร" (ค่าน้อยกว่า 10) หรือไม่
    # ถ้าใช่ -> แปลงเป็น mm ให้ทันที เพื่อให้โค้ดส่วนอื่นทำงานถูกต้อง
    
    raw_b = params.get('b', 300)
    raw_h = params.get('h', 500)
    msg_unit = ""

    if raw_b < 10: 
        params['b'] = raw_b * 1000.0
        msg_unit += f"Width: {raw_b}m ➔ {params['b']:.0f}mm "
    
    if raw_h < 10:
        params['h'] = raw_h * 1000.0
        msg_unit += f"Depth: {raw_h}m ➔ {params['h']:.0f}mm"
    
    if msg_unit:
        st.success(f"⚡ **Auto-Correct Units:**\n{msg_unit}")
    # ==========================================================

# --- MAIN LOGIC ---
if not stable:
    st.error("🚨 **Structure Error:** The structure is unstable. Please check supports.")
else:
    # --- ANALYSIS SETTINGS ---
    col_set1, col_set2 = st.columns([1, 2])
    with col_set1:
        st.markdown("### ⚙️ Analysis Settings")
        mode_select = st.radio("Display Mode:", ["Ultimate Strength (Design)", "Service Load (Check Deflection)"], index=0)
        
        st.markdown("---")
        # [CRITICAL CHECKBOX]
        include_sw = st.checkbox("➕ Include Beam Self-weight", value=True)
        
        # --- FIXED: Self-Weight Calculation (Unit: N/m) ---
        # ตอนนี้ params['b'] และ params['h'] เป็น mm แน่นอนแล้วจาก Smart Fix ด้านบน
        b_m = params['b'] / 1000.0
        h_m = params['h'] / 1000.0
        
        # คอนกรีต 24000 N/m3
        sw_val = b_m * h_m * 24000.0  
        
        if include_sw:
            st.caption(f"ℹ️ **Added:** {sw_val/1000:.2f} kN/m")
        else:
            st.caption("ℹ️ **Excluded:** 0.00 kN/m")
    
    with col_set2:
        st.markdown("### 🔢 Load Factors")
        c1, c2 = st.columns(2)
        
        # Determine Factors and Display Mode
        if "Service" in mode_select:
            f_dl, f_ll = 1.0, 1.0
            tag, is_service = "Service Limit State", True
            # Show disabled inputs for visual reference
            c1.disabled = True
            c2.disabled = True
        else:
            f_dl = c1.number_input("Dead Load Factor (DL)", 1.0, 2.0, 1.4, 0.1)
            f_ll = c2.number_input("Live Load Factor (LL)", 1.0, 2.0, 1.7, 0.1)
            tag, is_service = "Ultimate Limit State", False

    try:
        # ==========================================
        # ⚡ LOAD PREPARATION
        # ==========================================
        
        # 1. Use a local copy of user loads
        clean_user_loads = raw_user_loads_df.copy(deep=True)
        
        # 2. Add Self-Weight if selected
        if include_sw:
            sw_rows = []
            for i in range(n_spans):
                sw_rows.append({
                    'span_index': i, 
                    'type': 'U', 
                    'mag': sw_val,  # หน่วย N/m (หลักพัน)
                    'dist': spans[i], 
                    'd_start': 0, 
                    'case': 'SW'
                })
            df_sw_only = pd.DataFrame(sw_rows)
            final_calc_loads = pd.concat([clean_user_loads, df_sw_only], ignore_index=True)
            status_msg = "✅ **Self-Weight Included**"
        else:
            final_calc_loads = clean_user_loads
            status_msg = "❌ **Self-Weight Excluded (Pure User Loads)**"

        # --- RUN SOLVER ---
        # 1. Ultimate Run (Factored)
        calc_loads_ult = rc_load_processor.prepare_load_dataframe(final_calc_loads, n_spans, spans, params, f_dl, f_ll)
        x_ult, M_ult, V_ult, D_ult, R_ult = solver.solve_beam(spans, sup_df, calc_loads_ult, params)
        
        # 2. Service Run (Unfactored 1.0)
        calc_loads_svc = rc_load_processor.prepare_load_dataframe(final_calc_loads, n_spans, spans, params, 1.0, 1.0)
        x_svc, M_svc, V_svc, D_svc, R_svc = solver.solve_beam(spans, sup_df, calc_loads_svc, params)

        # Select data for plotting based on mode
        x_plot, M_plot, V_plot, D_plot, R_plot = (x_svc, M_svc, V_svc, D_svc, R_svc) if is_service else (x_ult, M_ult, V_ult, D_ult, R_ult)

        # --- TABS START ---
        tab1, tab2, tab3 = st.tabs(["📊 1. Analysis Results", "📝 2. Concrete Design", "📘 3. Report & BOQ"])
        final_design_res = []

        # ================= TAB 1: ANALYSIS RESULTS =================
        with tab1:
            st.subheader(f"📈 Analysis Diagrams ({tag})")
            
            # Info Bar
            cols_chk = st.columns([1, 4])
            with cols_chk[0]:
                st.info(status_msg)
            with cols_chk[1]:
                total_factored_N = calc_loads_ult['mag'].sum() if not calc_loads_ult.empty else 0
                st.caption(f"🔍 **Total Factored Load (Check):** {total_factored_N/1000:,.2f} kN")

            # Debugger
            with st.expander("🛠️ Debug: Check Loads"):
                st.write(f"**Calculated SW (N/m):** {sw_val:.2f} (from b={params['b']}mm, h={params['h']}mm)")
                st.write("**Processed Loads (Entering Solver - Unit N):**", calc_loads_ult)

            # Main Graph
            df_for_plot = pd.DataFrame({'x': x_plot, 'moment': M_plot, 'shear': V_plot, 'deflection': D_plot * 1000})
            unique_chart_key = f"chart_{include_sw}_{tag}_{np.random.randint(0,1000)}"
            
            fig = design_view.plot_analysis_results(
                res_df=df_for_plot, 
                spans=spans, 
                supports=sup_df, 
                loads=calc_loads_ult if not is_service else calc_loads_svc, 
                reactions=R_plot
            )
            st.plotly_chart(fig, use_container_width=True, key=unique_chart_key)
            
            # Key Metrics
            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("Max Shear (V_max)", f"{max(abs(V_plot))/1000:.2f} kN")
            c_m2.metric("Max Moment (M_max)", f"{max(M_plot)/1000:.2f} kNm")
            c_m3.metric("Max Deflection", f"{max(abs(D_plot))*1000:.2f} mm")
            
        # ================= TAB 2: CONCRETE DESIGN =================
        with tab2:
            st.header("🏗️ Reinforcement Detailing")
            
            # Constants for Design
            b_mm, h_mm = rc_utils.normalize_section_units(params['b'], params['h'])
            fc, fy = params['fc'], params['fy']
            offsets = [0] + list(np.cumsum(spans))
            
            # --- LOOP THROUGH SPANS ---
            for i in range(n_spans):
                s_len, s_start, s_end = spans[i], offsets[i], offsets[i+1]
                
                # Extract Forces for this span
                mask_u = (x_ult >= s_start - 1e-6) & (x_ult <= s_end + 1e-6)
                if not mask_u.any(): continue

                # Design Forces (Ultimate)
                mu_pos = max(0.0, (M_ult[mask_u]/1000.0).max())
                mu_neg = abs(min(0.0, (M_ult[mask_u]/1000.0).min()))
                vu_max = abs((V_ult[mask_u] / 1000.0)).max()

                # Service Forces
                mask_s = (x_svc >= s_start - 1e-6) & (x_svc <= s_end + 1e-6)
                ma_pos_svc = max(0.0, (M_svc[mask_s]/1000.0).max())
                delta_elastic_mm = abs(D_svc[mask_s]).max() * 1000.0

                with st.expander(f"📍 SPAN {i+1} (L={s_len} m) | Mu+ : {mu_pos:.1f} kNm, Mu- : {mu_neg:.1f} kNm", expanded=True):
                    col_input, col_draw = st.columns([2, 1])
                    
                    with col_input:
                        cover_mm = st.number_input(f"Cover (mm)", 20, 50, 25, key=f"cov_{i}")

                        # 1. Top Steel
                        st.markdown("#### 🔽 Top Reinforcement (Negative Moment)")
                        num_t_layers = st.selectbox("Top Layers", [1, 2], index=0, key=f"tl_qty_{i}")
                        top_layers = []
                        for l_idx in range(num_t_layers):
                            ct1, ct2 = st.columns(2)
                            with ct1: t_db = st.selectbox(f"L{l_idx+1} Dia", [12, 16, 20, 25, 28], index=1, key=f"tdb_{i}_{l_idx}")
                            with ct2: t_qty = st.number_input(f"L{l_idx+1} No.", 0, 20, 2 if l_idx==0 else 0, key=f"tn_{i}_{l_idx}")
                            top_layers.append({'n': t_qty, 'db': t_db})
                        
                        # Top Calcs
                        d_t_val, as_prov_t, y_centroid_t = rc_design_engine.get_centroid_and_d(top_layers, h_mm, cover_mm, 9)
                        d_t = h_mm - y_centroid_t if y_centroid_t > 0 else h_mm - (cover_mm + 9 + 16/2)
                        phi_Mn_t, _, _, _, _, _ = rc_design_engine.get_phi_Mn_details_multi(top_layers, d_t, b_mm, h_mm, fc, fy)
                        
                        st.caption(f"**Check Top:** Prov As: {as_prov_t:.0f} mm² | Cap: {phi_Mn_t:.1f} kNm {'✅' if phi_Mn_t >= mu_neg else '❌ (Need More)'}")

                        # 2. Bottom Steel
                        st.markdown("#### 🔼 Bottom Reinforcement (Positive Moment)")
                        num_b_layers = st.selectbox("Bottom Layers", [1, 2], index=0, key=f"bl_qty_{i}")
                        bot_layers = []
                        for l_idx in range(num_b_layers):
                            cb1, cb2 = st.columns(2)
                            with cb1: b_db = st.selectbox(f"L{l_idx+1} Dia", [12, 16, 20, 25, 28], index=1, key=f"bdb_{i}_{l_idx}")
                            with cb2: b_qty = st.number_input(f"L{l_idx+1} No.", 0, 20, 3 if l_idx==0 else 0, key=f"bn_{i}_{l_idx}")
                            bot_layers.append({'n': b_qty, 'db': b_db})
                        
                        # Bot Calcs
                        d_b, as_prov_b, _ = rc_design_engine.get_centroid_and_d(bot_layers, h_mm, cover_mm, 9)
                        if d_b <= 0: d_b = h_mm - (cover_mm + 9 + 16/2)
                        phi_Mn_b, _, _, _, _, _ = rc_design_engine.get_phi_Mn_details_multi(bot_layers, d_b, b_mm, h_mm, fc, fy)
                        
                        st.caption(f"**Check Bot:** Prov As: {as_prov_b:.0f} mm² | Cap: {phi_Mn_b:.1f} kNm {'✅' if phi_Mn_b >= mu_pos else '❌ (Need More)'}")

                        # 3. Shear
                        st.markdown("#### 🌀 Shear Stirrups")
                        cs1, cs2 = st.columns(2)
                        with cs1: stir_db = st.selectbox("Stirrup Dia", [6, 9, 12], index=1, key=f"sdb_final_{i}")
                        with cs2: stir_s = st.number_input("Spacing @ (mm)", 50, 300, 150, key=f"ss_{i}")
                        
                        status_v, phi_Vn, _, _, _, _ = rc_design_engine.check_shear_details(vu_max, b_mm, d_b, fc, fy, stir_db, stir_s)
                        if phi_Vn < vu_max: 
                            st.error(f"❌ Shear Fail: {phi_Vn:.1f} < {vu_max:.1f} kN")
                        else: 
                            st.success(f"✅ Shear OK: {phi_Vn:.1f} ≥ {vu_max:.1f} kN")

                        # 4. Serviceability Checks
                        st.markdown("---")
                        d_inst, d_long, Ie, Icr, lambda_d = rc_design_engine.check_serviceability(
                            ma_pos_svc, delta_elastic_mm, b_mm, h_mm, d_b, as_prov_b, as_prov_t, fc
                        )
                        limit_240 = (s_len * 1000) / 240
                        total_n_bars_bot = sum(l['n'] for l in bot_layers)
                        w_crack, fs_actual = rc_design_engine.check_crack_width(
                            Ma_svc=ma_pos_svc, b=b_mm, h=h_mm, d=d_b, As=as_prov_b, n_bars=total_n_bars_bot, fc=fc
                        )
                        limit_crack = 0.30
                        status_crack = "✅ Pass" if w_crack <= limit_crack else "⚠️ Warning"

                        col_chk1, col_chk2 = st.columns(2)
                        with col_chk1: st.metric("Deflection (L/240)", f"{d_long:.2f} mm", f"{'Pass' if d_long <= limit_240 else 'Fail'}")
                        with col_chk2: st.metric("Crack Width", f"{w_crack:.3f} mm", f"{'Pass' if w_crack <= limit_crack else 'Warning'}")

                    # Right Column: Instant Section Drawing
                    with col_draw:
                        fig_cs = plot_cross_section_fixed(
                            b=b_mm, h=h_mm, cover=cover_mm, 
                            top_layers=top_layers, bot_layers=bot_layers, 
                            shear_res={'db': stir_db, 's': stir_s}
                        )
                        st.pyplot(fig_cs)
                        plt.close(fig_cs) 

                    # Store Results for Report
                    final_design_res.append({
                        'span_id': i, 'L': s_len, 'b': b_mm, 'h': h_mm, 'fc': fc, 'fy': fy, 
                        'Mu_pos': mu_pos, 'Mu_neg': mu_neg, 'Vu_max': vu_max, 'cover': cover_mm,
                        'Ma_pos_svc': ma_pos_svc, 'delta_svc_mm': d_long, 
                        'top_db': top_layers[0]['db'] if top_layers else 12, 
                        'bot_db': bot_layers[0]['db'] if bot_layers else 12,
                        'stir_db': stir_db, 'stir_s': stir_s,
                        'pos': {'n': sum(l['n'] for l in bot_layers), 'area': as_prov_b, 'layers': bot_layers, 'status': (phi_Mn_b >= mu_pos)},
                        'neg': {'n': sum(l['n'] for l in top_layers), 'area': as_prov_t, 'layers': top_layers, 'status': (phi_Mn_t >= mu_neg)},
                        'shear': {'s': stir_s, 'db': stir_db, 'status': status_v},
                        'service': {'delta_long': d_long, 'limit_240': limit_240, 'ok': d_long <= limit_240},
                        'crack': {'w': w_crack, 'limit': limit_crack, 'status': status_crack},
                        'top': {'n': top_layers[0]['n'] if top_layers else 0, 'db': top_layers[0]['db'] if top_layers else 12, 'layers': num_t_layers, 'all_layers': top_layers},
                        'bot': {'n': bot_layers[0]['n'] if bot_layers else 0, 'db': bot_layers[0]['db'] if bot_layers else 12, 'layers': num_b_layers, 'all_layers': bot_layers}
                    })

            st.markdown("---")
            if st.button("🏗️ Generate Detailed Drawing"):
                if final_design_res:
                    svg_long, _ = section_plotter.plot_longitudinal_section_detailed(spans, sup_df, final_design_res, h_mm, cover_mm)
                    components.html(f'<div style="background:white; overflow-x:auto; border:1px solid #ddd; padding:10px;">{svg_long}</div>', height=500)
                else:
                    st.warning("Analysis incomplete. Please run analysis first.")

        # ================= TAB 3: REPORT & BOQ =================
        with tab3:
            st.header("📝 Calculation Reports")
            if not final_design_res:
                st.warning("⚠️ Please complete the design in Tab 2 first.")
            else:
                for res in final_design_res:
                    with st.expander(f"📘 Span {res['span_id']+1} Calculation Details", expanded=(res['span_id']==0)):
                        reporter.render_calculation_report(res)

            # ================= BOQ SECTION =================
            st.markdown("---")
            st.header("💵 Bill of Quantities (BOQ)")

            c_price1, c_price2, c_price3 = st.columns(3)
            price_conc = c_price1.number_input("Concrete (Baht/m³)", value=2400, step=50)
            price_steel = c_price2.number_input("Rebar (Baht/kg)", value=28.0, step=0.5)
            price_form = c_price3.number_input("Formwork (Baht/m²)", value=350, step=10)

            if final_design_res:
                total_conc_vol = 0.0
                total_form_area = 0.0
                total_steel_weight = 0.0

                for res in final_design_res:
                    L = res['L']
                    b_m = res['b'] / 1000.0
                    h_m = res['h'] / 1000.0
                    
                    # Concrete
                    vol = b_m * h_m * L
                    total_conc_vol += vol
                    
                    # Formwork (Sides + Bottom)
                    area = (2*h_m + b_m) * L
                    total_form_area += area
                    
                    # Main Steel
                    w_top = sum(get_rebar_weight(l['db']) * l['n'] for l in res['top']['all_layers'])
                    w_bot = sum(get_rebar_weight(l['db']) * l['n'] for l in res['bot']['all_layers'])
                    total_steel_weight += (w_top + w_bot) * L * 1.05 
                    
                    # Stirrups
                    stir_len_m = (2 * (res['b'] + res['h']) / 1000.0) 
                    num_stir = (L * 1000.0) / res['shear']['s'] + 1
                    w_stir = get_rebar_weight(res['shear']['db']) * stir_len_m * num_stir
                    total_steel_weight += w_stir

                boq_data = [
                    {"Item": "Concrete Structure (240 ksc)", "Quantity": total_conc_vol, "Unit": "m³", "Unit Price": price_conc},
                    {"Item": "Deformed Bars (DB) + Stirrups", "Quantity": total_steel_weight, "Unit": "kg", "Unit Price": price_steel},
                    {"Item": "Formwork", "Quantity": total_form_area, "Unit": "m²", "Unit Price": price_form},
                ]
                
                df_boq = pd.DataFrame(boq_data)
                df_boq["Amount (THB)"] = df_boq["Quantity"] * df_boq["Unit Price"]
                
                c_boq1, c_boq2, c_boq3, c_boq4 = st.columns(4)
                c_boq1.metric("Concrete", f"{total_conc_vol:.2f} m³")
                c_boq2.metric("Steel", f"{total_steel_weight:.2f} kg")
                c_boq3.metric("Formwork", f"{total_form_area:.2f} m²")
                c_boq4.metric("TOTAL COST", f"{df_boq['Amount (THB)'].sum():,.0f} ฿", border=True)
                
                st.dataframe(
                    df_boq.style.format({"Quantity": "{:.2f}", "Unit Price": "{:,.2f}", "Amount (THB)": "{:,.2f}"}), 
                    use_container_width=True, hide_index=True
                )

    except Exception as e:
        st.error(f"An unexpected error occurred during processing: {e}")
        st.exception(e)
