# rc_design_engine.py
import numpy as np
from rc_utils import get_beta1
import math

def get_centroid_and_d(layers, h_mm, cover_mm, stir_db):
    """
    คำนวณหาพื้นที่เหล็กสะสม (As), ระยะจุดศูนย์ถ่วง (y_bar), และความลึกประสิทธิผล (d)
    รองรับเหล็กหลายชั้น
    """
    total_area = 0.0
    sum_area_y = 0.0
    
    # ระยะห่างช่องว่างระหว่างชั้นเหล็ก (Clear Spacing) มาตรฐาน วสท./ACI มักใช้ 25 mm หรือ ขนาดเหล็กที่ใหญ่กว่า
    clear_spacing = 25.0 
    
    current_y = 0.0
    
    for i, layer in enumerate(layers):
        n = layer.get('n', 0)
        db = layer.get('db', 0)
        
        if n == 0 or db == 0:
            continue
            
        # พื้นที่เหล็กในชั้นนี้
        area = n * (math.pi * (db**2) / 4.0)
        
        # คำนวณระยะ y จากขอบคอนกรีตถึงกึ่งกลางเหล็กชั้นนี้
        if i == 0:
            # ชั้นที่ 1: หุ้มคอนกรีต + ปลอก + ครึ่งนึงของเหล็กแกน
            current_y = cover_mm + stir_db + (db / 2.0)
        else:
            # ชั้นที่ 2 ขึ้นไป: ระยะ y ของชั้นก่อนหน้า + ครึ่งเหล็กชั้นก่อนหน้า + clear spacing + ครึ่งเหล็กชั้นนี้
            prev_db = layers[i-1]['db']
            y_shift = (prev_db / 2.0) + clear_spacing + (db / 2.0)
            current_y += y_shift
            
        total_area += area
        sum_area_y += area * current_y
        
    # ป้องกัน error กรณีไม่มีการใส่เหล็ก
    if total_area == 0:
        return 0.0, 0.0, 0.0
        
    y_bar = sum_area_y / total_area
    d = h_mm - y_bar
    
    return d, total_area, y_bar

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

