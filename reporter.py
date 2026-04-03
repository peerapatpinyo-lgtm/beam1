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
            # สร้าง List ไว้เก็บข้อความสมการของแต่ละชั้น
            num_terms = []
            den_terms = []
            
            for i, layer in enumerate(valid_t_layers):
                n = layer['n']
                db = layer['db']
                
                A_layer = n * (np.pi * (db/2)**2)
                y_center = current_y + (db/2)
                
                if i == 0:
                    dt_approx = h - y_center 
                
                # --- แก้บั๊ก ext ด้วยการใช้ rf (Raw f-string) ---
                st.write(rf"- **Layer {i+1}:** {int(n)}-DB{int(db)} | $A_{{s{i+1}}} = {A_layer:.1f} \text{{ mm}}^2$ | $y_{{{i+1}}} = {y_center:.1f} \text{{ mm}}$")
                
                total_As += A_layer
                sum_Ay += (A_layer * y_center)
                current_y += db + vertical_spacing
                
                # เก็บค่าเพื่อนำไปแสดงในสมการ y_bar
                num_terms.append(f"({A_layer:.1f} \\times {y_center:.1f})")
                den_terms.append(f"{A_layer:.1f}")
                
            y_bar = sum_Ay / total_As if total_As > 0 else 0
            d_eff = h - y_bar
            
            if len(valid_t_layers) > 1:
                # นำข้อความสมการมาเชื่อมกันด้วยเครื่องหมายบวก
                num_str = " + ".join(num_terms)
                den_str = " + ".join(den_terms)
                
                st.markdown("**การหาจุดศูนย์ถ่วงกลุ่มเหล็กเสริม (Centroid, $\\bar{y}$):**")
                st.latex(r"\bar{y} = \frac{\sum (A_i \times y_i)}{\sum A_i}")
                # บรรทัดนี้คือการแทนค่าตัวเลขแบบกระจายทุกชั้น
                st.latex(rf"\bar{{y}} = \frac{{{num_str}}}{{{den_str}}}")
                st.latex(rf"\bar{{y}} = \frac{{{sum_Ay:.1f}}}{{{total_As:.1f}}} = {y_bar:.1f} \text{{ mm}}")
                # แสดงการคำนวณ d_eff
                st.latex(rf"d_{{eff}} = h - \bar{{y}} = {h:.0f} - {y_bar:.1f} = \mathbf{{{d_eff:.1f}}}\text{{ mm}}")
            else:
                # --- เพิ่มการแสดงสมการและแทนค่า d_eff กรณีมีเหล็กชั้นเดียว ---
                db1 = valid_t_layers[0]['db']
                st.latex(rf"d_{{eff}} = h - \text{{cover}} - d_{{stirrup}} - \frac{{d_b}}{{2}}")
                st.latex(rf"d_{{eff}} = {h:.0f} - {cov:.0f} - {stir_db:.0f} - \frac{{{db1:.0f}}}{{2}} = \mathbf{{{d_eff:.1f}}}\text{{ mm}}")
        else:
            st.warning("No reinforcement provided.")
            d_eff, total_As, y_bar, dt_approx = 0, 0, 0, 0
            return 0, 0
       

        # --- Required Steel Calculation (Detailed) ---
        st.markdown("**2. Required Reinforcement ($A_{s,req}$)**")
        Mu_calc = abs(Mu) * 1e6
        phi_flex = 0.9
        
        # คำนวณ Rn และ rho_req
        if d_eff > 0:
            Rn = Mu_calc / (phi_flex * b * d_eff**2)
            st.latex(rf"R_n = \frac{{M_u}}{{\phi b d_{{eff}}^2}} = \frac{{{Mu_calc:.0f}}}{{0.9 \times {b:.0f} \times {d_eff:.1f}^2}} = {Rn:.3f} \text{{ MPa}}")
            
            term_inside = 1 - (2 * Rn) / (0.85 * fc)
            if term_inside >= 0:
                rho_req = (0.85 * fc / fy) * (1 - np.sqrt(term_inside))
                st.latex(rf"\rho_{{req}} = \frac{{0.85 f'_c}}{{f_y}} \left( 1 - \sqrt{{1 - \frac{{2 R_n}}{{0.85 f'_c}}}} \right)")
                st.latex(rf"\rho_{{req}} = \frac{{0.85({fc})}}{{{fy}}} \left( 1 - \sqrt{{1 - \frac{{2({Rn:.3f})}}{{0.85({fc})}}}} \right) = {rho_req:.5f}")
            else:
                rho_req = 0
                st.error("⚠️ Section is over-reinforced or requires compression steel (Rn too high).")
        else:
            Rn, rho_req = 0, 0
            
        # คำนวณ rho_min
        rho_min_1 = 0.25 * np.sqrt(fc) / fy
        rho_min_2 = 1.4 / fy
        rho_min = max(rho_min_1, rho_min_2)
        
        st.latex(r"\rho_{min} = \max\left(\frac{0.25 \sqrt{f'_c}}{f_y}, \frac{1.4}{f_y}\right)")
        st.latex(rf"\rho_{{min}} = \max\left(\frac{{0.25 \sqrt{{{fc}}}}}{{{fy}}}, \frac{{1.4}}{{{fy}}}\right) = \max({rho_min_1:.5f}, {rho_min_2:.5f}) = {rho_min:.5f}")

        # คำนวณ As 
        as_req_calc = rho_req * b * d_eff
        as_min_calc = rho_min * b * d_eff
        as_final_req = max(as_req_calc, as_min_calc)

        st.latex(rf"A_{{s,req}} = \rho_{{req}} b d_{{eff}} = {rho_req:.5f} \times {b:.0f} \times {d_eff:.1f} = {as_req_calc:.1f} \text{{ mm}}^2")
        st.latex(rf"A_{{s,min}} = \rho_{{min}} b d_{{eff}} = {rho_min:.5f} \times {b:.0f} \times {d_eff:.1f} = {as_min_calc:.1f} \text{{ mm}}^2")
        
        # สรุปเปรียบเทียบ
        st.markdown(rf"**$\Rightarrow$ Design Required $A_s$:** $\max(A_{{s,req}}, A_{{s,min}}) = \mathbf{{{as_final_req:.1f}}} \text{{ mm}}^2$")
        st.markdown(rf"**$\Rightarrow$ Provided Capacity ($A_{{s,prov}}$):** $\mathbf{{{total_As:.1f}}} \text{{ mm}}^2$")
        
        if total_As >= as_final_req:
            st.success(rf"✅ Check: $A_{{s,prov}}$ ({total_As:.1f} mm²) $\ge$ Required $A_s$ ({as_final_req:.1f} mm²)")
        else:
            st.error(rf"❌ Check: $A_{{s,prov}}$ ({total_As:.1f} mm²) $<$ Required $A_s$ ({as_final_req:.1f} mm²) - Please increase reinforcement!")
       
        # ==========================================
        # 🌟 NEW: STRAIN COMPATIBILITY ANALYSIS WITH PLOT
        # ==========================================

        st.markdown("**3. Strain Compatibility & Stress Block (Iterative Method)**")
        
        # เรียกใช้งาน Engine คำนวณแบบละเอียด
        phiMn_val, As_t_val, a_val, Mn_val, c_val, eps_t_val, layer_res = get_phi_Mn_details_multi(
            all_bot_layers, all_top_layers, b, h, fc, fy, cov, stir_db, is_top_tension=is_top
        )


        st.latex(rf"c = {c_val:.2f} \text{{ mm}} \quad \text{{(Neutral Axis Depth)}}")
        st.latex(rf"a = \beta_1 c = {beta1:.3f} \times {c_val:.2f} = {a_val:.2f} \text{{ mm}}")

        # 1. วาดรูปหน้าตัดแบบเต็มความกว้าง (อยู่ด้านบน)
        if c_val > 0 and a_val > 0:
            try:
                fig_stress = section_plotter.plot_detailed_stress_strain(
                    b=b, h=h, c=c_val, a=a_val, fc=fc, layer_res=layer_res, is_top=is_top
                )
                # ไม่ต้องใส่ในคอลัมน์แล้ว ใช้ st.pyplot ตรงๆ เพื่อให้เต็มจอ
                st.pyplot(fig_stress, use_container_width=True)
            except Exception as e:
                st.error(f"⚠️ Diagram rendering failed: {e}")
                
        st.divider() # ตีเส้นแบ่งนิดหน่อยให้ดูสบายตา

        # 2. แบ่ง 2 คอลัมน์สำหรับเหล็กรับแรงอัดและแรงดึง (อยู่ด้านล่างรูป)
        col_comp, col_tens = st.columns(2)
        
        # --- คอลัมน์ซ้าย: เหล็กรับแรงอัด (Compression) ---
        with col_comp:
            comp_layers = [ly for ly in layer_res if ly['type'] == 'Compression']
            if comp_layers:
                st.markdown("🔴 **เหล็กรับแรงอัด (Compression):**")
                st.latex(r"\epsilon_s = 0.003 \left( \frac{c - d_i}{c} \right)")
                
                for lay_res in comp_layers:
                    di = lay_res['d_i']
                    eps_s = abs(lay_res['eps_s'])
                    fs = abs(lay_res['fs'])
                    is_yield = lay_res['is_yielded']
                    
                    status = "🔴 Yielded" if is_yield else "⚪ Elastic"
                    st.markdown(f"- **Layer @ $d'_i = {di:.1f}$ mm:**")
                    st.latex(rf"\epsilon_s = 0.003 \times \frac{{{c_val:.2f} - {di:.1f}}}{{{c_val:.2f}}} = {eps_s:.5f}")
                    
                    fs_calc = eps_s * Es
                    if is_yield:
                        st.latex(rf"f'_s = {eps_s:.5f} \times 200,000 = {fs_calc:.1f} \rightarrow \mathbf{{{fs:.1f}}} \text{{ MPa}} \text{{ ({status})}}")
                    else:
                        st.latex(rf"f'_s = {eps_s:.5f} \times 200,000 = \mathbf{{{fs:.1f}}} \text{{ MPa}} \text{{ ({status})}}")
            else:
                st.markdown("🔴 **เหล็กรับแรงอัด (Compression):**")
                st.info("ไม่มีเหล็กรับแรงอัด (Singly Reinforced)")

        # --- คอลัมน์ขวา: เหล็กรับแรงดึง (Tension) ---
        with col_tens:
            tens_layers = [ly for ly in layer_res if ly['type'] == 'Tension']
            if tens_layers:
                st.markdown("🟢 **เหล็กรับแรงดึง (Tension):**")
                st.latex(r"\epsilon_s = 0.003 \left( \frac{d_i - c}{c} \right)")
                
                for lay_res in tens_layers:
                    di = lay_res['d_i']
                    eps_s = lay_res['eps_s']
                    fs = lay_res['fs']
                    is_yield = lay_res['is_yielded']
                    
                    status = "🟢 Yielded" if is_yield else "🟡 Elastic"
                    st.markdown(f"- **Layer @ $d_i = {di:.1f}$ mm:**")
                    st.latex(rf"\epsilon_s = 0.003 \times \frac{{{di:.1f} - {c_val:.2f}}}{{{c_val:.2f}}} = {eps_s:.5f}")
                    
                    fs_calc = eps_s * Es
                    if is_yield:
                        st.latex(rf"f_s = {eps_s:.5f} \times 200,000 = {fs_calc:.1f} \rightarrow \mathbf{{{fs:.1f}}} \text{{ MPa}} \text{{ ({status})}}")
                    else:
                        st.latex(rf"f_s = {eps_s:.5f} \times 200,000 = \mathbf{{{fs:.1f}}} \text{{ MPa}} \text{{ ({status})}}")
            else:
                st.markdown("🟢 **เหล็กรับแรงดึง (Tension):**")
                st.warning("ไม่มีเหล็กรับแรงดึง")
