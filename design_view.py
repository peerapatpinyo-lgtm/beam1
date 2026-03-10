import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
import streamlit as st
from section_plotter import plot_longitudinal_section_detailed, plot_cross_section
from reporter import render_calculation_report

# ==========================================
# 1. BOQ CALCULATION
# ==========================================
def calculate_boq_summary(design_res, spans):
    total_concrete_vol = 0.0
    total_formwork_area = 0.0
    total_steel_weight = 0.0
    
    for i, res in enumerate(design_res):
        L = spans[i]
        b_mm = res.get('b') or 300
        h_mm = res.get('h') or 500

        b_m = b_mm / 1000.0
        h_m = h_mm / 1000.0
        
        # 1. Concrete (m3)
        vol = b_m * h_m * L
        total_concrete_vol += vol
        
        # 2. Formwork (m2)
        form_area = (2 * h_m + b_m) * L
        total_formwork_area += form_area
        
        # 3. Steel Weight (kg)
        w_main = 0.0
        def get_steel_weight(n, db, length):
            if n > 0:
                unit_w = (db**2 / 162)
                return n * unit_w * length
            return 0

        # Top
        if 'top' in res and isinstance(res['top'], dict) and 'all_layers' in res['top']:
             for layer in res['top']['all_layers']:
                 w_main += get_steel_weight(layer['n'], layer['db'], L * 1.1)
        else:
            n = res.get('top_n', 0)
            db = res.get('top_db', 12)
            w_main += get_steel_weight(n, db, L * 1.1)

        # Bottom
        if 'bot' in res and isinstance(res['bot'], dict) and 'all_layers' in res['bot']:
             for layer in res['bot']['all_layers']:
                 w_main += get_steel_weight(layer['n'], layer['db'], L * 1.1)
        else:
            n = res.get('bot_n', 0)
            db = res.get('bot_db', 12)
            w_main += get_steel_weight(n, db, L * 1.1)

        # Stirrups
        stir_db = res.get('shear', {}).get('db', res.get('stir_db', 6))
        stir_s_mm = res.get('shear', {}).get('s', res.get('stir_spacing', 200))
        stir_s = stir_s_mm / 1000.0
        
        if stir_s > 0:
            n_stir = int(L / stir_s) + 1
            len_stir = 2 * (b_m + h_m) 
            w_stir_unit = (stir_db**2 / 162)
            w_stir_total = n_stir * len_stir * w_stir_unit
        else:
            w_stir_total = 0
            
        span_steel = w_main + w_stir_total
        total_steel_weight += span_steel

    data = [
        {"Item": "Concrete Structure (240 ksc)", "Unit": "m3", "Quantity": float(f"{total_concrete_vol:.2f}")},
        {"Item": "Formwork (Beam sides & bottom)", "Unit": "m2", "Quantity": float(f"{total_formwork_area:.2f}")},
        {"Item": "Deformed Bars (DB) + Stirrups (RB)", "Unit": "kg", "Quantity": float(f"{total_steel_weight:.2f}")}
    ]
    return pd.DataFrame(data)

