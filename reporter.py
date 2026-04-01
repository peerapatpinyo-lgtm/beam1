# reporter.py
import streamlit as st
import numpy as np

def render_calculation_report(res):
    """
    Ultra-Detailed ACI 318-19 Compliance Report.
    Includes Clause References, Substitutions, Limit States, and Crack Width Control.
    """
    # --- Data Extraction ---
    # ใช้ .get() เพื่อป้องกัน Error กรณี key ไม่ครบ
    idx = res.get('span_id', 0) + 1
    L_m = res.get('L', 0)
    b = res.get('b', 200) 
    h = res.get('h', 400) 
    cov = res.get('cover', 25)
    fc = res.get('fc', 24)
    fy = res.get('fy', 400)
    
    Mu = res.get('Mu_pos', 0)
    Vu = res.get('Vu_max', 0)
    Ma = res.get('Ma_pos_svc', 0)    
    delta_svc = res.get('delta_svc_mm', 0) 
    
    # Extract Reinforcement Data safely
    bot = res.get('bot', {})
    bot_n = bot.get('n', 0)
    bot_db = bot.get('db', 12)
    
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

    st.markdown(f"## 🏛️ Comprehensive ACI 318-19 Design Audit: Span {idx}")
    st.markdown(f"**Structural Element:** Continuous RC Beam | **Span Length:** {L_m:.2f} m")
    st.divider()

    # =========================================================
    # 1. MATERIAL & SECTION PROPERTIES (ACI 19.2 & 20.2)
    # =========================================================
    st.markdown("### 1. Materials & Geometry (Ref: ACI 19.2 & 20.2)")
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Concrete Strength Properties:**")
        st.latex(rf"f'_c = {fc} \text{{ MPa (N/mm}^2\text{{)}}")
        st.latex(rf"E_c = 4700\sqrt{{f'_c}} = {Ec:.0f} \text{{ MPa}}")
        st.latex(rf"\beta_1 = {beta1:.3f} \quad \text{{(ACI 22.2.2.4.3)}}")
    with c2:
        st.write("**Steel Reinforcement:**")
        st.latex(rf"f_y = {fy} \text{{ MPa (N/mm}^2\text{{)}}")
        st.latex(rf"E_s = 200,000 \text{{ MPa}}")
        st.latex(rf"\text{{Section: }} {b:.0f} \times {h:.0f} \text{{ mm}}")

    # =========================================================
    # 2. FLEXURAL CAPACITY AUDIT (ACI 22.2)
    # =========================================================
    st.markdown("### 2. Flexural Strength Audit (Ref: ACI 22.2)")
    
    # 2.1 Effective Depth (d)
    d = h - cov - stir_db - (bot_db/2)
    st.markdown("**2.1 Effective Depth Calculation**")
    st.latex(rf"d = h - c_{{clear}} - \text{{db}}_{{stirrup}} - \frac{{\text{{db}}_{{bar}}}}{{2}}")
    st.latex(rf"d = {h} - {cov} - {stir_db} - \frac{{{bot_db}}}{{2}} = \mathbf{{{d:.1f}}}\text{{ mm}}")

    # [NEW] 2.2 Step-by-Step Required Steel Calculation
    st.markdown("**2.2 Required Reinforcement Calculation ($A_{s,req}$)**")
    
    # --- อธิบายเรื่องการแปลงหน่วย ---
    st.info("💡 **ข้อสังเกตเรื่องการแปลงหน่วย (Unit Conversion):**\n"
            "* โมเมนต์ประลัย ($M_u$) เดิมมีหน่วยเป็น $kN \cdot m$ จำเป็นต้องแปลงเป็น $N \cdot mm$ โดยการคูณ $10^6$\n"
            "* สาเหตุเพื่อให้สอดคล้องกับ $f'_c$ และ $f_y$ ที่มีหน่วยเป็น $MPa$ ($N/mm^2$) และมิติหน้าตัดคาน $b, d$ ที่เป็น $mm$ เพื่อให้หน่วยตัดกันได้พอดี")

    Mu_abs = abs(Mu)
    Mu_calc = Mu_abs * 1e6
    phi_flex = 0.9
    
    Rn = Mu_calc / (phi_flex * b * d**2) if d > 0 else 0
    term_inside = 1 - (2 * Rn) / (0.85 * fc)
    rho_req = (0.85 * fc / fy) * (1 - np.sqrt(term_inside)) if term_inside >= 0 else 0
    
    rho_min = max((0.25 * np.sqrt(fc) / fy), (1.4 / fy))
    rho_max = (0.85 * fc * beta1 / fy) * (0.003 / (0.003 + 0.005))
    
    as_req_calc = rho_req * b * d
    as_min_calc = rho_min * b * d
    as_final_req = max(as_req_calc, as_min_calc)

    # แสดงวิธีทำ: สูตร -> แทนค่า -> ตอบ
    st.markdown("**Step A: หาค่า $R_n$ (Coefficient of Resistance)**")
    st.latex(r"R_n = \frac{M_u \times 10^6}{\phi b d^2}")
    st.latex(rf"R_n = \frac{{{Mu_abs:.2f} \times 10^6}}{{{phi_flex} \cdot {b} \cdot {d:.1f}^2}} = \mathbf{{{Rn:.3f}}} \text{{ MPa}}")

    st.markdown("**Step B: หาค่าอัตราส่วนเหล็กเสริมที่ต้องการ ($\rho_{req}$)**")
    st.latex(r"\rho_{req} = \frac{0.85 f'_c}{f_y} \left( 1 - \sqrt{1 - \frac{2 R_n}{0.85 f'_c}} \right)")
    st.latex(rf"\rho_{req} = \frac{{0.85({fc})}}{{{fy}}} \left( 1 - \sqrt{{1 - \frac{{2({Rn:.3f})}}{{0.85({fc})}}}} \right) = \mathbf{{{rho_req:.5f}}}")

    st.markdown("**Step C: ตรวจสอบปริมาณเหล็กเสริมต่ำสุดและสูงสุด ($\rho_{min}, \rho_{max}$)**")
    st.latex(r"\rho_{min} = \max \left( \frac{0.25\sqrt{f'_c}}{f_y}, \frac{1.4}{f_y} \right)")
    st.latex(rf"\rho_{min} = \max \left( \frac{{0.25\sqrt{{{fc}}}}}{{{fy}}}, \frac{{1.4}}{{{fy}}} \right) = \mathbf{{{rho_min:.5f}}}")
    
    st.latex(r"\rho_{max} = \left( \frac{0.85 f'_c \beta_1}{f_y} \right) \left( \frac{0.003}{0.003 + 0.005} \right)")
    st.latex(rf"\rho_{max} = \left( \frac{{0.85({fc})({beta1:.3f})}}{{{fy}}} \right) \left( \frac{{0.003}}{{0.008}} \right) = \mathbf{{{rho_max:.5f}}}")

    st.markdown("**Step D: สรุปพื้นที่เหล็กเสริมที่ต้องการ ($A_{s,req}$)**")
    st.latex(rf"A_{{s,req\_calc}} = \rho_{{req}} b d = {rho_req:.5f} \cdot {b} \cdot {d:.1f} = {as_req_calc:.1f} \text{{ mm}}^2")
    st.latex(rf"A_{{s,min}} = \rho_{{min}} b d = {rho_min:.5f} \cdot {b} \cdot {d:.1f} = {as_min_calc:.1f} \text{{ mm}}^2")
    st.markdown(rf"**$\Rightarrow$ Design Required $A_s$:** $\max(A_{{s,req\_calc}}, A_{{s,min}}) = \mathbf{{{as_final_req:.1f}}} \text{{ mm}}^2$")

    # 2.3 Provided Steel & Section Capacity Check
    st.markdown("**2.3 Section Capacity Verification**")
    As = bot_n * (np.pi * (bot_db/2)**2)
    
    if As >= as_final_req:
        st.caption(f"✅ Provided As ({As:.1f} mm²) > Required As ({as_final_req:.1f} mm²)")
    else:
        st.error(f"❌ Provided As ({As:.1f} mm²) < Required As ({as_final_req:.1f} mm²)")

    # Calculate a (Depth of equivalent rectangular stress block)
    if As > 0:
        a = (As * fy) / (0.85 * fc * b)
        c_neutral = a / beta1
    else:
        a = 0
        c_neutral = 0

    # Calculate Strain
    if c_neutral > 0:
        epsilon_t = 0.003 * (d - c_neutral) / c_neutral
    else:
        epsilon_t = 999 # Infinite ductility implies no compression block

    # Determine Phi (Table 21.2.2)
    if epsilon_t >= 0.005:
        phi_f = 0.90
        state = "Tension-Controlled (Ductile)"
    elif epsilon_t <= 0.002:
        phi_f = 0.65
        state = "Compression-Controlled (Brittle)"
    else:
        phi_f = 0.65 + 0.25 * (epsilon_t - 0.002) / 0.003
        state = "Transition Zone"

    st.latex(rf"a = \frac{{A_s f_y}}{{0.85 f'_c b}} = \frac{{{As:.1f} \cdot {fy}}}{{0.85 \cdot {fc} \cdot {b}}} = {a:.2f}\text{{ mm}}")
    st.latex(rf"c = a/\beta_1 = {a:.2f}/{beta1:.3f} = {c_neutral:.2f}\text{{ mm}}")
    st.latex(rf"\epsilon_t = 0.003 \left( \frac{{d - c}}{{c}} \right) = \mathbf{{{epsilon_t:.5f}}}")
    st.info(f"**Result:** {state} | $\phi = {phi_f:.3f}$")

    # 2.4 Nominal vs Factored Moment
    Mn = As * fy * (d - a/2) * 1e-6
    phiMn = phi_f * Mn
    st.markdown("**2.4 Ultimate Strength Limit State**")
    st.latex(rf"M_n = A_s f_y (d - a/2) = {As:.0f} \cdot {fy} \cdot ({d:.1f} - {a/2:.1f}) \cdot 10^{{-6}} = {Mn:.2f}\text{{ kNm}}")
    st.latex(rf"\phi M_n = {phi_f:.2f} \cdot {Mn:.2f} = \mathbf{{{phiMn:.2f}}}\text{{ kNm}}")
    
    if phiMn >= Mu_abs:
        st.success(rf"✅ $\phi M_n ({phiMn:.2f} \text{{ kNm}}) \ge M_u ({Mu_abs:.2f} \text{{ kNm}})$ — Capacity OK")
    else:
        st.error(rf"❌ $\phi M_n ({phiMn:.2f} \text{{ kNm}}) < M_u ({Mu_abs:.2f} \text{{ kNm}})$ — INSUFFICIENT")

    # =========================================================
    # 3. SHEAR CAPACITY AUDIT (ACI 22.5)
    # =========================================================
    st.divider()
    st.markdown("### 3. Shear Strength Audit (Ref: ACI 22.5)")
    st.latex(rf"V_u = {abs(Vu):.2f}\text{{ kN}}")
    
    Vc = (0.17 * 1.0 * np.sqrt(fc) * b * d) / 1000
    Av = 2 * (np.pi * (stir_db/2)**2) 
    
    if stir_s > 0:
        Vs = (Av * fy * d / stir_s) / 1000
    else:
        Vs = 0
        
    phiVn = 0.75 * (Vc + Vs)

    st.latex(rf"V_c = 0.17 \lambda \sqrt{{f'_c}} b_w d = {Vc:.2f}\text{{ kN}}")
    st.latex(rf"V_s = \frac{{A_v f_{{yt}} d}}{{s}} = {Vs:.2f}\text{{ kN}}")
    st.latex(rf"\phi V_n = 0.75(V_c + V_s) = \mathbf{{{phiVn:.2f}}}\text{{ kN}}")
    
    s_max = min(d/2, 600)
    st.markdown(rf"**ACI Spacing Limit:** $s_{{max}} = \mathbf{{{s_max:.0f}}}\text{{ mm}}$")
    if stir_s <= s_max:
        st.caption(f"✅ Spacing OK ({stir_s} mm)")
    else:
        st.error(f"❌ Spacing exceeds limit ({s_max:.0f} mm)")

    # =========================================================
    # 4. SERVICEABILITY AUDIT (ACI 24.2 & Gergely-Lutz)
    # =========================================================
    st.divider()
    st.markdown("### 4. Serviceability Audit (Ref: ACI 24.2)")
    
    # --- 4.1 Deflection ---
    st.markdown("#### 4.1 Deflection Control")
    L_mm = L_m * 1000
    allowable_def = L_mm / 240
    
    st.write(f"**Limit:** Instantaneous Deflection (L/240):")
    st.latex(rf"\Delta_{{allow}} = \frac{{{L_mm:.0f}}}{{240}} = \mathbf{{{allowable_def:.2f}}}\text{{ mm}}")
    st.latex(rf"\Delta_{{actual}} = \mathbf{{{abs(delta_svc):.3f}}}\text{{ mm}}")

    if abs(delta_svc) <= allowable_def:
        st.success("✅ Deflection: PASS")
    else:
        st.warning("⚠️ Deflection: FAIL (Increase section stiffness)")

    # --- 4.2 Crack Width (Gergely-Lutz) ---
    st.markdown("#### 4.2 Crack Width Control (Gergely-Lutz)")
    
    if 'crack' in res:
        crack_data = res['crack']
        w_val = crack_data.get('w', 0)
        w_lim = crack_data.get('limit', 0.4)
        status = crack_data.get('status', 'N/A')
        
        st.markdown("Based on Gergely-Lutz equation (Modified for SI):")
        st.latex(r"w = 0.076 \beta f_s \sqrt[3]{d_c A}")
        
        c_cr1, c_cr2 = st.columns(2)
        with c_cr1:
            st.markdown(f"""
            **Parameters:**
            - Service Moment ($M_s$): {Ma:.2f} kNm
            - Cover ($d_c$): {cov} mm
            - Steel ($f_y$): {fy} MPa
            """)
        with c_cr2:
            st.markdown(f"""
            **Results:**
            - Calculated Width ($w$): **{w_val:.3f} mm**
            - Limit: {w_lim} mm
            - Status: **{status}**
            """)
            
        if w_val > w_lim:
             st.error(f"⚠️ Crack width ({w_val:.3f} mm) exceeds limit ({w_lim} mm). Recommend using smaller bar diameter with closer spacing.")
        else:
             st.success(f"✅ Crack width control passed.")
    else:
        st.info("Crack width analysis not available for this run.")

    st.divider()
    st.caption("Generated by Pro RC Beam Design Software | ACI 318-19 Compliant")