def get_phi_Mn_details_multi(bot_layers, top_layers, b, h, fc, fy, cover, stir_db, is_top_tension=False):
    """
    [ULTRA-UPGRADED] Strain Compatibility Method (Iterative Bisection)
    วิเคราะห์เหล็กทีละชั้นอย่างละเอียด หาแกนสะเทิน (c) ที่ C = T ตรงตาม ACI 318
    is_top_tension:
      False = โมเมนต์บวก (ล่างดึง-บนอัด) -> เหล็กล่าง=Tension, เหล็กบน=Compression
      True  = โมเมนต์ลบ (บนดึง-ล่างอัด) -> เหล็กบน=Tension, เหล็กล่าง=Compression
    """
    Es = 200000.0
    eps_cu = 0.003
    beta1 = get_beta1(fc)
    
    # 1. จัดกลุ่มเหล็กทั้งหมด (All Bars) ให้อยู่ในระบบพิกัดเดียวกัน
    # ให้ y = 0 เริ่มที่ขอบ "รับแรงอัดสูงสุด" (Compression Face)
    # y = ระยะความลึกจากขอบอัดถึงจุดศูนย์กลางเหล็กเส้น (d_i)
    
    all_bars = []
    
    def add_bars(layers, is_bottom_bars):
        current_spacing = cover + stir_db
        for layer in layers:
            n = layer.get('n', 0)
            db = layer.get('db', 0)
            if n > 0 and db > 0:
                area = n * (np.pi * (db / 2)**2)
                
                if not is_top_tension:
                    # โมเมนต์บวก: ขอบอัดอยู่ด้านบน
                    if is_bottom_bars:
                        y_depth = h - (current_spacing + db/2) # ล่าง=ดึง (ลึกจากขอบบน)
                    else:
                        y_depth = current_spacing + db/2     # บน=อัด (ใกล้ขอบบน)
                else:
                    # โมเมนต์ลบ: ขอบอัดอยู่ด้านล่าง
                    if is_bottom_bars:
                        y_depth = current_spacing + db/2     # ล่าง=อัด (ใกล้ขอบล่าง)
                    else:
                        y_depth = h - (current_spacing + db/2) # บน=ดึง (ลึกจากขอบล่าง)

                all_bars.append({'area': area, 'd_i': y_depth})
                current_spacing += db + 25.0 # สมมติ clear spacing 25mm

    add_bars(bot_layers, is_bottom_bars=True)
    add_bars(top_layers, is_bottom_bars=False)
    
    if not all_bars:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, []

    # หา dt (ความลึกของเหล็กรับแรงดึงชั้นนอกสุด)
    dt = max(bar['d_i'] for bar in all_bars)
    total_tension_As = sum(bar['area'] for bar in all_bars if bar['d_i'] > h/2) # ประมาณการ

    # 2. Bisection Method ค้นหาแกนสะเทิน 'c'
    c_low = 0.001
    c_high = h
    c = 0.001
    tolerance = 1.0 # ยอมให้แรงต่างกันไม่เกิน 1 Newton
    
    for _ in range(100): # วนหา 100 รอบ (เกินพอ)
        c = (c_low + c_high) / 2.0
        a = beta1 * c
        
        # แรงอัดคอนกรีต
        Cc = 0.85 * fc * a * b
        
        # แรงจากเหล็ก (บวก=ดึง, ลบ=อัด)
        Force_s = 0.0
        for bar in all_bars:
            eps_s = eps_cu * (bar['d_i'] - c) / c
            fs = max(-fy, min(fy, eps_s * Es))
            Force_s += bar['area'] * fs
            
        # ตรวจสอบสมดุลแรง
        # แรงรวม = แรงดึงรวม (Force_s ที่เป็นบวก) - แรงอัดคอนกรีต (Cc) + แรงอัดเหล็ก (Force_s ที่เป็นลบ)
        # เนื่องจากเรานิยาม แรงดึง = บวก, แรงอัด = ลบ
        # ดังนั้น Cc ต้องมีเครื่องหมายลบ เพื่อสู้กับแรงดึง
        Net_Force = Force_s - Cc 
        
        if abs(Net_Force) < tolerance:
            break
            
        if Net_Force > 0:
            # แรงดึงชนะแรงอัด -> ต้องเพิ่มพื้นที่แรงอัด -> เลื่อน c ลงมาลึกขึ้น
            c_low = c
        else:
            # แรงอัดชนะแรงดึง -> ต้องลดพื้นที่แรงอัด -> เลื่อน c ขึ้นไป
            c_high = c

    # 3. คำนวณ Moment Capacity (Mn) ที่แท้จริง รอบ Neutral Axis (หรือรอบแกนใดก็ได้)
    # เราจะ Take Moment รอบขอบรับแรงอัดสูงสุด (Top Fiber / Bottom Fiber แล้วแต่กรณี)
    a = beta1 * c
    Cc = 0.85 * fc * a * b
    
    Mn_Nmm = 0.0
    Mn_Nmm += Cc * (a / 2) # โมเมนต์จากคอนกรีต (ทวนเข็ม เป็นบวก)
    
    layer_results = []
    
    for i, bar in enumerate(sorted(all_bars, key=lambda x: x['d_i'])):
        eps_s = eps_cu * (bar['d_i'] - c) / c
        fs = max(-fy, min(fy, eps_s * Es))
        Force = bar['area'] * fs
        
        # โมเมนต์จากเหล็ก (เหล็กดึง fs เป็นบวก, แขนเป็นบวก -> โมเมนต์ทวนเข็ม)
        Mn_Nmm += Force * bar['d_i'] 
        
        layer_results.append({
            'layer_idx': i + 1,
            'd_i': bar['d_i'],
            'area': bar['area'],
            'eps_s': eps_s,
            'fs': fs,
            'is_yielded': abs(fs) >= fy,
            'type': "Tension" if fs > 0 else "Compression"
        })

    Mn_kNm = Mn_Nmm / 1e6
    
    # 4. หาตัวคูณลดกำลัง Phi (ใช้ dt ของเหล็กดึงนอกสุด)
    eps_t = eps_cu * (dt - c) / c if c > 0 else 999.0

    if eps_t >= 0.005:
        phi = 0.90
    elif eps_t <= 0.002:
        phi = 0.65
    else:
        phi = 0.65 + 0.25 * ((eps_t - 0.002) / 0.003)

    phi_Mn = phi * Mn_kNm

    return float(phi_Mn), float(total_tension_As), float(a), float(Mn_kNm), float(c), float(eps_t), layer_results

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
