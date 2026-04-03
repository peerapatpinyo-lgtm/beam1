# reporter.py
import streamlit as st
import numpy as np
from rc_design_engine import get_phi_Mn_details_multi
import section_plotter

def render_calculation_report(res):
    """
    Ultra-Detailed ACI 318-19 Compliance Report.
    Full Equation Substitution, Multiple-Layer Reinforcement, and Strain Compatibility.
    """
    # --- Data Extraction ---
    idx = res.get('span_id', 0) + 1
    L_m = res.get('L', 0)
    b = res.get('b', 200) 
    h = res.get('h', 400) 
    cov = res.get('cover', 25)
    fc = res.get('fc', 24)
    fy = res.get('fy', 400)
    
    # Moment & Shear Demands
    Mu_pos = res.get('Mu_pos', 0)
    Mu_neg = res.get('Mu_neg', 0)
    Vu = res.get('Vu_max', 0)
    delta_svc = res.get('delta_svc_mm', 0) 
    
    # --- Fix: Robust Multiple Layer Data Extraction ---
    def extract_layers(res_dict, prefix):
        layers = res_dict.get(f'{prefix}_layers', [])
        if not layers and prefix in res_dict:
            if 'all_layers' in res_dict[prefix]:
                layers = res_dict[prefix]['all_layers']
            else:
                layers = [{'n': res_dict[prefix].get('n', 0), 'db': res_dict[prefix].get('db', 12)}]
        return layers

    bot_layers = extract_layers(res, 'bot')
    top_layers = extract_layers(res, 'top')
        
    shear = res.get('shear', {})
    stir_db = shear.get('db', res.get('stir_db', 9))
    stir_s = shear.get('s', res.get('stir_s', 150))

    # --- Constants & ACI Parameters ---
    Es = 200000.0 
    Ec = 4700 * np.sqrt(fc)
    
    # ACI 22.2.2.4.3: Beta1 calculation
    if fc <= 28:
        beta1 = 0.85
    elif fc >= 55:
        beta1 = 0.65
    else:
        beta1 = 0.85 - (0.05 * (fc - 28) / 7)

    st.markdown(rf"## 🏛️ Comprehensive ACI 318-19 Design Audit: Span {idx}")
    st.markdown(rf"**Structural Element:** Continuous RC Beam | **Span Length:** {L_m:.2f} m")
    st.divider()

    # =========================================================
    # 1. MATERIAL & SECTION PROPERTIES
    # =========================================================
    st.markdown("### 1. Materials & Geometry (Ref: ACI 19.2 & 20.2)")
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Concrete Strength Properties:**")
        st.latex(rf"f'_c = {fc} \text{{ MPa}}")
        st.latex(rf"E_c = 4700\sqrt{{f'_c}} = 4700\sqrt{{{fc}}} = {Ec:.0f} \text{{ MPa}}")
        st.latex(rf"\beta_1 = {beta1:.3f} \quad \text{{(ACI 22.2.2.4.3)}}")
    with c2:
        st.write("**Steel Reinforcement:**")
        st.latex(rf"f_y = {fy} \text{{ MPa}}, \quad E_s = 200,000 \text{{ MPa}}")
        st.latex(rf"\text{{Section (b }} \times \text{{ h): }} {b:.0f} \times {h:.0f} \text{{ mm}}")

    st.divider()

    # =========================================================
    # 1.1 MINIMUM BEAM DEPTH CHECK (ACI 318-19 Table 9.3.1.1)
    # =========================================================
    st.markdown("### 1.1 Minimum Beam Depth Check ($h_{min}$)")
    
    L_mm = L_m * 1000
    
    # ACI 318-19 Table 9.3.1.1: fy modification factor
    fy_modifier = 0.4 + (fy / 700)
    
    # ดึงข้อมูลประเภทของช่วงคาน (ถ้าไม่มีให้ตั้งค่าเริ่มต้นเป็นคานต่อเนื่องสองข้าง)
    span_type = res.get('span_condition', 'Continuous (Both Ends)')
    
    # คำนวณ h_min ตามสภาพจุดรองรับ
    if span_type == 'Simply Supported':
        denom = 16
    elif span_type == 'Continuous (One End)':
        denom = 18.5
    elif span_type == 'Continuous (Both Ends)':
        denom = 21
    elif span_type == 'Cantilever':
        denom = 8
    else:
        denom = 21 # Default fallback
        
    h_min_req = (L_mm / denom) * fy_modifier
    
    st.write(f"**Span Condition:** {span_type}")
    
    st.latex(rf"h_{{min}} = \frac{{L}}{{{denom}}} \left( 0.4 + \frac{{f_y}}{{700}} \right)")
    st.latex(rf"h_{{min}} = \frac{{{L_mm:.0f}}}{{{denom}}} \left( 0.4 + \frac{{{fy}}}{{700}} \right) = \mathbf{{{h_min_req:.1f}}} \text{{ mm}}")
    
    hc1, hc2, hc3 = st.columns(3)
    hc1.metric("Provided Depth ($h$)", f"{h:.0f} mm")
    hc2.metric("Minimum Required ($h_{min}$)", f"{h_min_req:.1f} mm")
    
    if h >= h_min_req:
        hc3.success("✅ STATUS: PASS (Deflection check not strictly required)")
    else:
        hc3.warning("⚠️ STATUS: FAIL (Calculate exact deflection per ACI 24.2)")

    st.divider()

    # =========================================================
    # HELPER FUNCTION FOR FLEXURAL AUDIT (UPGRADED TO STRAIN COMPATIBILITY)
    # =========================================================
    def render_flexural_audit(title, Mu, all_bot_layers, all_top_layers, is_top=False):
        st.markdown(f"#### {title}")
        
        if abs(Mu) == 0:
            st.info("No moment demand for this section.")
            return 0, 0
            
        # เลือกแสดงผลเหล็กรับแรงดึงเพื่อหา d_eff ประมาณการ (ใช้กับ As,req)
        tension_layers = all_top_layers if is_top else all_bot_layers
        valid_t_layers = [ly for ly in tension_layers if ly.get('n', 0) > 0 and ly.get('db', 0) > 0]
        
        total_As = 0.0
        sum_Ay = 0.0
        current_y = cov + stir_db
        vertical_spacing = 25.0
        dt_approx = 0.0 
        
        st.markdown(f"**1. Reinforcement Details (Tension Side)**")
        
        if valid_t_layers:
            for i, layer in enumerate(valid_t_layers):
                n = layer['n']
                db = layer['db']
                
                A_layer = n * (np.pi * (db/2)**2)
                y_center = current_y + (db/2)
                
                if i == 0:
                    dt_approx = h - y_center 
                
                st.write(f"- **Layer {i+1}:** {int(n)}-DB{int(db)} | $A_{{s{i+1}}} = {A_layer:.1f} \text{{ mm}}^2$ | $y_{{{i+1}}} = {y_center:.1f} \text{{ mm}}$")
                
                total_As += A_layer
                sum_Ay += (A_layer * y_center)
                current_y += db + vertical_spacing
                
            y_bar = sum_Ay / total_As if total_As > 0 else 0
            d_eff = h - y_bar
            
            if len(valid_t_layers) > 1:
                st.latex(rf"\bar{{y}} = \frac{{\sum A_i y_i}}{{\sum A_i}} = \frac{{{sum_Ay:.1f}}}{{{total_As:.1f}}} = {y_bar:.1f} \text{{ mm}}")
                st.latex(rf"d_{{eff}} = h - \bar{{y}} = \mathbf{{{d_eff:.1f}}}\text{{ mm}}")
            else:
                st.latex(rf"d_{{eff}} = h - c_{{clear}} - d_{{stirrup}} - \frac{{d_{{b}}}}{{2}} = \mathbf{{{d_eff:.1f}}}\text{{ mm}}")
        else:
            st.warning("No reinforcement provided.")
            d_eff, total_As, y_bar, dt_approx = 0, 0, 0, 0
            return 0, 0

        # --- Required Steel Calculation (Basic Approx) ---
        st.markdown("**2. Required Reinforcement ($A_{s,req}$)**")
        Mu_calc = abs(Mu) * 1e6
        phi_flex = 0.9
        
        Rn = Mu_calc / (phi_flex * b * d_eff**2) if d_eff > 0 else 0
        term_inside = 1 - (2 * Rn) / (0.85 * fc)
        rho_req = (0.85 * fc / fy) * (1 - np.sqrt(term_inside)) if term_inside >= 0 else 0
        
        rho_min = max((0.25 * np.sqrt(fc) / fy), (1.4 / fy))
        
        as_req_calc = rho_req * b * d_eff
        as_min_calc = rho_min * b * d_eff
        as_final_req = max(as_req_calc, as_min_calc)

        st.latex(rf"A_{{s,req}} = \rho_{{req}} b d_{{eff}} = {rho_req:.5f} \times {b:.0f} \times {d_eff:.1f} = {as_req_calc:.1f} \text{{ mm}}^2")
        st.latex(rf"A_{{s,min}} = \rho_{{min}} b d_{{eff}} = {rho_min:.5f} \times {b:.0f} \times {d_eff:.1f} = {as_min_calc:.1f} \text{{ mm}}^2")
        st.markdown(rf"**$\Rightarrow$ Design Required $A_s$:** $\max(A_{{s,req}}, A_{{s,min}}) = \mathbf{{{as_final_req:.1f}}} \text{{ mm}}^2$")
        
        if total_As >= as_final_req:
            st.success(rf"✅ Check: Provided $A_s$ ({total_As:.1f} mm²) $\ge$ Required $A_s$ ({as_final_req:.1f} mm²)")
        else:
            st.error(rf"❌ Check: Provided $A_s$ ({total_As:.1f} mm²) $<$ Required $A_s$ ({as_final_req:.1f} mm²)")

        # ==========================================
        # 🌟 NEW: STRAIN COMPATIBILITY ANALYSIS WITH PLOT
        # ==========================================
        st.markdown("**3. Strain Compatibility & Stress Block (Iterative Method)**")
        
        # เรียกใช้งาน Engine คำนวณแบบละเอียด
        phiMn_val, As_t_val, a_val, Mn_val, c_val, eps_t_val, layer_res = get_phi_Mn_details_multi(
            all_bot_layers, all_top_layers, b, h, fc, fy, cov, stir_db, is_top_tension=is_top
        )

        col_math, col_plot = st.columns([1.1, 1])
        
        with col_math:
            st.latex(rf"c = {c_val:.2f} \text{{ mm}} \quad \text{{(Neutral Axis Depth)}}")
            st.latex(rf"a = \beta_1 c = {beta1:.3f} \times {c_val:.2f} = {a_val:.2f} \text{{ mm}}")
            
            st.markdown("**Layer-by-Layer Stress/Strain Distribution ($C=T$ Balanced):**")
            for lay_res in layer_res:
                # ตกแต่ง UI ไอคอน
                if lay_res['type'] == 'Tension':
                    status = "🟢 Yielded" if lay_res['is_yielded'] else "🟡 Elastic"
                    st.write(f"- **Bar @ $d$ = {lay_res['d_i']:.1f} mm** ({lay_res['type']}): $\epsilon_s$ = {lay_res['eps_s']:.5f} | $f_s$ = {lay_res['fs']:.1f} MPa | {status}")
                else:
                    status = "🔴 Yielded (Comp)" if lay_res['is_yielded'] else "⚪ Elastic (Comp)"
                    st.write(f"- **Bar @ $d'$ = {lay_res['d_i']:.1f} mm** ({lay_res['type']}): $\epsilon_s$ = {lay_res['eps_s']:.5f} | $f_s$ = {lay_res['fs']:.1f} MPa | {status}")

        with col_plot:
            # วาดรูป Stress-Strain ตามสภาวะที่กำลังคำนวณอยู่
            if c_val > 0 and a_val > 0:
                try:
                    fig_stress = section_plotter.plot_stress_strain_diagram(
                        b=b, h=h, d=d_eff, c=c_val, a=a_val, fc=fc
                    )
                    st.pyplot(fig_stress, use_container_width=True)
                except Exception as e:
                    st.error(f"⚠️ Diagram rendering failed: {e}")

        # --- Ultimate Strength Limit State ---
        st.markdown("**4. Ultimate Flexural Capacity ($\phi M_n$)**")
        
        if eps_t_val >= 0.005:
            phi_f = 0.90
            state = "Tension-Controlled (Ductile)"
        elif eps_t_val <= 0.002:
            phi_f = 0.65
            state = "Compression-Controlled (Brittle)"
        else:
            phi_f = 0.65 + 0.25 * (eps_t_val - 0.002) / 0.003
            state = "Transition Zone"

        st.latex(rf"\epsilon_t = \mathbf{{{eps_t_val:.5f}}} \implies \phi = {phi_f:.3f} \text{{ ({state})}}")
        st.latex(rf"M_{{n,exact}} = \sum (F_i \times \text{{arm}}_i) + M_{{concrete}} = {Mn_val:.2f}\text{{ kNm}}")
        st.latex(rf"\phi M_n = {phi_f:.3f} \times {Mn_val:.2f} = \mathbf{{{phiMn_val:.2f}}}\text{{ kNm}}")
        
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric(label="Required Demand ($M_u$)", value=f"{abs(Mu):.2f} kNm")
        mc2.metric(label="Provided Capacity ($\phi M_n$)", value=f"{phiMn_val:.2f} kNm", delta=f"{phiMn_val - abs(Mu):.2f} kNm")
        
        if phiMn_val >= abs(Mu) and eps_t_val >= 0.004:
            mc3.success("✅ STATUS: PASS")
        elif eps_t_val < 0.004:
            mc3.error("❌ STATUS: FAIL (Code Violation: ε_t < 0.004)")
        else:
            mc3.error("❌ STATUS: FAIL (Capacity)")

        return d_eff, dt_approx

    # =========================================================
    # 2. FLEXURAL CAPACITY AUDIT (Execution)
    # =========================================================
    st.markdown("### 2. Flexural Strength Audit (Ref: ACI 22.2)")
    
    # Render Top Reinforcement (Negative Moment) -> is_top=True
    st.markdown("🔽 **NEGATIVE MOMENT (Support / Top Steel)**")
    render_flexural_audit("Top Reinforcement Evaluation", Mu_neg, bot_layers, top_layers, is_top=True)
    
    st.write("---")
    
    # Render Bottom Reinforcement (Positive Moment) -> is_top=False
    st.markdown("🔼 **POSITIVE MOMENT (Mid-span / Bottom Steel)**")
    d_eff_bot, dt_bot = render_flexural_audit("Bottom Reinforcement Evaluation", Mu_pos, bot_layers, top_layers, is_top=False)


    # =========================================================
    # 3. SHEAR CAPACITY AUDIT
    # =========================================================
    st.divider()
    st.markdown("### 3. Shear Strength Audit (Ref: ACI 22.5)")
    
    d_shear = d_eff_bot if d_eff_bot > 0 else (h - cov - stir_db - 8)
    
    st.latex(rf"\text{{Factored Shear Force, }} V_u = {abs(Vu):.2f}\text{{ kN}}")
    
    Vc = (0.17 * 1.0 * np.sqrt(fc) * b * d_shear) / 1000
    Av = 2 * (np.pi * (stir_db**2) / 4) 
    
    st.latex(rf"A_v = 2 \times \frac{{\pi d_b^2}}{{4}} = 2 \times \frac{{\pi ({stir_db})^2}}{{4}} = {Av:.1f} \text{{ mm}}^2 \quad \text{{(2 legs)}}")
    st.latex(rf"V_c = 0.17 \lambda \sqrt{{f'_c}} b_w d = 0.17(1.0)\sqrt{{{fc}}}({b:.0f})({d_shear:.1f}) \times 10^{{-3}} = {Vc:.2f}\text{{ kN}}")
    
    if stir_s > 0:
        Vs = (Av * fy * d_shear / stir_s) / 1000
        st.latex(rf"V_s = \frac{{A_v f_{{yt}} d}}{{s}} = \frac{{{Av:.1f} \times {fy} \times {d_shear:.1f}}}{{{stir_s}}} \times 10^{{-3}} = {Vs:.2f}\text{{ kN}}")
    else:
        Vs = 0
        st.latex(r"V_s = 0 \text{ kN (No shear reinforcement provided)}")
        
    phiVn = 0.75 * (Vc + Vs)
    st.latex(rf"\phi V_n = 0.75(V_c + V_s) = 0.75({Vc:.2f} + {Vs:.2f}) = \mathbf{{{phiVn:.2f}}}\text{{ kN}}")
    
    sc1, sc2 = st.columns(2)
    sc1.metric("Required Shear ($V_u$)", f"{abs(Vu):.2f} kN")
    sc2.metric("Shear Capacity ($\phi V_n$)", f"{phiVn:.2f} kN", delta=f"{phiVn - abs(Vu):.2f} kN")

    s_max = min(d_shear/2, 600)
    st.markdown(rf"**ACI Maximum Spacing Limit ($s_{{max}}$):** $\min(d/2, 600) = \mathbf{{{s_max:.0f}}}\text{{ mm}}$")
    if stir_s <= s_max and phiVn >= abs(Vu):
        st.success(rf"✅ Shear PASS: $\phi V_n \ge V_u$ | Provided spacing ({stir_s} mm) $\le s_{{max}}$ ({s_max:.0f} mm)")
    else:
        st.error(rf"❌ Shear FAIL: Check capacity or spacing limit")

    # =========================================================
    # 4. SERVICEABILITY AUDIT
    # =========================================================
    st.divider()
    st.markdown("### 4. Serviceability Audit (Ref: ACI 24.2)")
    
    # --- 4.1 Deflection ---
    st.markdown("#### 4.1 Deflection Control")
    L_mm = L_m * 1000
    allowable_def = L_mm / 240
    
    st.write("**Instantaneous Deflection Limit (L/240):**")
    st.latex(rf"\Delta_{{allow}} = \frac{{L}}{{240}} = \frac{{{L_mm:.0f}}}{{240}} = \mathbf{{{allowable_def:.2f}}}\text{{ mm}}")
    st.latex(rf"\Delta_{{actual}} = \mathbf{{{abs(delta_svc):.3f}}}\text{{ mm}}")

    if abs(delta_svc) <= allowable_def:
        st.success(rf"✅ Deflection PASS: $\Delta_{{actual}} \le \Delta_{{allow}}$")
    else:
        st.warning(rf"⚠️ Deflection FAIL: $\Delta_{{actual}} > \Delta_{{allow}}$ (Increase section stiffness)")

    # --- 4.2 Crack Width ---
    st.markdown("#### 4.2 Crack Width Control (Gergely-Lutz)")
    
    valid_bot_layers = [ly for ly in bot_layers if ly.get('n', 0) > 0 and ly.get('db', 0) > 0]
    
    if 'crack' in res or valid_bot_layers:
        crack_data = res.get('crack', {})
        w_lim = crack_data.get('limit', 0.4)
        
        bot_db_1 = valid_bot_layers[0]['db'] if valid_bot_layers else 12
        dc = cov + stir_db + (bot_db_1 / 2)
        
        fs = fy * 0.6 # Approximation for service steel stress
        bot_n_total = sum(layer['n'] for layer in valid_bot_layers) if valid_bot_layers else 1
        A_eff = (2 * dc * b) / bot_n_total if bot_n_total > 0 else 0
        
        w_val = 0.076 * 1.2 * fs * np.cbrt(dc * A_eff) * 1e-3
        
        st.markdown("Based on Gergely-Lutz equation (Modified for SI):")
        st.latex(rf"w = 0.076 \beta f_s \sqrt[3]{{d_c A}}")
        st.latex(rf"w \approx 0.076 (1.2) ({fs:.0f}) \sqrt[3]{{{dc:.1f} \times {A_eff:.1f}}} \times 10^{{-3}} = \mathbf{{{w_val:.3f}}}\text{{ mm}}")
            
        if w_val > w_lim:
             st.error(rf"⚠️ Crack width ({w_val:.3f} mm) exceeds limit ({w_lim} mm). Recommend using smaller bar diameter with closer spacing.")
        else:
             st.success(rf"✅ Crack width control passed ({w_val:.3f} mm $\le$ {w_lim} mm).")
    else:
        st.info("Crack width analysis data not available.")

    st.divider()
    st.caption("Generated by Pro RC Beam Design Software | ACI 318-19 Compliant (Rigorous Strain Compatibility)")
