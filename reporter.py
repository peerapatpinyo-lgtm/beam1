# reporter.py  ── Fixed & Production-Ready Version
import streamlit as st
import numpy as np
from rc_design_engine import get_phi_Mn_details_multi
import section_plotter
import streamlit.components.v1 as components


def render_calculation_report(res):
    """
    Ultra-Detailed ACI 318-19 Compliance Report.
    Full Equation Substitution, Multiple-Layer Reinforcement, and Strain Compatibility.
    """
    idx    = res.get('span_id', 0) + 1
    L_m    = res.get('L', 0)
    b      = res.get('b', 200)
    h      = res.get('h', 400)
    cov    = res.get('cover', 25)
    fc     = res.get('fc', 24)
    fy     = res.get('fy', 400)
    Mu_pos = res.get('Mu_pos', 0)
    Mu_neg = res.get('Mu_neg', 0)
    Vu     = res.get('Vu_max', 0)
    delta_svc = res.get('delta_svc_mm', 0)

    # Robust layer extraction
    def extract_layers(res_dict, prefix):
        layers = res_dict.get(f'{prefix}_layers', [])
        if not layers and prefix in res_dict:
            d = res_dict[prefix]
            if isinstance(d, dict) and 'all_layers' in d:
                layers = d['all_layers']
            elif isinstance(d, dict):
                layers = [{'n': d.get('n', 0), 'db': d.get('db', 12)}]
        return layers

    bot_layers = extract_layers(res, 'bot')
    top_layers = extract_layers(res, 'top')

    shear    = res.get('shear', {})
    stir_db  = shear.get('db', res.get('stir_db', 9))
    stir_s   = shear.get('s',  res.get('stir_s', 150))

    Es  = 200000.0
    Ec  = 4700 * np.sqrt(fc)
    if fc <= 28:  beta1 = 0.85
    elif fc >= 55: beta1 = 0.65
    else:          beta1 = 0.85 - 0.05 * (fc - 28) / 7

    st.markdown(rf"## 🏛️ ACI 318-19 Design Report — Span {idx}")
    st.markdown(rf"**Element:** Continuous RC Beam | **Span:** {L_m:.2f} m")
    st.divider()

    # ── 1. Materials & Geometry ─────────────────────────────────────────────
    with st.expander("🧱 1. Materials & Geometry (ACI 19.2 / 20.2)", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Concrete:**")
            st.latex(rf"f'_c = {fc:.2f}\ \text{{MPa}}")
            st.latex(rf"E_c = 4700\sqrt{{f'_c}} = 4700\sqrt{{{fc:.2f}}} = {Ec:.0f}\ \text{{MPa}}")
            st.latex(rf"\beta_1 = {beta1:.3f}")
        with c2:
            st.write("**Steel:**")
            st.latex(rf"f_y = {fy:.2f}\ \text{{MPa}},\quad E_s = 200{{,}}000\ \text{{MPa}}")
            st.latex(rf"\text{{Section }}(b \times h) = {b:.0f} \times {h:.0f}\ \text{{mm}}")

    # ── 1.1 Minimum Depth Check ──────────────────────────────────────────────
    with st.expander("📏 1.1 Minimum Beam Depth — ACI Table 9.3.1.1", expanded=False):
        L_mm = L_m * 1000
        fy_mod = 0.4 + fy / 700
        span_type = res.get('span_condition', 'Continuous (Both Ends)')
        denom_map = {'Simply Supported': 16, 'Continuous (One End)': 18.5,
                     'Continuous (Both Ends)': 21, 'Cantilever': 8}
        denom = denom_map.get(span_type, 21)
        h_min = (L_mm / denom) * fy_mod
        st.write(f"**Span Condition:** {span_type}")
        st.latex(rf"h_{{min}} = \frac{{L}}{{{denom}}}\!\left(0.4+\frac{{f_y}}{{700}}\right) = \frac{{{L_mm:.0f}}}{{{denom}}}\!\left(0.4+\frac{{{fy:.1f}}}{{700}}\right) = {h_min:.1f}\ \text{{mm}}")
        cols = st.columns(3)
        cols[0].metric("Provided h", f"{h:.0f} mm")
        cols[1].metric("Required h_min", f"{h_min:.1f} mm")
        if h >= h_min:
            cols[2].success("✅ PASS")
        else:
            cols[2].warning("⚠️ FAIL — Compute exact deflection")

    # ── Helper: Full Flexural Audit ──────────────────────────────────────────
    def render_flexural_audit(Mu, all_bot_layers, all_top_layers, is_top=False):
        if abs(Mu) == 0:
            st.info("No moment demand for this section.")
            return 0, 0

        tension_layers = all_top_layers if is_top else all_bot_layers
        valid_t = [ly for ly in tension_layers if ly.get('n', 0) > 0 and ly.get('db', 0) > 0]

        total_As, sum_Ay, current_y, dt_approx = 0.0, 0.0, cov + stir_db, 0.0
        num_terms, den_terms = [], []

        st.markdown("**1. Reinforcement Details (Tension Side)**")
        if valid_t:
            for i, layer in enumerate(valid_t):
                n, db = layer['n'], layer['db']
                A_layer = n * (np.pi * (db / 2) ** 2)
                y_center = current_y + db / 2
                if i == 0: dt_approx = h - y_center
                st.write(rf"- **Layer {i+1}:** {int(n)}-DB{int(db)} | $A_{{s{i+1}}} = {A_layer:.1f}\ \text{{mm}}^2$ | $y_{{{i+1}}} = {y_center:.1f}\ \text{{mm}}$")
                total_As  += A_layer
                sum_Ay    += A_layer * y_center
                current_y += db + 25.0
                num_terms.append(f"({A_layer:.1f}\\times{y_center:.1f})")
                den_terms.append(f"{A_layer:.1f}")

            y_bar  = sum_Ay / total_As if total_As > 0 else 0
            d_eff  = h - y_bar

            if len(valid_t) > 1:
                st.markdown("**Centroid of reinforcement ($\\bar{y}$):**")
                st.latex(r"\bar{y}=\frac{\sum(A_i\times y_i)}{\sum A_i}")
                st.latex(rf"\bar{{y}}=\frac{{{'+'.join(num_terms)}}}{{{'+'.join(den_terms)}}}={y_bar:.1f}\ \text{{mm}}")
                st.latex(rf"d_{{eff}}=h-\bar{{y}}={h:.0f}-{y_bar:.1f}=\mathbf{{{d_eff:.1f}}}\ \text{{mm}}")
            else:
                db1 = valid_t[0]['db']
                st.latex(rf"d_{{eff}}=h-\text{{cover}}-d_{{stir}}-\frac{{d_b}}{{2}}={h:.0f}-{cov:.0f}-{stir_db:.0f}-\frac{{{db1:.0f}}}{{2}}=\mathbf{{{d_eff:.1f}}}\ \text{{mm}}")
        else:
            st.warning("No reinforcement provided.")
            return 0, 0

        # Required As
        st.markdown("**2. Required Reinforcement ($A_{s,req}$)**")
        Mu_calc   = abs(Mu) * 1e6
        phi_flex  = 0.9
        if d_eff > 0:
            Rn = Mu_calc / (phi_flex * b * d_eff ** 2)
            st.latex(rf"R_n=\frac{{M_u}}{{\phi b\,d_{{eff}}^2}}=\frac{{{Mu_calc:.0f}}}{{0.9\times{b:.0f}\times{d_eff:.1f}^2}}={Rn:.3f}\ \text{{MPa}}")
            term = 1 - 2 * Rn / (0.85 * fc)
            if term >= 0:
                rho_req = (0.85 * fc / fy) * (1 - np.sqrt(term))
                st.latex(rf"\rho_{{req}}=\frac{{0.85f'_c}}{{f_y}}\!\left(1-\sqrt{{1-\frac{{2R_n}}{{0.85f'_c}}}}\right)={rho_req:.5f}")
            else:
                rho_req = 0
                st.error("⚠️ Section over-reinforced — requires compression steel.")
        else:
            Rn, rho_req = 0, 0

        rho_min_1 = 0.25 * np.sqrt(fc) / fy
        rho_min_2 = 1.4 / fy
        rho_min   = max(rho_min_1, rho_min_2)
        st.latex(rf"\rho_{{min}}=\max\!\left(\frac{{0.25\sqrt{{f'_c}}}}{{f_y}},\frac{{1.4}}{{f_y}}\right)=\max({rho_min_1:.5f},{rho_min_2:.5f})={rho_min:.5f}")

        as_req_calc  = rho_req  * b * d_eff
        as_min_calc  = rho_min  * b * d_eff
        as_final_req = max(as_req_calc, as_min_calc)
        st.latex(rf"A_{{s,req}}={rho_req:.5f}\times{b:.0f}\times{d_eff:.1f}={as_req_calc:.1f}\ \text{{mm}}^2")
        st.latex(rf"A_{{s,min}}={rho_min:.5f}\times{b:.0f}\times{d_eff:.1f}={as_min_calc:.1f}\ \text{{mm}}^2")
        st.markdown(rf"$\Rightarrow$ **Design $A_s$:** $\max={{\mathbf{{{as_final_req:.1f}}}}}\ \text{{mm}}^2$ | **Provided:** $\mathbf{{{total_As:.1f}}}\ \text{{mm}}^2$")
        if total_As >= as_final_req:
            st.success(rf"✅ $A_{{s,prov}}$ ({total_As:.1f} mm²) ≥ Required ({as_final_req:.1f} mm²)")
        else:
            st.error(rf"❌ $A_{{s,prov}}$ ({total_As:.1f} mm²) < Required ({as_final_req:.1f} mm²) — Increase reinforcement!")

        # Strain Compatibility
        st.markdown("**3. Strain Compatibility & Stress Block**")
        phiMn, As_t, a_val, Mn_val, c_val, eps_t, layer_res = get_phi_Mn_details_multi(
            all_bot_layers, all_top_layers, b, h, fc, fy, cov, stir_db, is_top_tension=is_top
        )
        st.latex(rf"c = {c_val:.2f}\ \text{{mm}}\quad a = \beta_1 c = {beta1:.3f}\times{c_val:.2f} = {a_val:.2f}\ \text{{mm}}")

        if c_val > 0 and a_val > 0:
            try:
                fig_stress = section_plotter.plot_detailed_stress_strain(
                    b=b, h=h, c=c_val, a=a_val, fc=fc, layer_res=layer_res, is_top=is_top
                )
                st.pyplot(fig_stress, use_container_width=True)
            except Exception as e:
                st.error(f"⚠️ Diagram rendering failed: {e}")
        st.divider()

        col_comp, col_tens = st.columns(2)
        with col_comp:
            comp = [ly for ly in layer_res if ly['type'] == 'Compression']
            st.markdown("🔴 **Compression Bars:**")
            if comp:
                st.latex(r"\epsilon_s=0.003\left(\frac{c-d_i}{c}\right)")
                for ly in comp:
                    di, eps_s, fs = ly['d_i'], abs(ly['eps_s']), abs(ly['fs'])
                    status = "🔴 Yielded" if ly['is_yielded'] else "⚪ Elastic"
                    st.markdown(f"- Layer @ $d'_i = {di:.1f}$ mm:")
                    st.latex(rf"\epsilon_s=0.003\times\frac{{{c_val:.2f}-{di:.1f}}}{{{c_val:.2f}}}={eps_s:.5f}")
                    st.latex(rf"f'_s={eps_s:.5f}\times200\,000\to\mathbf{{{fs:.1f}}}\ \text{{MPa}}\ \text{{({status})}}")
            else:
                st.info("Singly Reinforced")

        with col_tens:
            tens = [ly for ly in layer_res if ly['type'] == 'Tension']
            st.markdown("🟢 **Tension Bars:**")
            if tens:
                st.latex(r"\epsilon_s=0.003\left(\frac{d_i-c}{c}\right)")
                for ly in tens:
                    di, eps_s, fs = ly['d_i'], ly['eps_s'], ly['fs']
                    status = "🟢 Yielded" if ly['is_yielded'] else "🟡 Elastic"
                    st.markdown(f"- Layer @ $d_i = {di:.1f}$ mm:")
                    st.latex(rf"\epsilon_s=0.003\times\frac{{{di:.1f}-{c_val:.2f}}}{{{c_val:.2f}}}={eps_s:.5f}")
                    st.latex(rf"f_s={eps_s:.5f}\times200\,000\to\mathbf{{{fs:.1f}}}\ \text{{MPa}}\ \text{{({status})}}")
            else:
                st.warning("No tension bars")

        # Final capacity
        st.markdown("**4. Ultimate Capacity ($\\phi M_n$)**")
        if eps_t >= 0.005:    phi_f, state = 0.90, "Tension-Controlled"
        elif eps_t <= 0.002:  phi_f, state = 0.65, "Compression-Controlled"
        else:
            phi_f = 0.65 + 0.25 * (eps_t - 0.002) / 0.003
            state = "Transition Zone"
        st.latex(rf"\epsilon_t=\mathbf{{{eps_t:.5f}}}\implies\phi={phi_f:.3f}\ \text{{({state})}}")

        Cc_kN   = 0.85 * fc * a_val * b / 1000
        M_conc  = Cc_kN * (a_val / 2) / 1000
        st.latex(rf"M_{{concrete}}=C_c\times\frac{{a}}{{2}}={Cc_kN:.1f}\times\frac{{{a_val:.1f}}}{{2}}\times10^{{-3}}={M_conc:.2f}\ \text{{kNm}}")

        sum_M_steel = 0.0
        for ly in layer_res:
            F_kN  = ly['area'] * ly['fs'] / 1000
            arm_m = ly['d_i'] / 1000
            M_lay = F_kN * arm_m
            sum_M_steel += M_lay
            if abs(F_kN) > 0.1:
                st.latex(rf"M_{{s,{ly['layer_idx']}}}={F_kN:.1f}\times{arm_m:.3f}={M_lay:.2f}\ \text{{kNm}}")

        st.latex(rf"M_{{n}}=M_{{concrete}}+\sum M_s={M_conc:.2f}+{sum_M_steel:.2f}=\mathbf{{{Mn_val:.2f}}}\ \text{{kNm}}")
        st.latex(rf"\phi M_n={phi_f:.3f}\times{Mn_val:.2f}=\mathbf{{{phiMn:.2f}}}\ \text{{kNm}}")

        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("Demand $M_u$",   f"{abs(Mu):.2f} kNm")
        mc2.metric("Capacity $\\phi M_n$", f"{phiMn:.2f} kNm", delta=f"{phiMn - abs(Mu):.2f} kNm")
        if phiMn >= abs(Mu) and eps_t >= 0.004:
            mc3.success("✅ PASS")
        elif eps_t < 0.004:
            mc3.error("❌ FAIL (ε_t < 0.004 — Code Violation)")
        else:
            mc3.error("❌ FAIL (Insufficient Capacity)")

        return d_eff, dt_approx

    # ── 2. Flexural Audits ───────────────────────────────────────────────────
    with st.expander("📉 2.1 NEGATIVE MOMENT — Top Steel", expanded=False):
        render_flexural_audit(Mu_neg, bot_layers, top_layers, is_top=True)

    with st.expander("📈 2.2 POSITIVE MOMENT — Bottom Steel", expanded=True):
        d_eff_bot, _ = render_flexural_audit(Mu_pos, bot_layers, top_layers, is_top=False)

    # ── 3. Shear ─────────────────────────────────────────────────────────────
    with st.expander("✂️ 3. Shear Strength — ACI 22.5", expanded=False):
        d_shear = d_eff_bot if d_eff_bot > 0 else (h - cov - stir_db - 8)
        st.latex(rf"V_u = {abs(Vu):.2f}\ \text{{kN}}")
        Vc   = (0.17 * np.sqrt(fc) * b * d_shear) / 1000
        Av   = 2 * np.pi * (stir_db / 2) ** 2
        s_ok = max(float(stir_s), 1.0)
        Vs   = (Av * fy * d_shear / s_ok) / 1000
        phiVn = 0.75 * (Vc + Vs)
        st.latex(rf"A_v=2\times\frac{{\pi d_b^2}}{{4}}=2\times\frac{{\pi({stir_db})^2}}{{4}}={Av:.1f}\ \text{{mm}}^2")
        st.latex(rf"V_c=0.17\sqrt{{f'_c}}\,b_w d={0.17*np.sqrt(fc):.4f}\times{b:.0f}\times{d_shear:.1f}\times10^{{-3}}={Vc:.2f}\ \text{{kN}}")
        st.latex(rf"V_s=\frac{{A_v f_{{yt}} d}}{{s}}=\frac{{{Av:.1f}\times{fy:.1f}\times{d_shear:.1f}}}{{{s_ok:.0f}}}\times10^{{-3}}={Vs:.2f}\ \text{{kN}}")
        st.latex(rf"\phi V_n=0.75(V_c+V_s)=0.75({Vc:.2f}+{Vs:.2f})=\mathbf{{{phiVn:.2f}}}\ \text{{kN}}")
        s_max = min(d_shear / 2, 600)
        sc1, sc2 = st.columns(2)
        sc1.metric("$V_u$",       f"{abs(Vu):.2f} kN")
        sc2.metric("$\\phi V_n$", f"{phiVn:.2f} kN", delta=f"{phiVn - abs(Vu):.2f} kN")
        st.markdown(rf"**$s_{{max}}$** = min(d/2, 600) = {s_max:.0f} mm")
        if s_ok <= s_max and phiVn >= abs(Vu):
            st.success(f"✅ Shear PASS | s={s_ok:.0f} mm ≤ s_max={s_max:.0f} mm")
        else:
            st.error("❌ Shear FAIL — Check capacity or spacing")

    # ── 4. Serviceability ────────────────────────────────────────────────────
    with st.expander("🔎 4. Serviceability — ACI 24.2", expanded=False):
        st.markdown("#### 4.1 Deflection Control")
        L_mm = L_m * 1000
        def_opts = {
            "L/180 — Flat roofs (no fragile finish)": 180,
            "L/240 — Floors/roofs (non-fragile finish)": 240,
            "L/360 — Floors (no fragile partitions)": 360,
            "L/480 — Floors with fragile partitions": 480,
        }
        sel = st.selectbox("Allowable Deflection Limit:", list(def_opts.keys()), index=1)
        denom_d  = def_opts[sel]
        allow_d  = L_mm / denom_d
        st.latex(rf"\Delta_{{allow}}=\frac{{L}}{{{denom_d}}}=\frac{{{L_mm:.0f}}}{{{denom_d}}}={allow_d:.2f}\ \text{{mm}}")
        st.latex(rf"\Delta_{{actual}}=\mathbf{{{abs(delta_svc):.3f}}}\ \text{{mm}}")
        if abs(delta_svc) <= allow_d:
            st.success("✅ Deflection PASS")
        else:
            st.warning("⚠️ Deflection FAIL — Increase section stiffness")

        st.divider()
        st.markdown("#### 4.2 Crack Width (Gergely-Lutz)")
        valid_bot = [ly for ly in bot_layers if ly.get('n', 0) > 0 and ly.get('db', 0) > 0]
        if valid_bot:
            crack_data = res.get('crack', {})
            w_lim   = crack_data.get('limit', 0.4)
            bot_db1 = valid_bot[0]['db']
            dc      = cov + stir_db + bot_db1 / 2
            fs_svc  = fy * 0.6
            n_bot   = sum(ly['n'] for ly in valid_bot)
            A_eff   = (2 * dc * b) / n_bot if n_bot > 0 else 0
            w_val   = 11e-6 * 1.2 * fs_svc * np.cbrt(dc * A_eff)
            st.latex(rf"w = 11\times10^{{-6}}\,\beta\,f_s\,\sqrt[3]{{d_c A}}")
            st.latex(rf"w \approx 11\times10^{{-6}}(1.2)({fs_svc:.0f})\,\sqrt[3]{{{dc:.1f}\times{A_eff:.1f}}} = \mathbf{{{w_val:.3f}}}\ \text{{mm}}")
            if w_val <= w_lim:
                st.success(rf"✅ Crack width OK ({w_val:.3f} ≤ {w_lim} mm)")
            else:
                st.error(rf"⚠️ Crack width {w_val:.3f} > limit {w_lim} mm — Use smaller bars")
        else:
            st.info("No bottom reinforcement data.")

    st.divider()
    st.caption("Generated by Pro RC Beam Design | ACI 318-19 Compliant — Rigorous Strain Compatibility")

    # Print / Export button
    st.write("")
    components.html(
        """
        <style>
        .print-btn {
            background: #ff4b4b; color: white; padding: 10px 20px;
            border: none; border-radius: 8px; cursor: pointer;
            font-size: 15px; font-weight: bold;
            box-shadow: 0 4px 6px rgba(0,0,0,.1); transition: .2s;
        }
        .print-btn:hover { background: #e03030; }
        </style>
        <div style="text-align:right;">
            <button class="print-btn" onclick="window.parent.print()">🖨️ Save as PDF / Print</button>
        </div>
        """,
        height=60,
    )