# ==========================================
# 2. PLOTLY ANALYSIS GRAPH (Fixed Scale)
# ==========================================
def plot_analysis_results(res_df, spans, supports, loads, reactions):
    """
    Standard clean plotting style with dynamic scaling for visual elements.
    """
    fig = make_subplots(
        rows=4, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.08,
        subplot_titles=(
            "<b>1. Free Body Diagram (FBD)</b>", 
            "<b>2. Shear Force Diagram (SFD)</b>", 
            "<b>3. Bending Moment Diagram (BMD)</b>",
            "<b>4. Deflection Diagram</b>"
        ),
        row_heights=[0.25, 0.25, 0.25, 0.25]
    )

    # ROW 1: LOAD MODEL (FBD)
    total_L = sum(spans)
    cum_dist = [0] + list(np.cumsum(spans))
    
    # Beam Line
    fig.add_trace(go.Scatter(
        x=[0, total_L], y=[0, 0], 
        mode='lines', line=dict(color='black', width=4), hoverinfo='skip'
    ), row=1, col=1)
    
    # Supports
    for idx, row in supports.iterrows():
        sym = "triangle-up"
        if row['type'] == 'Fixed': sym = "square"
        elif row['type'] == 'Roller': sym = "circle"
        
        fig.add_trace(go.Scatter(
            x=[row['x']], y=[-0.05], 
            mode='markers+text',
            marker=dict(symbol=sym, size=14, color='white', line=dict(width=2, color='black')),
            text=[row['type'][0]], textposition="bottom center",
            hoverinfo='name', name=f"Support"
        ), row=1, col=1)

    # Loads Processing
    if isinstance(loads, pd.DataFrame):
        load_iter = loads.to_dict('records')
    elif isinstance(loads, list):
        load_iter = loads
    else:
        load_iter = []

    # --- 1. Find Max Load for Scaling ---
    max_mag = 1.0
    for l in load_iter:
        m = abs(l['mag'])
        if m > max_mag: max_mag = m
    
    # --- 2. Draw Loads ---
    for l in load_iter:
        span_idx = int(l['span_index'])
        start_x_span = cum_dist[span_idx]
        mag_raw = l['mag']
        mag_kN = mag_raw / 1000.0  # N -> kN
        
        # Calculate visual height ratio (0.15 to 0.6)
        ratio = abs(mag_raw) / max_mag
        h_vis = 0.15 + (ratio * 0.45) 

        case_type = l.get('case', 'DL')
        if case_type == 'LL':
            color = '#c0392b' # Red
        else:
            color = '#2980b9' # Blue (DL, SW)

        # --- POINT LOAD ---
        if l['type'] == 'P':
            x_loc = start_x_span + float(l['d_start']) 
            # Arrow scale logic
            arrow_len = 40 * (0.5 + 0.5*ratio) # Pixel length
            
            fig.add_annotation(
                x=x_loc, y=0, 
                ax=0, ay=-arrow_len,
                xref="x1", yref="y1",
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2, arrowcolor=color,
                text=f"<b>{mag_kN:.2f} kN</b>", yshift=5, row=1, col=1
            )
            
        # --- UNIFORM LOAD ---
        elif l['type'] == 'U':
            x_s = start_x_span + float(l.get('d_start', 0))
            dist_val = float(l['dist'])
            x_e = x_s + dist_val
            
            # 1. Shaded Area
            fig.add_trace(go.Scatter(
                x=[x_s, x_e, x_e, x_s],
                y=[0, 0, h_vis, h_vis],
                fill='toself', fillcolor=color, opacity=0.2,
                line=dict(width=0), hoverinfo='skip', showlegend=False
            ), row=1, col=1)
            
            # 2. Top Line
            fig.add_trace(go.Scatter(
                x=[x_s, x_e], y=[h_vis, h_vis],
                mode='lines', line=dict(color=color, width=2), hoverinfo='skip'
            ), row=1, col=1)
            
            # 3. Arrows
            n_arrows = max(2, int(dist_val * 1.5)) 
            arrow_x_points = np.linspace(x_s, x_e, n_arrows + 2)[1:-1]
            for ax_x in arrow_x_points:
                fig.add_annotation(
                    x=ax_x, y=0, ax=0, ay=-30*ratio, # Scale arrow slightly
                    xref="x1", yref="y1",
                    showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor=color,
                    row=1, col=1
                )
            
            # 4. Label
            label_text = f"<b>w={mag_kN:.2f} kN/m</b>"
            if case_type == 'SW':
                label_text = f"<b>SW={mag_kN:.2f} kN/m</b>"
                
            fig.add_annotation(
                x=(x_s+x_e)/2, y=h_vis,
                text=label_text,
                showarrow=False, yshift=10, font=dict(color=color), row=1, col=1
            )

    # ROW 2: SHEAR FORCE
    fig.add_hline(y=0, line_color="black", line_width=1, row=2, col=1)
    fig.add_trace(go.Scatter(
        x=res_df['x'], y=res_df['shear']/1000, 
        mode='lines', name='Shear (kN)', line=dict(color='#e74c3c', width=2),
        fill='tozeroy', fillcolor='rgba(231, 76, 60, 0.1)'
    ), row=2, col=1)
    
    v_max = res_df['shear'].max() / 1000
    v_min = res_df['shear'].min() / 1000
    for val in [v_max, v_min]:
        if abs(val) > 0.01:
            idx = (res_df['shear']/1000 - val).abs().idxmin()
            fig.add_annotation(
                x=res_df['x'].iloc[idx], y=val,
                text=f"<b>{val:.2f}</b>", showarrow=False, yshift=10 if val>0 else -10,
                font=dict(color='#e74c3c', size=11), row=2, col=1
            )

    # ROW 3: BENDING MOMENT
    fig.add_hline(y=0, line_color="black", line_width=1, row=3, col=1)
    fig.add_trace(go.Scatter(
        x=res_df['x'], y=res_df['moment']/1000, 
        mode='lines', name='Moment (kN-m)', line=dict(color='#27ae60', width=2),
        fill='tozeroy', fillcolor='rgba(39, 174, 96, 0.1)'
    ), row=3, col=1)

    m_max = res_df['moment'].max() / 1000
    m_min = res_df['moment'].min() / 1000
    for val in [m_max, m_min]:
        if abs(val) > 0.01:
            idx = (res_df['moment']/1000 - val).abs().idxmin()
            fig.add_annotation(
                x=res_df['x'].iloc[idx], y=val,
                text=f"<b>{val:.2f}</b>", 
                showarrow=True, arrowhead=1, ay=25 if val>0 else -25,
                font=dict(color='#27ae60', size=11), row=3, col=1
            )

    # ROW 4: DEFLECTION
    fig.add_hline(y=0, line_color="black", line_width=1, row=4, col=1)
    fig.add_trace(go.Scatter(
        x=res_df['x'], y=res_df['deflection'], 
        mode='lines', name='Deflection (mm)', line=dict(color='#8e44ad', width=2)
    ), row=4, col=1)
    
    idx_max_def = res_df['deflection'].abs().idxmax()
    max_def_val = res_df['deflection'].iloc[idx_max_def]
    fig.add_annotation(
        x=res_df['x'].iloc[idx_max_def], y=max_def_val,
        text=f"<b>Max: {max_def_val:.3f} mm</b>",
        showarrow=True, arrowhead=1, 
        ay=30 if max_def_val < 0 else -30,
        font=dict(color='#8e44ad', size=11), row=4, col=1
    )

    # Grid & Layout
    for x_pos in cum_dist:
        fig.add_vline(x=x_pos, line_width=1, line_dash="dash", line_color="gray", opacity=0.3)

    fig.update_layout(
        title="<b>Structural Analysis Results</b>",
        height=1000, showlegend=False, template="plotly_white", hovermode="x unified",
        margin=dict(t=60, b=40, l=60, r=20)
    )
    
    # --- FIX GRAPH DISTORTION ---
    # Lock range for load diagram so it always has headspace
    fig.update_yaxes(range=[-0.25, 1.0], showgrid=False, visible=False, row=1, col=1) 
    
    fig.update_yaxes(title_text="Shear (kN)", showgrid=True, row=2, col=1)
    fig.update_yaxes(title_text="Moment (kN-m)", autorange="reversed", showgrid=True, row=3, col=1)
    fig.update_yaxes(title_text="Deflection (mm)", showgrid=True, zeroline=True, row=4, col=1)
    fig.update_xaxes(title_text="Length (m)", row=4, col=1)

    return fig

