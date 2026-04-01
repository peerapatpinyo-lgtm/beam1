# rc_design_engine.py
import numpy as np
from rc_utils import get_beta1

def get_centroid_and_d(layers, h, cover, stir_db):
    """
    คำนวณจุดศูนย์ถ่วงของกลุ่มเหล็กเสริม (Centroid) และ Effective Depth (d)
    layers: list ของ dict เช่น [{'n': 3, 'db': 20}, {'n': 2, 'db': 20}]
    """
    if not layers:
        return 0.0, 0.0, 0.0
    
    total_area = 0.0
    sum_ay = 0.0
    vertical_spacing = 25.0 
    
    current_y_from_bottom = cover + stir_db
    
    for layer in layers:
        n = layer['n']
        db = layer['db']
        if n <= 0: continue
        
        area = n * (np.pi * (db/2)**2)
        y_center = current_y_from_bottom + (db/2)
        
        total_area += area
        sum_ay += (area * y_center)
        
        current_y_from_bottom += db + vertical_spacing
        
    if total_area == 0:
        return 0.0, 0.0, 0.0
        
    y_bar = sum_ay / total_area 
    d_eff = h - y_bar
    
    return float(d_eff), float(total_area), float(y_bar)

def get_as_req(Mu_kNm, d_eff_mm, fc, fy, b_mm):
    """
    Calculate Required Steel Area based on ACI 318
    """
    if Mu_kNm == 0 or d_eff_mm <= 0: 
        return 0.0, 0.0, False, {}
        
    Mu = abs(Mu_kNm) * 1e6 
    phi = 0.9 
    
    Rn = Mu / (phi * b_mm * d_eff_mm**2)
    term_inside = 1 - (2 * Rn) / (0.85 * fc)
    
    if term_inside < 0:
        return 0.0, 0.0, True, {} 

    rho = (0.85 * fc / fy) * (1 - np.sqrt(term_inside))
    as_req_calc = rho * b_mm * d_eff_mm
    
    as_min = max((0.25 * np.sqrt(fc) / fy) * b_mm * d_eff_mm, (1.4 / fy) * b_mm * d_eff_mm)
    
    # คำนวณค่าเพิ่มเติมสำหรับทำรายการคำนวณ (Report)
    rho_min = as_min / (b_mm * d_eff_mm)
    beta1 = get_beta1(fc)
    rho_max = (0.85 * fc * beta1 / fy) * (0.003 / (0.003 + 0.005))
    
    as_final = max(as_req_calc, as_min)
    
    details = {
        "Mu": Mu,
        "phi": phi,
        "Rn": Rn,
        "rho_req": rho,
        "rho_min": rho_min,
        "rho_max": rho_max,
        "as_req_calc": as_req_calc,
        "as_min": as_min,
        "as_final": as_final
    }
    
    return float(as_final), float(rho), False, details

