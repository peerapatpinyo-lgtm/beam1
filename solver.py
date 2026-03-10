import numpy as np
import pandas as pd

def solve_beam(spans, sup_df, loads_df, params):
    """
    Solves the continuous beam using Direct Stiffness Method (FEM).
    Theory: Timoshenko Beam (includes Shear Deformation).
    *** Standard Units Used: Force = kN, Length = m ***
    """
    # --- 0.1 Safety Check for Empty Loads ---
    if loads_df.empty or 'span_index' not in loads_df.columns:
        loads_df = pd.DataFrame(columns=['span_index', 'type', 'mag', 'dist', 'd_start'])

    # --- 0.2 Parameter Calculation & Defaults ---
    # 1. จัดการหน่วยหน้าตัด (b, h) ให้อยู่ในหน่วย "เมตร (m)" เสมอ
    b_raw = params.get('b', 300)
    h_raw = params.get('h', 500)
    b = b_raw / 1000.0 if b_raw >= 10 else b_raw
    h = h_raw / 1000.0 if h_raw >= 10 else h_raw

    # 2. คำนวณค่า E (Modulus of Elasticity) ให้อยู่ในหน่วย "kPa (kN/m²)"
    if 'fc' in params:
        # ใช้สูตร ACI: E = 4700 * sqrt(fc') MPa 
        # 1 ksc = 0.0980665 MPa
        fc_mpa = params['fc'] * 0.0980665
        E = 4700 * np.sqrt(fc_mpa) * 1e3  # คูณ 1e3 แปลง MPa เป็น kPa (kN/m²)
    else:
        E = params.get('E', 25e6) # Default 25e6 kPa (25 GPa)
        if E > 1e8:  # ถ้าเผลอรับค่ามาเป็น Pa ให้ปรับเป็น kPa
            E = E / 1000.0 
            
    # 3. จัดการค่า I (Moment of Inertia) ให้อยู่ในหน่วย "m⁴"
    if 'I' in params:
        I = params['I']
        if I > 1: # ถ้าเผลอส่ง I มาเป็น mm⁴ ให้แปลงกลับเป็น m⁴
            I = I / 1e12
    else:
        I = (b * h**3) / 12.0

    # --- Timoshenko Parameters ---
    nu = 0.2  
    G = E / (2.0 * (1.0 + nu)) 
    k_factor = 5.0 / 6.0    
    As = k_factor * b * h   
    
    # 1. Setup Nodes & Elements
    n_spans = len(spans)
    n_nodes = n_spans + 1
    node_coords = [0] + list(np.cumsum(spans))
    
    n_dof = 2 * n_nodes
    K_global = np.zeros((n_dof, n_dof))
    F_global = np.zeros(n_dof)
    
    # 2. Build Stiffness Matrix (K) with Timoshenko Factor (Phi)
    for i in range(n_spans):
        L = spans[i]
        Phi = (12 * E * I) / (G * As * L**2)
        const = (E * I) / ((1 + Phi) * L**3)
        
        k11 = 12
        k12 = 6 * L
        k22 = (4 + Phi) * L**2
        k24 = (2 - Phi) * L**2
        
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

    # 3. Process Loads (Fixed End Actions - FEA)
    fea_local = [] 
    for _ in range(n_spans):
        fea_local.append(np.zeros(4)) 

    if not loads_df.empty:
        for _, load in loads_df.iterrows():
            try:
                span_idx = int(load['span_index'])
                if span_idx >= n_spans: continue

                L = spans[span_idx]
                mag = load['mag'] # kN or kN/m
                idx = [2*span_idx, 2*span_idx+1, 2*(span_idx+1), 2*(span_idx+1)+1]
                fea = np.zeros(4)
                
                # --- แก้ไขจุดที่ 1 ---
                l_type = str(load['type']).strip().upper()
                if l_type in ['P', 'POINT', 'POINT LOAD']:
                    P = mag
                    a = float(load['d_start']) 
                    a = max(0.0, min(L, a))
                    b_dist = L - a
                    denom = L**2
                    
                    fea[0] = (P * b_dist**2 * (3*a + b_dist)) / L**3
                    fea[1] = (P * a * b_dist**2) / denom
                    fea[2] = (P * a**2 * (a + 3*b_dist)) / L**3
                    fea[3] = -(P * a**2 * b_dist) / denom
                    
                elif l_type in ['U', 'UNIFORM', 'DISTRIBUTED', 'LINE']:
                    w = mag
                    a = float(load.get('d_start', 0.0))
                    dist_len = float(load.get('dist', L))
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
                        
                        c_dist = b_load - a
                        R2 = (w * c_dist) - R1
                        
                        fea[0] = R1
                        fea[1] = M1
                        fea[2] = R2
                        fea[3] = M2

                fea_local[span_idx] += fea
                
                F_global[idx[0]] -= fea[0]
                F_global[idx[1]] -= fea[1]
                F_global[idx[2]] -= fea[2]
                F_global[idx[3]] -= fea[3]
            except Exception:
                continue

    # 4. Apply Boundary Conditions
    fixed_dofs = []
    for i, row in sup_df.iterrows():
        node_idx = int(row['id']) if 'id' in row else i
        if node_idx >= n_nodes: continue

        fixed_dofs.append(2*node_idx) 
        if row.get('type') == 'Fixed':
            fixed_dofs.append(2*node_idx + 1)
            
    free_dofs = [i for i in range(n_dof) if i not in fixed_dofs]
    
    K_ff = K_global[np.ix_(free_dofs, free_dofs)]
    F_ff = F_global[free_dofs]
    
    try:
        d_free = np.linalg.solve(K_ff, F_ff)
    except np.linalg.LinAlgError:
        return np.zeros(10), np.zeros(10), np.zeros(10), np.zeros(10), {}
    
    d_all = np.zeros(n_dof)
    d_all[free_dofs] = d_free
    
    # 5. Post-Processing
    x_total, moment_total, shear_total, def_total = [], [], [], []
    
    for i in range(n_spans):
        L = spans[i]
        x0 = node_coords[i]
        u_ele = d_all[[2*i, 2*i+1, 2*(i+1), 2*(i+1)+1]]
        
        points = [0.0, L]
        span_loads = loads_df[loads_df['span_index'] == i]
        
        # --- แก้ไขจุดที่ 2 ---
        for _, load in span_loads.iterrows():
            l_type = str(load['type']).strip().upper()
            if l_type in ['P', 'POINT', 'POINT LOAD']:
                p_loc = float(load['d_start'])
                points.extend([max(0, p_loc - 1e-5), p_loc, min(L, p_loc + 1e-5)])
            elif l_type in ['U', 'UNIFORM', 'DISTRIBUTED', 'LINE']:
                s = float(load['d_start'])
                e = s + float(load['dist'])
                points.extend([max(0, s), min(L, e)])
        
        x_dense = np.linspace(0, L, 101)
        x_local = np.sort(np.unique(np.concatenate([x_dense, points])))
        
        # 5.1 Internal Forces
        Phi = (12 * E * I) / (G * As * L**2)
        const = (E * I) / ((1 + Phi) * L**3)
        k_ele_local = const * np.array([
            [12, 6*L, -12, 6*L],
            [6*L, (4+Phi)*L**2, -6*L, (2-Phi)*L**2],
            [-12, -6*L, 12, -6*L],
            [6*L, (2-Phi)*L**2, -6*L, (4+Phi)*L**2]
        ])
        
        f_int = np.dot(k_ele_local, u_ele) + fea_local[i]
        
        V_start = f_int[0]
        M_start_matrix = f_int[1] 
        M_beam_start = -M_start_matrix

        m_x_list, v_x_list = [], []
        
        for x in x_local:
            V_curr = V_start
            M_curr = M_beam_start + V_start * x
            
            # --- แก้ไขจุดที่ 3 ---
            for _, load in span_loads.iterrows():
                mag = load['mag']
                l_type = str(load['type']).strip().upper()
                if l_type in ['P', 'POINT', 'POINT LOAD']:
                    p_loc = float(load['d_start'])
                    if x > p_loc:
                        V_curr -= mag
                        M_curr -= mag * (x - p_loc)
                elif l_type in ['U', 'UNIFORM', 'DISTRIBUTED', 'LINE']:
                    u_start = float(load['d_start'])
                    u_len = float(load['dist'])
                    u_end = u_start + u_len
                    if x > u_start:
                        eff_end = min(x, u_end)
                        eff_len = eff_end - u_start
                        load_force = mag * eff_len
                        centroid_dist = x - (u_start + eff_len/2)
                        V_curr -= load_force
                        M_curr -= load_force * centroid_dist

            m_x_list.append(M_curr)
            v_x_list.append(V_curr)

        # 5.2 Deflection (Double Integration)
        M_arr = np.array(m_x_list)
        V_arr = np.array(v_x_list)
        
        theta_b = np.zeros_like(x_local)
        v_b = np.zeros_like(x_local)
        v_s = np.zeros_like(x_local)
        
        for j in range(1, len(x_local)):
            dx = x_local[j] - x_local[j-1]
            theta_b[j] = theta_b[j-1] + 0.5 * (M_arr[j-1] + M_arr[j]) / (E * I) * dx
            v_b[j] = v_b[j-1] + 0.5 * (theta_b[j-1] + theta_b[j]) * dx
            v_s[j] = v_s[j-1] + 0.5 * (V_arr[j-1] + V_arr[j]) / (G * As) * dx
            
        v_total_int = v_b + v_s
        
        C2 = u_ele[0]
        C1 = (u_ele[2] - v_total_int[-1] - C2) / L if L > 0 else 0
            
        v_def_m = v_total_int + C1 * x_local + C2 # คายค่าเป็นเมตร (m) ไม่ต้องคูณ 1000 แล้ว
        
        x_total.extend(x0 + x_local)
        moment_total.extend(m_x_list)
        shear_total.extend(v_x_list)
        def_total.extend(v_def_m) 

    # 6. Reactions Calculation
    FEA_R = np.zeros(n_dof)
    for i in range(n_spans):
        f = fea_local[i]
        idx = [2*i, 2*i+1, 2*(i+1), 2*(i+1)+1]
        FEA_R[idx[0]] += f[0]
        FEA_R[idx[1]] += f[1]
        FEA_R[idx[2]] += f[2]
        FEA_R[idx[3]] += f[3]
        
    R_final = np.dot(K_global, d_all) + FEA_R
    
    reactions = {}
    for i, row in sup_df.iterrows():
        n_idx = int(row['id']) if 'id' in row else i
        if n_idx < n_nodes:
            reactions[f"R{n_idx}"] = R_final[2*n_idx]

    return np.array(x_total), np.array(moment_total), np.array(shear_total), np.array(def_total), reactions