# ==========================================
# 3. DESIGN CHECK DISPLAY
# ==========================================
def display_design_comparison(mu_pos, mu_neg, vu, design_res):
    st.markdown("---")
    st.subheader("🛠 RC Design Verification")
    
    fc = design_res.get('fc', 24)
    fy = design_res.get('fy', 400)
    b = design_res.get('b', 200)
    h = design_res.get('h', 400)
    d = h - 50
    as_min = max((0.25 * np.sqrt(fc) / fy) * b * d, (1.4 / fy) * b * d)

    st.markdown("#### 📏 Reinforcement Area ($A_s$)")
    as_col1, as_col2 = st.columns(2)
    
    with as_col1:
        as_req_calc = design_res.get('as_req_bot', 0.0)
        as_req_final = max(as_req_calc, as_min)
        as_prov = design_res.get('as_prov_bot', 0.0)
        st.write("**Bottom Steel (Mid-span)**")
        st.write(f"Required: `{as_req_final:.0f}` $mm^2$ | Provided: `{as_prov:.0f}` $mm^2$")
        if as_req_final > 0:
            ratio = min(as_prov / as_req_final, 1.0)
            st.progress(ratio)
            if as_prov >= as_req_final:
                st.success(f"✅ Pass ({(as_prov/as_req_final*100):.0f}%)")
            else:
                st.error(f"❌ Fail ({(as_prov/as_req_final*100):.0f}%)")

    with as_col2:
        as_req_calc_t = design_res.get('as_req_top', 0.0)
        as_req_final_t = max(as_req_calc_t, as_min)
        as_prov_t = design_res.get('as_prov_top', 0.0)
        st.write("**Top Steel (Support)**")
        st.write(f"Required: `{as_req_final_t:.0f}` $mm^2$ | Provided: `{as_prov_t:.0f}` $mm^2$")
        if as_req_final_t > 0:
            ratio_t = min(as_prov_t / as_req_final_t, 1.0)
            st.progress(ratio_t)
            if as_prov_t >= as_req_final_t:
                st.success(f"✅ Pass ({(as_prov_t/as_req_final_t*100):.0f}%)")
            else:
                st.error(f"❌ Fail ({(as_prov_t/as_req_final_t*100):.0f}%)")

    st.markdown("---")
    st.markdown("#### ⚡ Section Capacity ($\phi M_n, \phi V_n$)")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Positive Moment**")
        phi_mn_pos = design_res.get('phi_Mn_pos', 0.0)
        st.metric("Demand", f"{mu_pos:.2f} kNm")
        st.metric("Capacity", f"{phi_mn_pos:.2f} kNm", 
                  delta=f"{(phi_mn_pos - mu_pos):.2f}", delta_color="normal")
        st.write("✅ Safe") if phi_mn_pos >= mu_pos else st.write("❌ Unsafe")
    with col2:
        st.markdown("**Negative Moment**")
        phi_mn_neg = design_res.get('phi_Mn_neg', 0.0)
        mu_neg_abs = abs(mu_neg)
        st.metric("Demand", f"{mu_neg_abs:.2f} kNm")
        st.metric("Capacity", f"{phi_mn_neg:.2f} kNm",
                  delta=f"{(phi_mn_neg - mu_neg_abs):.2f}", delta_color="normal")
        st.write("✅ Safe") if phi_mn_neg >= mu_neg_abs else st.write("❌ Unsafe")
    with col3:
        st.markdown("**Shear Force**")
        phi_vn = design_res.get('phi_Vn', 0.0)
        st.metric("Demand", f"{vu:.2f} kN")
        st.metric("Capacity", f"{phi_vn:.2f} kN",
                  delta=f"{(phi_vn - vu):.2f}", delta_color="normal")
        st.write("✅ Safe") if phi_vn >= vu else st.write("❌ Unsafe")
            
    top_n = design_res.get('top_n', 0)
    top_db = design_res.get('top_db', 0)
    bot_n = design_res.get('bot_n', 0)
    bot_db = design_res.get('bot_db', 0)
    stir_db = design_res.get('stir_db', 0)
    stir_sp = design_res.get('stir_spacing', 0)

    st.info(f"📝 **Detail:** Top {top_n}DB{top_db} | Bot {bot_n}DB{bot_db} | Stirrup RB{stir_db}@{stir_sp}mm")