# --- Ultimate Strength Limit State ---
        st.markdown("**4. Ultimate Flexural Capacity ($\phi M_n$) & Exact Moment Summation**")
        
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
        
        # --- เพิ่มการแจกแจงที่มาของโมเมนต์แบบ Exact ---
        st.markdown("**Breakdown of Moment about Compression Face:**")
        
        # 1. โมเมนต์จากคอนกรีต
        Cc_kN = (0.85 * fc * a_val * b) / 1000
        M_conc_kNm = Cc_kN * (a_val / 2) / 1000
        st.latex(rf"M_{{concrete}} = C_c \times \frac{{a}}{{2}} = {Cc_kN:.1f} \times \frac{{{a_val:.1f}}}{{2}} \times 10^{{-3}} = {M_conc_kNm:.2f} \text{{ kNm}}")
        
        # 2. โมเมนต์จากเหล็กแต่ละชั้น
        sum_M_steel = 0.0
        for lay_res in layer_res:
            F_kN = (lay_res['area'] * lay_res['fs']) / 1000
            arm_m = lay_res['d_i'] / 1000
            M_layer = F_kN * arm_m
            sum_M_steel += M_layer
            
            # แสดงค่าเฉพาะชั้นที่มีแรงกระทำนัยสำคัญ (เพื่อไม่ให้หน้าจอยาวเกินไป)
            if abs(F_kN) > 0.1:
                st.latex(rf"M_{{s, layer {lay_res['layer_idx']}}} = F_s \times d_i = {F_kN:.1f} \times {arm_m:.3f} = {M_layer:.2f} \text{{ kNm}}")

        # 3. สรุปผลรวมโมเมนต์
        st.latex(rf"M_{{n,exact}} = M_{{concrete}} + \sum M_s = {M_conc_kNm:.2f} + {sum_M_steel:.2f} = \mathbf{{{Mn_val:.2f}}}\text{{ kNm}}")
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
        
        # เพิ่มตัวเลือก Deflection Limit ตามมาตรฐาน ACI 318 Table 24.2.2
        def_options = {
            "L/180 (หลังคาแบน ที่ไม่รองรับชิ้นส่วนที่แตกหักง่าย)": 180,
            "L/240 (พื้น/หลังคา ที่รองรับชิ้นส่วนที่ไม่แตกหักง่าย)": 240,
            "L/360 (พื้นทั่วไป ที่ไม่รองรับชิ้นส่วนที่แตกหักง่าย)": 360,
            "L/480 (พื้น/หลังคา ที่รองรับชิ้นส่วนที่แตกหักง่าย)": 480
        }
        
        selected_def_label = st.selectbox(
            "📍 เลือกเกณฑ์ระยะแอ่นตัวที่ยอมให้ (Allowable Deflection Limit):",
            options=list(def_options.keys()),
            index=1 # ตั้งค่าเริ่มต้นไว้ที่ L/240
        )
        
        denom_def = def_options[selected_def_label]
        allowable_def = L_mm / denom_def
        
        st.write("**Allowable Deflection Limit:**")
        st.latex(rf"\Delta_{{allow}} = \frac{{L}}{{{denom_def}}} = \frac{{{L_mm:.0f}}}{{{denom_def}}} = \mathbf{{{allowable_def:.2f}}}\text{{ mm}}")
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