def get_phi_Mn_details_multi(bot_layers, top_layers, b, h, fc, fy, cover, stir_db):
    """
    [UPGRADED] คำนวณ Moment Capacity (Phi Mn) เชิงลึก 
    รองรับ: เหล็กหลายชั้น (Multiple Layers), คานเสริมเหล็กคู่ (Doubly Reinforced), 
    ตรวจสอบการครากเหล็กอัด (Yield Check) และใช้ dt ในการหาค่า Phi
    """
    Es = 200000.0
    eps_cu = 0.003
    eps_y = fy / Es
    beta1 = get_beta1(fc)

    # 1. คำนวณฝั่งเหล็กรับแรงดึง (Tension Steel)
    As = 0.0
    sum_ay_bot = 0.0
    current_y_bot = cover + stir_db
    dt = 0.0 # ความลึกเหล็กชั้นนอกสุด
    
    for i, layer in enumerate(bot_layers):
        n = layer.get('n', 0)
        db = layer.get('db', 0)
        if n <= 0: continue
        
        area = n * (np.pi * (db/2)**2)
        y_center = current_y_bot + (db/2)
        
        if i == 0:
            dt = h - y_center # เหล็กชั้นล่างสุด (ไกลสุดจากขอบบน)
            
        As += area
        sum_ay_bot += (area * y_center)
        current_y_bot += db + 25.0 

    if As == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    y_bar_bot = sum_ay_bot / As
    d = h - y_bar_bot 

    # 2. คำนวณฝั่งเหล็กรับแรงอัด (Compression Steel)
    As_prime = 0.0
    sum_ay_top = 0.0
    current_y_top = cover + stir_db
    
    if top_layers:
        for layer in top_layers:
            n = layer.get('n', 0)
            db = layer.get('db', 0)
            if n <= 0: continue
            
            area = n * (np.pi * (db/2)**2)
            y_center = current_y_top + (db/2)
            
            As_prime += area
            sum_ay_top += (area * y_center)
            current_y_top += db + 25.0

    d_prime = sum_ay_top / As_prime if As_prime > 0 else 0.0

    # 3. คำนวณแกนสะเทิน (c) และตรวจสอบการคราก
    if As_prime == 0:
        a = (As * fy) / (0.85 * fc * b)
        c = a / beta1
        fs_prime = 0.0
    else:
        a_assume = ((As - As_prime) * fy) / (0.85 * fc * b)
        if a_assume <= 0: a_assume = 0.001 
        
        c_assume = a_assume / beta1
        eps_s_prime = eps_cu * (c_assume - d_prime) / c_assume if c_assume > 0 else 0

        if eps_s_prime >= eps_y:
            c = c_assume
            a = a_assume
            fs_prime = fy
        else:
            A_quad = 0.85 * fc * beta1 * b
            B_quad = eps_cu * Es * As_prime - As * fy
            C_quad = -eps_cu * Es * As_prime * d_prime
            
            discriminant = B_quad**2 - 4 * A_quad * C_quad
            
            if discriminant >= 0:
                c = (-B_quad + np.sqrt(discriminant)) / (2 * A_quad)
            else:
                c = 0.001
                
            a = beta1 * c
            fs_prime = Es * eps_cu * (c - d_prime) / c if c > 0 else 0.0

    if c <= 0:
        return 0.0, float(As), 0.0, 0.0, 0.0, 0.0

    # 4. คำนวณกำลังต้านทานโมเมนต์ (Mn)
    Cc = 0.85 * fc * a * b
    Cs = As_prime * fs_prime
    
    Mn_Nmm = Cc * (d - a/2) + Cs * (d - d_prime)
    Mn_kNm = Mn_Nmm / 1e6

    # 5. หาตัวคูณลดกำลัง Phi (โดยใช้ dt ของชั้นนอกสุด)
    if dt == 0: dt = d 
    
    eps_t = eps_cu * (dt - c) / c if c > 0 else 999.0

    if eps_t >= 0.005:
        phi = 0.90
    elif eps_t <= 0.002:
        phi = 0.65
    else:
        phi = 0.65 + 0.25 * ((eps_t - 0.002) / 0.003)

    phi_Mn = phi * Mn_kNm

    return float(phi_Mn), float(As), float(a), float(Mn_kNm), float(c), float(eps_t)

def check_shear_details(Vu_kN, b, d, fc, fy, stir_db, spacing):
    """
    Check Shear Capacity
    """
    if d <= 0: 
        return "FAIL (Invalid d)", 0.0, 0.0, 0.0, 0.0, 0.0
    
    Vu = abs(Vu_kN) * 1000 
    phi = 0.75 
    
    Vc = 0.17 * np.sqrt(fc) * b * d
    phi_Vc = phi * Vc
    
    Av = 2 * (np.pi * (stir_db/2)**2)
    s = max(spacing, 1.0)
    Vs = (Av * fy * d) / s
    phi_Vs = phi * Vs
    
    phi_Vn = (phi_Vc + phi_Vs) / 1000 
    
    is_ok = (phi_Vn * 1000) >= Vu
    
    if not is_ok:
        status = f"FAIL (Vu={abs(Vu_kN):.1f} > φVn={phi_Vn:.1f} kN)"
    else:
        status = "OK"

    return status, float(phi_Vn), float(phi_Vc/1000), float(phi_Vs/1000), float(Vc), float(Vs)

def check_serviceability(Ma_kNm, delta_elastic_mm, b, h, d_eff, Ast_bot, Ast_top, fc, Es=200000):
    """
    คำนวณ Long-term Deflection ตาม ACI 318-19 (Bischoff's Formula)
    Must return: (delta_immediate, delta_longterm, Ie, Icr, lambda_delta)
    """
    if Ma_kNm == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    Ma = abs(Ma_kNm) * 1e6 # N-mm
    Ec = 4700 * np.sqrt(fc) # MPa
    n = Es / Ec # Modular Ratio
    
    # 1. Calculate Gross Inertia (Ig)
    Ig = (b * h**3) / 12
    yt = h / 2
    
    # 2. Calculate Cracking Moment (Mcr) - ACI Eq. 24.2.3.5
    fr = 0.62 * np.sqrt(fc) # Modulus of Rupture
    Mcr = (fr * Ig) / yt
    
    # 3. Calculate Cracked Inertia (Icr) using Transformed Section
    rho = Ast_bot / (b * d_eff)
    k = np.sqrt(2*rho*n + (rho*n)**2) - (rho*n)
    kd = k * d_eff
    
    Icr = (b * kd**3) / 3 + n * Ast_bot * (d_eff - kd)**2
    
    # 4. Calculate Effective Inertia (Ie) - ACI 318-19 (Bischoff's Formula) Eq. 24.2.3.5b
    limit_Mcr = (2/3) * Mcr
    
    if Ma <= limit_Mcr:
        Ie = Ig
    else:
        term = (limit_Mcr / Ma)**2
        denom = 1 - term * (1 - (Icr / Ig))
        Ie = Icr / denom
        
    Ie = min(Ie, Ig)
    
    # 5. Calculate Immediate Deflection (Adjusted for Stiffness)
    delta_immediate = delta_elastic_mm * (Ig / Ie)
    
    # 6. Long-term Deflection Multiplier (ACI Table 24.2.4.1.3)
    xi = 2.0
    rho_prime = Ast_top / (b * d_eff) if d_eff > 0 else 0
    lambda_delta = xi / (1 + 50 * rho_prime)
    
    delta_longterm = delta_immediate + (lambda_delta * delta_immediate)
    
    return float(delta_immediate), float(delta_longterm), float(Ie), float(Icr), float(lambda_delta)

