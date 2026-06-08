# app.py  ── Fixed & Production-Ready Version
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import streamlit.components.v1 as components

import input_handler
import solver
import design_view
import section_plotter
import reporter
import rc_utils
import rc_design_engine
import rc_load_processor
import app_styles

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Pro RC Beam Design", layout="wide", page_icon="🏗️")
try: app_styles.apply_custom_css()
except Exception: pass

# ── Helper: rebar weight (kg/m) ──────────────────────────────────────────────
def get_rebar_weight(d_mm):
    return (d_mm ** 2) / 162.0

# ── Helper: cross-section drawing ────────────────────────────────────────────
def plot_cross_section_fixed(b, h, cover, top_layers, bot_layers, shear_res):
    fig, ax = plt.subplots(figsize=(4, 5))
    ax.add_patch(patches.Rectangle((0, 0), b, h, lw=2, ec='black', fc='#f0f2f6'))
    ax.add_patch(patches.Rectangle((cover, cover), b-2*cover, h-2*cover,
                                    lw=1.5, ec='#34495e', fc='none', ls='--'))

    def draw_layer(layers, is_top):
        if not layers: return
        outer_dia = layers[0]['db']
        curr_y = h - cover - outer_dia/2 if is_top else cover + outer_dia/2
        for idx, layer in enumerate(layers):
            n, dia = layer.get('n', 0), layer.get('db', 16)
            if n == 0: continue
            color = '#c0392b' if is_top else '#27ae60'
            if idx > 0:
                prev_dia = layers[idx-1]['db']
                shift    = prev_dia/2 + 25.0 + dia/2
                curr_y   = curr_y - shift if is_top else curr_y + shift
            sx, ex = cover + dia/2, b - cover - dia/2
            xs = np.linspace(sx, ex, n) if n > 1 else [b/2]
            for x in xs:
                ax.add_patch(patches.Circle((x, curr_y), dia/2, color=color, zorder=10))

    draw_layer(top_layers, True)
    draw_layer(bot_layers, False)

    tx = b + b * 0.1
    t_lbl = " + ".join([f"{int(l['n'])}-DB{int(l['db'])}" for l in top_layers if l['n'] > 0])
    b_lbl = " + ".join([f"{int(l['n'])}-DB{int(l['db'])}" for l in bot_layers if l['n'] > 0])
    if t_lbl: ax.text(tx, h - cover, f"Top:\n{t_lbl}", color='#c0392b', fontsize=10, fontweight='bold', va='top')
    if b_lbl: ax.text(tx, cover, f"Bot:\n{b_lbl}", color='#27ae60', fontsize=10, fontweight='bold', va='bottom')
    ax.text(tx, h/2, f"RB{int(shear_res['db'])}@{int(shear_res['s'])}", color='#2c3e50', fontsize=9, va='center')

    ax.set_title(f"Section {int(b)}×{int(h)} mm", fontsize=12, fontweight='bold', pad=15)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_xlim(-50, b + max(250, b * 0.6))
    ax.set_ylim(-50, h + 50)
    plt.tight_layout()
    return fig

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="main-header">🏗️ RC Beam Analysis & Design Pro</div>', unsafe_allow_html=True)

# ── Sidebar Inputs ────────────────────────────────────────────────────────────
with st.sidebar:
    params, n_spans, spans, sup_df, raw_user_loads_df, stable = input_handler.render_all_sidebar_inputs()

# ── Main Logic ────────────────────────────────────────────────────────────────
if not stable:
    st.error("🚨 **Structure Unstable:** Please add sufficient supports (≥ 3 restraints).")
    st.stop()

# ── Analysis Settings ─────────────────────────────────────────────────────────
col_set1, col_set2 = st.columns([1, 2])
with col_set1:
    st.markdown("### ⚙️ Analysis Settings")
    mode_select = st.radio("Display Mode:", ["Ultimate Strength (Design)", "Service Load (Check Deflection)"])
    st.markdown("---")
    include_sw = st.checkbox("➕ Include Beam Self-weight", value=True)
    b_m, h_m   = params['b'] / 1000.0, params['h'] / 1000.0
    sw_val     = b_m * h_m * 24.0       # kN/m  (concrete unit weight 24 kN/m³)
    if include_sw: st.caption(f"ℹ️ SW = {sw_val:.3f} kN/m (b={params['b']:.0f}×h={params['h']:.0f} mm @ 24 kN/m³)")
    else:          st.caption("ℹ️ Self-weight excluded")

