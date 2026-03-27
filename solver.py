import numpy as np
import pandas as pd
import streamlit as st 

def safe_float(val, default=0.0):
    try:
        if pd.isna(val) or str(val).strip() == '': return default
        return float(val)
    except:
        return default

def solve_beam(spans, sup_df, loads_df, params):
    # --- 0.1 Safety Check ---
    if loads_df is None or loads_df.empty or 'span_index' not in loads_df.columns:
        loads_df = pd.DataFrame(columns=['span_index', 'type', 'mag', 'dist', 'd_start'])
        
    if sup_df is None or sup_df.empty:
        sup_df = pd.DataFrame([{'id': 0, 'type': 'Pinned'}, {'id': len(spans), 'type': 'Pinned'}])


    # --- 0.2 Parameter Calculation ---
    b_raw = safe_float(params.get('b', 300), 300)
    h_raw = safe_float(params.get('h', 500), 500)
    
    # 1. ให้ b และ h เป็นหน่วย เมตร (m) ทั้งหมด
    b = b_raw / 1000.0 if b_raw >= 10 else b_raw
    h = h_raw / 1000.0 if h_raw >= 10 else h_raw

    # 2. คำนวณ I ในหน่วย m^4
    if 'I' in params:
        I = safe_float(params['I'], (b * h**3) / 12.0)
        if I > 1: I = I / 1e12  # ถ้าส่งมาเป็น mm^4 ให้แปลงเป็น m^4
    else:
        I = (b * h**3) / 12.0

    # 3. คำนวณ E ให้ออกมาเป็นหน่วย kN/m^2 (kPa)
    if 'fc' in params:
        # รับค่า fc ที่เป็น MPa มาจาก params โดยตรง (เอาตัวคูณ 0.098... ออก)
        fc_mpa = safe_float(params['fc'])
        
        # E สูตร ACI คือ MPa (N/mm^2)
        # 1 MPa = 1,000 kN/m^2
        E_mpa = 4700 * np.sqrt(fc_mpa) if fc_mpa > 0 else 25000.0
        E = E_mpa * 1000.0  # ตอนนี้ E เป็น kN/m^2 แล้ว!
    else:
        E = safe_float(params.get('E', 25e6), 25e6)
        # สมมติส่งมา 2.5e10 N/m^2 แปลงเป็น kN/m^2
        if E > 1e8: 
            E = E / 1000.0

    nu = 0.2  
    G = E / (2.0 * (1.0 + nu)) 
    k_factor = 5.0 / 6.0    
    As = k_factor * b * h   
    
    n_spans = len(spans)
    n_nodes = n_spans + 1
    node_coords = [0] + list(np.cumsum(spans))
    n_dof = 2 * n_nodes
    K_global = np.zeros((n_dof, n_dof))
    F_global = np.zeros(n_dof)
    
    # 2. Build Stiffness Matrix
    for i in range(n_spans):
        L = safe_float(spans[i], 1.0)
        Phi = (12 * E * I) / (G * As * L**2)
        const = (E * I) / ((1 + Phi) * L**3)
        k11 = 12; k12 = 6 * L; k22 = (4 + Phi) * L**2; k24 = (2 - Phi) * L**2
        k_ele = const * np.array([
            [k11,   k12, -k11,   k12],
            [k12,   k22, -k12,   k24],
            [-k11, -k12,  k11,  -k12],
            [k12,   k24, -k12,   k22]
        ])
        idx = [2*i, 2*i+1, 2*(i+1), 2*(i+1)+1]
        for r in range(4):
            for c in range(4):
                K_global[idx[r], idx[c]] += k_ele[r, c]

    fea_local = [np.zeros(4) for _ in range(n_spans)]
    
    # === ตัวแปรเก็บข้อมูลสำหรับ Debug ===
    dbg_forces = []

    # 3. Process Loads
    for _, load in loads_df.iterrows():
        try:
            span_idx = int(safe_float(load.get('span_index', -1)))
            if span_idx < 0 or span_idx >= n_spans: continue

            L = spans[span_idx]
            mag = safe_float(load.get('mag', 0.0))
            if mag == 0.0: continue 

            idx = [2*span_idx, 2*span_idx+1, 2*(span_idx+1), 2*(span_idx+1)+1]
            fea = np.zeros(4)
            l_type = str(load.get('type', 'P')).strip().upper()
            
            if l_type in ['P', 'POINT', 'POINT LOAD']:
                P = mag
                a = safe_float(load.get('d_start', 0.0))
                a = max(0.0, min(L, a))
                b_dist = L - a
                denom = L**2
                fea[0] = (P * b_dist**2 * (3*a + b_dist)) / L**3
                fea[1] = (P * a * b_dist**2) / denom
                fea[2] = (P * a**2 * (a + 3*b_dist)) / L**3
                fea[3] = -(P * a**2 * b_dist) / denom
                
            elif l_type in ['U', 'UNIFORM', 'DISTRIBUTED', 'LINE']:
                w = mag
                a = safe_float(load.get('d_start', 0.0))
                dist_len = safe_float(load.get('dist', L))
                b_load = a + dist_len
                a = max(0.0, min(L, a))
                b_load = max(0.0, min(L, b_load))
                
                if b_load > a:
                    def int_M1(x): return (L**2 * x**2 / 2) - (2 * L * x**3 / 3) + (x**4 / 4)
                    M1 = (w / L**2) * (int_M1(b_load) - int_M1(a))
                    def int_M2(x): return (L * x**3 / 3) - (x**4 / 4)
                    M2 = -(w / L**2) * (int_M2(b_load) - int_M2(a))
                    def int_R1(x): return (L**3 * x) - (L * x**3) + (x**4 / 2)
                    R1 = (w / L**3) * (int_R1(b_load) - int_R1(a))
                    R2 = (w * (b_load - a)) - R1
                    fea[0] = R1; fea[1] = M1; fea[2] = R2; fea[3] = M2

            fea_local[span_idx] += fea
            F_global[idx[0]] -= fea[0]; F_global[idx[1]] -= fea[1]
            F_global[idx[2]] -= fea[2]; F_global[idx[3]] -= fea[3]
            
            # บันทึกสิ่งที่ Solver มองเห็น
            dbg_forces.append(f"เจอโหลด Type: '{l_type}', ขนาด: {mag:.2f}, สร้างแรง FEA: {np.round(fea, 2)}")
        except Exception as e:
            continue

    fixed_dofs = []
    for i, row in sup_df.iterrows():
        node_idx = int(safe_float(row.get('id', i)))
        if node_idx >= n_nodes: continue
        fixed_dofs.append(2*node_idx) 
        if str(row.get('type', '')).strip().title() == 'Fixed':
            fixed_dofs.append(2*node_idx + 1)
            
    free_dofs = [i for i in range(n_dof) if i not in fixed_dofs]
    K_ff = K_global[np.ix_(free_dofs, free_dofs)]
    F_ff = F_global[free_dofs]
    
    try:
        d_free = np.linalg.solve(K_ff, F_ff)
    except np.linalg.LinAlgError as e:
        dummy_x = np.linspace(0, sum(spans), 10)
        return dummy_x, np.zeros(10), np.zeros(10), np.zeros(10), {"Error": "Support ไม่สมบูรณ์"}
    
    d_all = np.zeros(n_dof)
    d_all[free_dofs] = d_free
    
    # === โชว์เรดาร์ความจริงบนหน้าเว็บ ===
    with st.expander(f"🕵️‍♂️ THE TRUTH ABOUT SOLVER (คลิกเพื่อดูความจริง!)", expanded=True):
        st.write(f"**1. Solver ได้รับตารางโหลดจำนวน:** {len(loads_df)} แถว")
        st.write(f"**2. อาร์เรย์แรงกระทำ (F_global):** {np.round(F_global, 2)}")
        st.write(f"**3. ระยะเคลื่อนตัว (d_free):** {np.round(d_free, 6)}")
        for msg in dbg_forces:
            st.code(msg)
        if np.all(F_global == 0):
            st.error("🚨 F_global เป็น 0 ทั้งหมด! แปลว่าโค้ดเมินโหลดทิ้งไป ไม่ได้ถูกเอามาคำนวณเลย!")

    # 5. Post-Processing
    x_total, moment_total, shear_total, def_total = [], [], [], []
    
    # 🛠️ FIX: เช็คก่อนเลยว่ามีโหลดจริงมั้ย ถ้าไม่มีก็ไม่ต้องเข้าลูปคำนวณให้เปลืองแรง
    has_any_load = not loads_df.empty and (loads_df.get('mag', 0) != 0).any()

    for i in range(n_spans):
        L = spans[i]
        x0 = node_coords[i]
        u_ele = d_all[[2*i, 2*i+1, 2*(i+1), 2*(i+1)+1]]
        
        points = [0.0, L]
        span_loads = loads_df[loads_df['span_index'] == i]
        
        for _, load in span_loads.iterrows():
            mag = safe_float(load.get('mag', 0.0))
            if mag == 0: continue # ข้ามโหลดปลอมๆ
            
            l_type = str(load.get('type', 'P')).strip().upper()
            if l_type in ['P', 'POINT', 'POINT LOAD']:
                p_loc = safe_float(load.get('d_start', 0.0))
                points.extend([max(0, p_loc - 1e-5), p_loc, min(L, p_loc + 1e-5)])
            elif l_type in ['U', 'UNIFORM', 'DISTRIBUTED', 'LINE']:
                s = safe_float(load.get('d_start', 0.0))
                e = s + safe_float(load.get('dist', L))
                points.extend([max(0, s), min(L, e)])
        
        x_dense = np.linspace(0, L, 101)
        x_local = np.sort(np.unique(np.concatenate([x_dense, points])))
        
        Phi = (12 * E * I) / (G * As * L**2)
        const = (E * I) / ((1 + Phi) * L**3)
        k_ele_local = const * np.array([
            [12, 6*L, -12, 6*L],
            [6*L, (4+Phi)*L**2, -6*L, (2-Phi)*L**2],
            [-12, -6*L, 12, -6*L],
            [6*L, (2-Phi)*L**2, -6*L, (4+Phi)*L**2]
        ])
        
        f_int = np.dot(k_ele_local, u_ele) + fea_local[i]
        V_start, M_start_matrix = f_int[0], f_int[1] 
        M_beam_start = -M_start_matrix
        m_x_list, v_x_list = [], []
        
        for x in x_local:
            # 🛠️ FIX: ถ้าไม่มีโหลดกระทำเลยทั้งระบบ บังคับให้เป็น 0 ไปเลย กันการคำนวณคลาดเคลื่อนสะสม
            if not has_any_load:
                V_curr = 0.0
                M_curr = 0.0
            else:
                V_curr = V_start
                M_curr = M_beam_start + V_start * x
                
                for _, load in span_loads.iterrows():
                    mag = safe_float(load.get('mag', 0.0))
                    if mag == 0.0: continue
                    l_type = str(load.get('type', 'P')).strip().upper()
                    
                    if l_type in ['P', 'POINT', 'POINT LOAD']:
                        p_loc = safe_float(load.get('d_start', 0.0))
                        if x > p_loc:
                            V_curr -= mag
                            M_curr -= mag * (x - p_loc)
                    elif l_type in ['U', 'UNIFORM', 'DISTRIBUTED', 'LINE']:
                        u_start = safe_float(load.get('d_start', 0.0))
                        u_len = safe_float(load.get('dist', L))
                        u_end = u_start + u_len
                        if x > u_start:
                            eff_end = min(x, u_end)
                            eff_len = eff_end - u_start
                            load_force = mag * eff_len
                            V_curr -= load_force
                            M_curr -= load_force * (x - (u_start + eff_len/2))

            m_x_list.append(M_curr)
            v_x_list.append(V_curr)

        M_arr, V_arr = np.array(m_x_list), np.array(v_x_list)
        theta_b, v_b, v_s = np.zeros_like(x_local), np.zeros_like(x_local), np.zeros_like(x_local)
        
        for j in range(1, len(x_local)):
            dx = x_local[j] - x_local[j-1]
            theta_b[j] = theta_b[j-1] + 0.5 * (M_arr[j-1] + M_arr[j]) / (E * I) * dx
            v_b[j] = v_b[j-1] + 0.5 * (theta_b[j-1] + theta_b[j]) * dx
            v_s[j] = v_s[j-1] + 0.5 * (V_arr[j-1] + V_arr[j]) / (G * As) * dx
            
        v_total_int = v_b + v_s
        C2 = u_ele[0]
        C1 = (u_ele[2] - v_total_int[-1] - C2) / L if L > 0 else 0
        v_def_m = v_total_int + C1 * x_local + C2 
        
        # 🛠️ FIX: เคลียร์ Deflection เป็น 0 ถ้าระบบไม่มีโหลดเลย
        if not has_any_load:
            v_def_m = np.zeros_like(x_local)

        x_total.extend(x0 + x_local)
        moment_total.extend(m_x_list)
        shear_total.extend(v_x_list)
        def_total.extend(v_def_m) 

    # 6. Reactions Calculation
    FEA_R = np.zeros(n_dof)
    for i in range(n_spans):
        f = fea_local[i]
        idx = [2*i, 2*i+1, 2*(i+1), 2*(i+1)+1]
        FEA_R[idx[0]] += f[0]; FEA_R[idx[1]] += f[1]
        FEA_R[idx[2]] += f[2]; FEA_R[idx[3]] += f[3]
        
    R_final = np.dot(K_global, d_all) + FEA_R
    
    reactions = {}
    for i, row in sup_df.iterrows():
        n_idx = int(safe_float(row.get('id', i)))
        if n_idx < n_nodes:
            # 🛠️ FIX: ถ้าระบบไม่มีโหลดเลย Reaction ต้องเป็น 0
            reactions[f"R{n_idx}"] = 0.0 if not has_any_load else R_final[2*n_idx]

    return np.array(x_total), np.array(moment_total), np.array(shear_total), np.array(def_total), reactions