def check_crack_width(Ma_svc, b, h, d, As, n_bars, fc, Es=200000):
    """
    Calculate Crack Width using Gergely-Lutz Equation.
    w = 0.076 * beta * fs * cbrt(dc * A) (Imperial base converted to SI)
    """
    if Ma_svc <= 0 or As <= 0 or n_bars == 0:
        return 0.0, 0.0

    # 1. Calculate Modular Ratio (n) & Neutral Axis (k)
    Ec = 4700 * np.sqrt(fc)
    n = Es / Ec
    rho = As / (b * d)
    k = np.sqrt((rho * n)**2 + 2 * rho * n) - (rho * n)
    j = 1 - k/3
    
    # 2. Calculate Steel Stress (fs) at Service Load
    fs = (Ma_svc * 1e6) / (As * j * d) # MPa
    
    # 3. Geometric Parameters for Gergely-Lutz
    x = k * d
    
    dc = h - d 
    if dc < 0: dc = 40 # Fallback
    
    beta = (h - x) / (d - x)
    A_eff = (2 * dc * b) / n_bars
    
    # 4. Calculation (Convert to Imperial for Formula, then back to mm)
    fs_ksi = fs / 6.895        # MPa -> ksi
    dc_in = dc / 25.4          # mm -> inch
    A_in = A_eff / 645.16      # mm2 -> inch2
    
    w_thou = 0.076 * beta * fs_ksi * (dc_in * A_in)**(1/3)
    w_mm = (w_thou / 1000) * 25.4
    
    return w_mm, fs

def arrange_bars_into_layers(total_n, db, b, cover, stir_db):
    """
    คำนวณและจัดเรียงเหล็กเป็นชั้นๆ ตามข้อกำหนดระยะห่างของ ACI Code
    """
    if total_n <= 0:
        return []
        
    inner_w = b - (2 * cover) - (2 * stir_db)
    min_spacing = max(25.0, db) # ACI: ระยะห่างช่องไฟขั้นต่ำ 25 mm หรือเท่ากับ db
    
    max_per_layer = int((inner_w + min_spacing) // (db + min_spacing))
    if max_per_layer < 2: 
        max_per_layer = 2 
        
    layers = []
    rem = int(total_n)
    while rem > 0:
        take = min(rem, max_per_layer)
        layers.append({'n': take, 'db': db})
        rem -= take
    return layers

def design_flexure_auto(Mu_kNm, b, h, cover, stir_db, main_db, fc, fy):
    """
    ระบบคำนวณเหล็กอัตโนมัติ: หา As -> จัดชั้น -> คำนวณ d จริง -> วนลูปเช็คซ้ำ
    Returns: layers, d_actual, as_req, as_prov, status, details
    """
    if Mu_kNm == 0:
        return [], float(h - cover - stir_db - (main_db/2)), 0.0, 0.0, "OK", {}
        
    # 1. สมมติฐานแรกลองให้เหล็กเรียงชั้นเดียวก่อน
    d_assume = h - cover - stir_db - (main_db / 2)
    as_req, _, is_over_max, details = get_as_req(Mu_kNm, d_assume, fc, fy, b)
    
    if is_over_max:
        return [], float(d_assume), float(as_req), 0.0, "FAIL (Section too small/Need Compression Steel)", details
        
    a_bar = np.pi * (main_db / 2)**2
    n_bars = int(np.ceil(as_req / a_bar))
    if n_bars < 2: n_bars = 2 
    
    # 2. เข้าลูปคำนวณ
    max_iter = 5
    for _ in range(max_iter):
        layers = arrange_bars_into_layers(n_bars, main_db, b, cover, stir_db)
        d_actual, as_prov, y_bar = get_centroid_and_d(layers, h, cover, stir_db)
        as_req_new, _, _, details_new = get_as_req(Mu_kNm, d_actual, fc, fy, b)
        
        if as_prov >= as_req_new:
            details = details_new 
            break 
        else:
            n_bars += 1 
            
    return layers, float(d_actual), float(as_req_new), float(as_prov), "OK", details