# ==========================================
# 4. MAIN RENDER CONTROLLER
# ==========================================
def render_design_view(res_package):
    if not res_package:
        st.error("No design results to display.")
        return

    # Unpack Data
    x = res_package['x']
    m = res_package['m']
    v = res_package['v']
    d = res_package['d']
    react = res_package['reactions']
    design_res = res_package['design_results']
    spans = res_package['spans']
    sup_df = res_package['supports']
    params = res_package['params']
    
    # 1. เตรียม Load Data
    raw_loads = res_package.get('loads', [])
    if isinstance(raw_loads, pd.DataFrame):
        display_loads = raw_loads.to_dict('records')
    else:
        display_loads = list(raw_loads) if raw_loads else []

    # 2. จัดการ Self-weight
    include_sw = params.get('include_sw', True)

    if include_sw: 
        for i, res in enumerate(design_res):
            val_b = res.get('b') or params.get('b') or 300
            val_h = res.get('h') or params.get('h') or 500

            b_m = float(val_b) / 1000.0
            h_m = float(val_h) / 1000.0
            L = spans[i]
            
            sw_mag = 24000 * b_m * h_m 
            
            sw_load = {
                'type': 'U',
                'mag': sw_mag,
                'span_index': i,
                'd_start': 0,
                'dist': L,
                'case': 'SW'
            }
            display_loads.append(sw_load)

    st.markdown("## 🏗️ Design Dashboard")
    
    # ======================================================
    #  TABLE DISPLAY (FIX: วางตรงนี้ ขึ้นแน่นอน 100%)
    # ======================================================
    st.markdown("### 📋 Load Combinations")
    dl_factor = params.get('dl_factor', 1.4)
    ll_factor = params.get('ll_factor', 1.7)
    
    combo_data = [
        {"Load Type": "Dead Load (DL)", "Factor": f"{dl_factor:.2f}", "Description": "Superimposed Dead Load"},
        {"Load Type": "Live Load (LL)", "Factor": f"{ll_factor:.2f}", "Description": "Occupancy / Usage Load"},
    ]
    
    if include_sw:
        combo_data.insert(0, {
            "Load Type": "Self-Weight (SW)", 
            "Factor": f"{dl_factor:.2f}", 
            "Description": "Computed from Beam Section (2400 kg/m³)"
        })
    else:
        combo_data.append({
            "Load Type": "Self-Weight (SW)", 
            "Factor": "Excluded", 
            "Description": "-"
        })
        
    st.dataframe(pd.DataFrame(combo_data), use_container_width=True, hide_index=True)
    st.caption(f"*Ultimate Load Equation: U = {dl_factor}DL + {ll_factor}LL*")
    st.divider()
    # ======================================================

    t1, t2, t3 = st.tabs(["📊 Analysis Results", "📐 Section Details", "📝 Report"])
    
    # --- TAB 1: Analysis ---
    with t1:
        st.subheader("Analysis Diagrams")
        df_plot = pd.DataFrame({'x': x, 'moment': m, 'shear': v, 'deflection': d})
        
        fig = plot_analysis_results(df_plot, spans, sup_df, display_loads, react)
        
        st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("Reactions")
        r_data = [{"Support": k, "Reaction (kN)": f"{val/1000:.2f}"} for k, val in react.items()]
        st.dataframe(pd.DataFrame(r_data), use_container_width=True, hide_index=True)

    # --- TAB 2: Design Details ---
    with t2:
        st.subheader("Detailed Section Design")
        span_opts = [f"Span {i+1}" for i in range(len(spans))]
        selected_span_idx = st.selectbox("Select Span:", range(len(spans)), format_func=lambda x: span_opts[x])
        current_res = design_res[selected_span_idx]
        
        col1, col2 = st.columns([1, 2])
        with col1:
             st.markdown("#### Cross Section")
             svg_cross = plot_cross_section(current_res)
             st.image(svg_cross, use_container_width=True)
        with col2:
             display_design_comparison(current_res['Mu_pos'], current_res['Mu_neg'], current_res['Vu_max'], current_res)

        st.divider()
        st.subheader("Longitudinal Profile")
        svg_long, _ = plot_longitudinal_section_detailed(spans, sup_df, design_res, params.get('h', 500), params.get('cover', 25))
        st.image(svg_long, use_container_width=True)

    # --- TAB 3: Report & BOQ ---
    with t3:
        st.header("📝 Summary")
        st.subheader("1. Bill of Quantities")
        boq_df = calculate_boq_summary(design_res, spans)
        st.dataframe(boq_df.style.format({"Quantity": "{:.2f}"}), use_container_width=True, hide_index=True)
        csv = boq_df.to_csv(index=False).encode('utf-8')
        st.download_button(label="📥 Download CSV", data=csv, file_name='boq_estimate.csv', mime='text/csv')
        st.divider()
        st.subheader("2. Calculation Report")
        for i, res in enumerate(design_res):
            with st.expander(f"View Report: Span {i+1}", expanded=False):
                res['span_id'] = i
                res['L'] = spans[i]
                render_calculation_report(res)