with col_set2:
    st.markdown("### 🔢 Load Factors")
    is_service = "Service" in mode_select
    tag        = "Service Limit State" if is_service else "Ultimate Limit State"
    c1, c2     = st.columns(2)
    f_dl = c1.number_input("Dead Load Factor (f_DL)", 1.0, 2.0,
                            value=1.0 if is_service else 1.4, step=0.1, disabled=is_service)
    f_ll = c2.number_input("Live Load Factor (f_LL)",  1.0, 2.0,
                            value=1.0 if is_service else 1.7, step=0.1, disabled=is_service)

try:
    # ── Prepare Loads ─────────────────────────────────────────────────────────
    clean_loads = raw_user_loads_df.copy(deep=True)
    if not clean_loads.empty:
        if 'type' in clean_loads.columns:
            clean_loads['type'] = clean_loads['type'].apply(
                lambda x: 'P' if str(x).upper().startswith('P') else 'U')
        if 'case' in clean_loads.columns:
            clean_loads['case'] = clean_loads['case'].apply(
                lambda x: 'LL' if ('L' in str(x).upper() and 'D' not in str(x).upper()) else 'DL')

    if include_sw:
        sw_rows = [{'span_index': i, 'type': 'U', 'mag': sw_val,
                    'dist': spans[i], 'd_start': 0, 'case': 'DL'}
                   for i in range(n_spans)]
        final_loads = pd.concat([clean_loads, pd.DataFrame(sw_rows)], ignore_index=True)
    else:
        final_loads = clean_loads

    # ── Run Solver ───────────────────────────────────────────────────────────
    calc_ult = rc_load_processor.prepare_load_dataframe(final_loads, n_spans, spans, params, f_dl, f_ll)
    x_ult, M_ult, V_ult, D_ult, R_ult = solver.solve_beam(spans, sup_df, calc_ult, params)

    calc_svc = rc_load_processor.prepare_load_dataframe(final_loads, n_spans, spans, params, 1.0, 1.0)
    x_svc, M_svc, V_svc, D_svc, R_svc = solver.solve_beam(spans, sup_df, calc_svc, params)

    if is_service:
        x_plot, M_plot, V_plot, D_plot, R_plot = x_svc, M_svc, V_svc, D_svc, R_svc
    else:
        x_plot, M_plot, V_plot, D_plot, R_plot = x_ult, M_ult, V_ult, D_ult, R_ult

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["📊 1. Analysis Results", "📝 2. Concrete Design", "📘 3. Report & BOQ"])
    final_design_res = []

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 1 — Analysis Results
    # ═════════════════════════════════════════════════════════════════════════
    with tab1:
        st.subheader(f"📈 Analysis Diagrams ({tag})")

        # Summary metrics
        v_max_val = np.max(np.abs(V_plot))
        m_max_val = np.max(np.abs(M_plot))
        d_max_val = np.max(np.abs(D_plot)) * 1000
        cm1, cm2, cm3 = st.columns(3)
        cm1.metric("Max |Shear|",     f"{v_max_val:.3f} kN")
        cm2.metric("Max |Moment|",    f"{m_max_val:.3f} kNm")
        cm3.metric("Max |Deflection|", f"{d_max_val:.3f} mm")

        # Debug expander (collapsed by default)
        with st.expander("🔍 Debug: Processed Load Table", expanded=False):
            st.write(f"**Self-weight:** {sw_val:.3f} kN/m | **Include SW:** {include_sw}")
            st.write("**Loads entering solver (kN):**")
            st.dataframe(calc_ult, hide_index=True)
            total_factored = sum(
                row['mag'] * row['dist'] if row['type'] == 'U' else row['mag']
                for _, row in calc_ult.iterrows()
            ) if not calc_ult.empty else 0
            st.caption(f"**Total Factored Load:** {total_factored:,.3f} kN")

        # Plot
        df_plot = pd.DataFrame({'x': x_plot, 'moment': M_plot, 'shear': V_plot,
                                 'deflection': D_plot * 1000})
        fig = design_view.plot_analysis_results(
            res_df=df_plot, spans=spans, supports=sup_df,
            loads=calc_ult if not is_service else calc_svc, reactions=R_plot
        )
        st.plotly_chart(fig, use_container_width=True)

        # Reactions table
        st.markdown("#### Support Reactions")
        r_data = [{"Support": k, "Vertical Reaction (kN)": f"{v:.3f}"} for k, v in R_plot.items()]
        st.dataframe(pd.DataFrame(r_data), hide_index=True)

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 2 — Concrete Design
    # ═════════════════════════════════════════════════════════════════════════
    with tab2:
        st.header("🏗️ Reinforcement Detailing")
        b_mm, h_mm = rc_utils.normalize_section_units(params['b'], params['h'])
        fc, fy     = params['fc'], params['fy']
        offsets    = [0] + list(np.cumsum(spans))

        for i in range(n_spans):
            s_len, s_start, s_end = spans[i], offsets[i], offsets[i + 1]

            mask_u = (x_ult >= s_start - 1e-6) & (x_ult <= s_end + 1e-6)
            if not mask_u.any(): continue

            mu_pos  = max(0.0, M_ult[mask_u].max())
            mu_neg  = abs(min(0.0, M_ult[mask_u].min()))
            vu_max  = abs(V_ult[mask_u]).max()

            mask_s  = (x_svc >= s_start - 1e-6) & (x_svc <= s_end + 1e-6)
            ma_pos_svc       = max(0.0, M_svc[mask_s].max()) if mask_s.any() else 0.0
            delta_elastic_mm = abs(D_svc[mask_s]).max() * 1000.0 if mask_s.any() else 0.0

            with st.expander(
                f"📍 SPAN {i+1} (L={s_len} m) | Mu+: {mu_pos:.1f} kNm | Mu−: {mu_neg:.1f} kNm",
                expanded=True
            ):
                col_input, col_draw = st.columns([2, 1])

                with col_input:
                    cover_mm = st.number_input("Cover (mm)", 20, 75, 25, key=f"cov_{i}")

                    # Top Steel
                    st.markdown("#### 🔽 Top Steel (Negative Moment)")
                    num_t_layers = st.selectbox("Top Layers", [1, 2], key=f"tl_{i}")
                    top_layers = []
                    for li in range(num_t_layers):
                        ct1, ct2 = st.columns(2)
                        t_db  = ct1.selectbox(f"L{li+1} Dia", [12, 16, 20, 25, 28], index=1, key=f"tdb_{i}_{li}")
                        t_qty = ct2.number_input(f"L{li+1} No.", 0, 20, 2 if li == 0 else 0, key=f"tn_{i}_{li}")
                        top_layers.append({'n': t_qty, 'db': t_db})
                    top_res_ph = st.empty()

                    # Bottom Steel
                    st.markdown("#### 🔼 Bottom Steel (Positive Moment)")
                    num_b_layers = st.selectbox("Bottom Layers", [1, 2], key=f"bl_{i}")
                    bot_layers = []
                    for li in range(num_b_layers):
                        cb1, cb2 = st.columns(2)
                        b_db  = cb1.selectbox(f"L{li+1} Dia", [12, 16, 20, 25, 28], index=1, key=f"bdb_{i}_{li}")
                        b_qty = cb2.number_input(f"L{li+1} No.", 0, 20, 3 if li == 0 else 0, key=f"bn_{i}_{li}")
                        bot_layers.append({'n': b_qty, 'db': b_db})
                    bot_res_ph = st.empty()

                    # Stirrups
                    st.markdown("#### 🌀 Shear Stirrups")
                    cs1, cs2  = st.columns(2)
                    stir_db   = cs1.selectbox("Stirrup Dia", [6, 9, 12], index=1, key=f"sdb_{i}")
                    stir_s    = cs2.number_input("Spacing (mm)", 50, 300, 150, key=f"ss_{i}")
                    shear_res_ph = st.empty()

                    # ── Design Checks ────────────────────────────────────────
                    _, as_prov_t, _ = rc_design_engine.get_centroid_and_d(top_layers, h_mm, cover_mm, stir_db)
                    phi_Mn_t, *_    = rc_design_engine.get_phi_Mn_details_multi(
                        bot_layers, top_layers, b_mm, h_mm, fc, fy, cover_mm, stir_db, is_top_tension=True)
                    top_res_ph.caption(
                        f"**Top Check:** As = {as_prov_t:.0f} mm² | φMn = {phi_Mn_t:.1f} kNm "
                        f"{'✅' if phi_Mn_t >= mu_neg else '❌ Need more steel'}"
                    )

                    d_b, as_prov_b, y_centroid_b = rc_design_engine.get_centroid_and_d(
                        bot_layers, h_mm, cover_mm, stir_db)
                    phi_Mn_b, *_  = rc_design_engine.get_phi_Mn_details_multi(
                        bot_layers, top_layers, b_mm, h_mm, fc, fy, cover_mm, stir_db)
                    bot_res_ph.caption(
                        f"**Bottom Check:** As = {as_prov_b:.0f} mm² | φMn = {phi_Mn_b:.1f} kNm "
                        f"{'✅' if phi_Mn_b >= mu_pos else '❌ Need more steel'}"
                    )

                    status_v, phi_Vn, *_ = rc_design_engine.check_shear_details(
                        vu_max, b_mm, d_b, fc, fy, stir_db, stir_s)
                    if phi_Vn < vu_max:
                        shear_res_ph.error(f"❌ Shear FAIL: φVn={phi_Vn:.1f} < Vu={vu_max:.1f} kN")
                    else:
                        shear_res_ph.success(f"✅ Shear OK: φVn={phi_Vn:.1f} ≥ Vu={vu_max:.1f} kN")

                    # Serviceability
                    st.markdown("---")
                    d_inst, d_long, Ie, Icr, lambda_d = rc_design_engine.check_serviceability(
                        ma_pos_svc, delta_elastic_mm, b_mm, h_mm, d_b, as_prov_b, as_prov_t, fc)
                    limit_240     = (s_len * 1000) / 240
                    n_bars_bot    = sum(l['n'] for l in bot_layers)
                    w_crack, fs_a = rc_design_engine.check_crack_width(
                        ma_pos_svc, b_mm, h_mm, d_b, as_prov_b, n_bars_bot, fc)
                    limit_crack   = 0.30

                    chk1, chk2 = st.columns(2)
                    chk1.metric("Long-term Deflection", f"{d_long:.2f} mm",
                                delta=f"Limit L/240 = {limit_240:.1f} mm",
                                delta_color="off")
                    if d_long > limit_240: chk1.warning("⚠️ Exceeds L/240")

                    chk2.metric("Crack Width", f"{w_crack:.3f} mm",
                                delta=f"Limit = {limit_crack} mm", delta_color="off")
                    if w_crack > limit_crack: chk2.warning("⚠️ Exceeds limit")

                # Right column: cross section
                with col_draw:
                    fig_cs = plot_cross_section_fixed(
                        b=b_mm, h=h_mm, cover=cover_mm,
                        top_layers=top_layers, bot_layers=bot_layers,
                        shear_res={'db': stir_db, 's': stir_s}
                    )
                    st.pyplot(fig_cs, use_container_width=True)
                    plt.close(fig_cs)

                # Collect for report
                a_val = (as_prov_b * fy) / (0.85 * fc * b_mm) if b_mm > 0 else 0
                c_val = a_val / rc_utils.get_beta1(fc)
                final_design_res.append({
                    'span_id': i, 'L': s_len, 'b': b_mm, 'h': h_mm, 'fc': fc, 'fy': fy,
                    'Mu_pos': mu_pos, 'Mu_neg': mu_neg, 'Vu_max': vu_max, 'cover': cover_mm,
                    'Ma_pos_svc': ma_pos_svc, 'delta_svc_mm': d_long,
                    'top_db': top_layers[0]['db'] if top_layers else 12,
                    'bot_db': bot_layers[0]['db'] if bot_layers else 12,
                    'stir_db': stir_db, 'stir_s': stir_s,
                    'pos':    {'n': sum(l['n'] for l in bot_layers), 'area': as_prov_b,
                               'layers': bot_layers, 'status': phi_Mn_b >= mu_pos},
                    'neg':    {'n': sum(l['n'] for l in top_layers), 'area': as_prov_t,
                               'layers': top_layers, 'status': phi_Mn_t >= mu_neg},
                    'shear':  {'s': stir_s, 'db': stir_db, 'status': status_v},
                    'service':{'delta_long': d_long, 'limit_240': limit_240, 'ok': d_long <= limit_240},
                    'crack':  {'w': w_crack, 'limit': limit_crack, 'status': '✅ Pass' if w_crack <= limit_crack else '⚠️ Warning'},
                    'top': {'n': top_layers[0]['n'] if top_layers else 0,
                            'db': top_layers[0]['db'] if top_layers else 12,
                            'layers': num_t_layers, 'all_layers': top_layers},
                    'bot': {'n': bot_layers[0]['n'] if bot_layers else 0,
                            'db': bot_layers[0]['db'] if bot_layers else 12,
                            'layers': num_b_layers, 'all_layers': bot_layers},
                    'd_b': d_b, 'a': a_val, 'c': c_val,
                })

        st.markdown("---")
        if st.button("🏗️ Generate Longitudinal Drawing"):
            if final_design_res:
                svg_long, _ = section_plotter.plot_longitudinal_section_detailed(
                    spans, sup_df, final_design_res, h_mm, cover_mm)
                components.html(
                    f'<div style="background:white;overflow-x:auto;border:1px solid #ddd;padding:10px;">{svg_long}</div>',
                    height=500
                )
            else:
                st.warning("Complete design in Tab 2 first.")

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 3 — Report & BOQ
    # ═════════════════════════════════════════════════════════════════════════
    with tab3:
        st.header("📝 Calculation Reports")
        if not final_design_res:
            st.warning("⚠️ Complete design in Tab 2 first.")
        else:
            for res in final_design_res:
                with st.expander(f"📘 Span {res['span_id']+1} Calculation Details",
                                 expanded=(res['span_id'] == 0)):
                    reporter.render_calculation_report(res)

        # BOQ
        st.markdown("---")
        st.header("💵 Bill of Quantities (BOQ)")
        pc1, pc2, pc3 = st.columns(3)
        price_conc  = pc1.number_input("Concrete (THB/m³)",  value=2400, step=50)
        price_steel = pc2.number_input("Rebar (THB/kg)",     value=28.0, step=0.5)
        price_form  = pc3.number_input("Formwork (THB/m²)",  value=350,  step=10)

        if final_design_res:
            total_vol, total_form, total_steel = 0.0, 0.0, 0.0
            for res in final_design_res:
                L_r = res['L']
                bm, hm = res['b']/1000.0, res['h']/1000.0
                total_vol  += bm * hm * L_r
                total_form += (2*hm + bm) * L_r
                w_top  = sum(get_rebar_weight(l['db']) * l['n'] for l in res['top']['all_layers'])
                w_bot  = sum(get_rebar_weight(l['db']) * l['n'] for l in res['bot']['all_layers'])
                total_steel += (w_top + w_bot) * L_r * 1.05
                n_stir = (L_r * 1000.0) / res['shear']['s'] + 1
                stir_L = 2 * (res['b'] + res['h']) / 1000.0
                total_steel += get_rebar_weight(res['shear']['db']) * stir_L * n_stir

            boq_data = [
                {"Item": "Concrete Structure (240 ksc)", "Qty": total_vol,  "Unit": "m³",  "Unit Price": price_conc},
                {"Item": "Deformed Bars + Stirrups",     "Qty": total_steel,"Unit": "kg",  "Unit Price": price_steel},
                {"Item": "Formwork",                      "Qty": total_form, "Unit": "m²",  "Unit Price": price_form},
            ]
            df_boq = pd.DataFrame(boq_data)
            df_boq["Amount (THB)"] = df_boq["Qty"] * df_boq["Unit Price"]
            total_cost = df_boq["Amount (THB)"].sum()

            bq1, bq2, bq3, bq4 = st.columns(4)
            bq1.metric("Concrete",  f"{total_vol:.2f} m³")
            bq2.metric("Steel",     f"{total_steel:.2f} kg")
            bq3.metric("Formwork",  f"{total_form:.2f} m²")
            bq4.metric("TOTAL COST", f"{total_cost:,.0f} ฿", border=True)

            st.dataframe(
                df_boq.style.format({"Qty": "{:.2f}", "Unit Price": "{:,.2f}", "Amount (THB)": "{:,.2f}"}),
                hide_index=True, use_container_width=True
            )

except Exception as e:
    st.error(f"❌ Unexpected error: {e}")
    st.exception(e)
