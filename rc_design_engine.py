# rc_design_engine.py  ── Fixed & Production-Ready Version
import numpy as np
from rc_utils import get_beta1
import math


def get_centroid_and_d(layers, h_mm, cover_mm, stir_db):
    """
    คำนวณ As รวม, ระยะจุดศูนย์ถ่วง y_bar, และ d_eff สำหรับเหล็กหลายชั้น
    FIX: filter valid layers ก่อน เพื่อกำจัด bug ชั้นที่มี n=0 ทำให้ y ผิด
    """
    valid_layers = [l for l in layers if l.get('n', 0) > 0 and l.get('db', 0) > 0]
    if not valid_layers:
        return 0.0, 0.0, 0.0

    clear_spacing = 25.0
    total_area    = 0.0
    sum_area_y    = 0.0
    current_y     = cover_mm + stir_db   # ระยะจากขอบ → inner face of stirrup

    for i, layer in enumerate(valid_layers):
        n, db = layer['n'], layer['db']
        area  = n * (math.pi * (db ** 2) / 4.0)

        if i == 0:
            current_y += db / 2.0
        else:
            prev_db    = valid_layers[i - 1]['db']
            current_y += (prev_db / 2.0) + clear_spacing + (db / 2.0)

        total_area += area
        sum_area_y += area * current_y

    y_bar = sum_area_y / total_area
    d     = h_mm - y_bar
    return d, total_area, y_bar


def get_as_req(Mu_kNm, d_eff_mm, fc, fy, b_mm):
    """Required Steel Area — ACI 318-19"""
    if Mu_kNm == 0 or d_eff_mm <= 0:
        return 0.0, 0.0, False, {}

    Mu  = abs(Mu_kNm) * 1e6
    phi = 0.9
    Rn  = Mu / (phi * b_mm * d_eff_mm ** 2)
    term_inside = 1 - (2 * Rn) / (0.85 * fc)

    if term_inside < 0:
        return 0.0, 0.0, True, {}

    rho        = (0.85 * fc / fy) * (1 - np.sqrt(term_inside))
    as_req_calc = rho * b_mm * d_eff_mm
    as_min      = max((0.25 * np.sqrt(fc) / fy) * b_mm * d_eff_mm,
                      (1.4  / fy)              * b_mm * d_eff_mm)
    rho_min    = as_min / (b_mm * d_eff_mm)
    beta1      = get_beta1(fc)
    rho_max    = (0.85 * fc * beta1 / fy) * (0.003 / (0.003 + 0.005))
    as_final   = max(as_req_calc, as_min)

    details = dict(Mu=Mu, phi=phi, Rn=Rn, rho_req=rho,
                   rho_min=rho_min, rho_max=rho_max,
                   as_req_calc=as_req_calc, as_min=as_min, as_final=as_final)
    return float(as_final), float(rho), False, details


def get_phi_Mn_details_multi(bot_layers, top_layers, b, h, fc, fy,
                              cover, stir_db, is_top_tension=False):
    """
    Strain Compatibility Method (Bisection) — ACI 318-19
    is_top_tension=False → positive moment (bottom = tension)
    is_top_tension=True  → negative moment (top = tension)

    FIX: Mn moment formula: Mn = sum(Force_i * d_i) - Cc*(a/2)
         where all d_i measured from compression face.
    """
    Es     = 200000.0
    eps_cu = 0.003
    beta1  = get_beta1(fc)

    all_bars = []

    def add_bars(layers, is_bottom_bars):
        current_spacing = cover + stir_db
        for layer in layers:
            n  = layer.get('n', 0)
            db = layer.get('db', 0)
            if n > 0 and db > 0:
                area = n * (np.pi * (db / 2) ** 2)
                if not is_top_tension:
                    # positive moment — compression face at top
                    if is_bottom_bars:
                        y_depth = h - (current_spacing + db / 2)  # tension
                    else:
                        y_depth = current_spacing + db / 2         # compression
                else:
                    # negative moment — compression face at bottom
                    if is_bottom_bars:
                        y_depth = current_spacing + db / 2         # compression
                    else:
                        y_depth = h - (current_spacing + db / 2)  # tension
                all_bars.append({'area': area, 'd_i': y_depth})
                current_spacing += db + 25.0

    add_bars(bot_layers, is_bottom_bars=True)
    add_bars(top_layers, is_bottom_bars=False)

    if not all_bars:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, []

    dt                = max(bar['d_i'] for bar in all_bars)
    total_tension_As  = sum(bar['area'] for bar in all_bars if bar['d_i'] > h / 2)

    # Bisection — find neutral axis c where Net_Force = 0
    c_low, c_high = 0.001, h
    c = h / 2
    for _ in range(100):
        c  = (c_low + c_high) / 2.0
        a  = beta1 * c
        Cc = 0.85 * fc * a * b
        Force_s = sum(
            bar['area'] * max(-fy, min(fy, Es * eps_cu * (bar['d_i'] - c) / c))
            for bar in all_bars
        )
        Net_Force = Force_s - Cc
        if abs(Net_Force) < 1.0:  # 1 N tolerance
            break
        if Net_Force > 0:
            c_low = c
        else:
            c_high = c

    # Moment about compression face: Mn = sum(Force_i * d_i) - Cc*(a/2)
    a  = beta1 * c
    Cc = 0.85 * fc * a * b

    Mn_Nmm      = -Cc * (a / 2)   # concrete compression (FIX: negative sign)
    layer_results = []

    for idx, bar in enumerate(sorted(all_bars, key=lambda x: x['d_i'])):
        eps_s  = eps_cu * (bar['d_i'] - c) / c
        fs     = max(-fy, min(fy, eps_s * Es))
        Force  = bar['area'] * fs
        Mn_Nmm += Force * bar['d_i']
        layer_results.append({
            'layer_idx': idx + 1,
            'd_i':       bar['d_i'],
            'area':      bar['area'],
            'eps_s':     eps_s,
            'fs':        fs,
            'is_yielded': abs(fs) >= fy,
            'type':      "Tension" if fs > 0 else "Compression"
        })

    Mn_kNm = abs(Mn_Nmm) / 1e6   # abs() for robustness against small numerical sign flip

    # Phi factor (ACI 21.2.2)
    eps_t = eps_cu * (dt - c) / c if c > 0 else 999.0
    if   eps_t >= 0.005: phi = 0.90
    elif eps_t <= 0.002: phi = 0.65
    else:                phi = 0.65 + 0.25 * ((eps_t - 0.002) / 0.003)

    phi_Mn = phi * Mn_kNm
    return float(phi_Mn), float(total_tension_As), float(a), float(Mn_kNm), \
           float(c), float(eps_t), layer_results


def check_shear_details(Vu_kN, b, d, fc, fy, stir_db, spacing):
    """
    Shear Capacity — ACI 318-19 Ch. 22.5
    Added: Vs_max check (ACI 22.5.8.2) and Av_min/s check (ACI 9.6.3.4)
    Returns: (status, phi_Vn, phi_Vc, phi_Vs, Vc, Vs)
    """
    if d <= 0:
        return "FAIL (Invalid d)", 0.0, 0.0, 0.0, 0.0, 0.0

    Vu  = abs(Vu_kN) * 1000   # N
    phi = 0.75

    # Vc (ACI 22.5.5.1, lambda=1.0 normal-weight)
    Vc = 0.17 * np.sqrt(fc) * b * d   # N

    # Stirrup contribution
    Av   = 2 * np.pi * (stir_db / 2) ** 2
    s    = max(float(spacing), 1.0)
    Vs   = (Av * fy * d) / s           # N

    # ACI 22.5.8.2 — Max Vs (section size limit)
    Vs_max = 0.66 * np.sqrt(fc) * b * d   # N
    vs_exceeded = Vs > Vs_max

    # ACI 9.6.3.4 — Minimum stirrup area
    Av_min_s = max(0.062 * np.sqrt(fc) * b / fy,
                   0.35 * b / fy)          # mm²/mm
    av_min_ok = (Av / s) >= Av_min_s

    phi_Vc = phi * Vc
    phi_Vs = phi * min(Vs, Vs_max)         # cap Vs at max
    phi_Vn = (phi_Vc + phi_Vs) / 1000      # kN

    is_ok = (phi_Vn * 1000) >= Vu

    # Build status string
    if vs_exceeded:
        status = f"FAIL (Vs exceeds ACI 22.5.8.2 max — increase section size)"
    elif not av_min_ok:
        status = f"FAIL (Av/s={Av/s:.3f} < Av_min/s={Av_min_s:.3f} — ACI 9.6.3.4)"
    elif not is_ok:
        status = f"FAIL (Vu={abs(Vu_kN):.1f} > φVn={phi_Vn:.1f} kN)"
    else:
        status = "OK"

    return status, float(phi_Vn), float(phi_Vc / 1000), float(phi_Vs / 1000), \
           float(Vc), float(Vs)


def check_serviceability(Ma_kNm, delta_elastic_mm, b, h, d_eff,
                          Ast_bot, Ast_top, fc, Es=200000):
    """
    Long-term Deflection — ACI 318-19 Section 24.2 (Bischoff Formula)
    Returns: (delta_immediate, delta_longterm, Ie, Icr, lambda_delta)
    """
    if Ma_kNm == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    Ma = abs(Ma_kNm) * 1e6   # N·mm
    Ec = 4700 * np.sqrt(fc)   # MPa
    n  = Es / Ec

    Ig = (b * h ** 3) / 12
    yt = h / 2
    fr  = 0.62 * np.sqrt(fc)
    Mcr = (fr * Ig) / yt

    # Cracked transformed section inertia
    if d_eff > 0 and Ast_bot > 0:
        rho = Ast_bot / (b * d_eff)
        k   = np.sqrt(2 * rho * n + (rho * n) ** 2) - (rho * n)
        kd  = k * d_eff
        Icr = (b * kd ** 3) / 3 + n * Ast_bot * (d_eff - kd) ** 2
    else:
        Icr = Ig * 0.35   # fallback estimate

    # Effective inertia (Bischoff, ACI 318-19 Eq. 24.2.3.5b)
    limit_Mcr = (2 / 3) * Mcr
    if Ma <= limit_Mcr:
        Ie = Ig
    else:
        term  = (limit_Mcr / Ma) ** 2
        denom = 1 - term * (1 - Icr / Ig)
        denom = max(denom, 1e-6)   # guard against divide-by-zero
        Ie    = Icr / denom
    Ie = min(Ie, Ig)

    delta_immediate = delta_elastic_mm * (Ig / Ie)

    # Long-term multiplier (ACI Table 24.2.4.1.3, xi=2.0 for ≥5 years)
    xi          = 2.0
    rho_prime   = Ast_top / (b * d_eff) if d_eff > 0 else 0
    lambda_delta = xi / (1 + 50 * rho_prime)
    delta_longterm = delta_immediate * (1 + lambda_delta)

    return (float(delta_immediate), float(delta_longterm),
            float(Ie), float(Icr), float(lambda_delta))


def check_crack_width(Ma_svc, b, h, d, As, n_bars, fc, Es=200000):
    """
    Crack Width — Gergely-Lutz equation (Imperial → SI conversion)
    """
    if Ma_svc <= 0 or As <= 0 or n_bars == 0:
        return 0.0, 0.0

    Ec  = 4700 * np.sqrt(fc)
    n   = Es / Ec
    rho = As / (b * d)
    k   = np.sqrt((rho * n) ** 2 + 2 * rho * n) - (rho * n)
    j   = 1 - k / 3
    fs  = (Ma_svc * 1e6) / (As * j * d)   # MPa

    x    = k * d
    dc   = h - d
    if dc < 0: dc = 40
    beta  = (h - x) / (d - x) if (d - x) > 0 else 1.2
    A_eff = (2 * dc * b) / n_bars

    fs_ksi = fs / 6.895
    dc_in  = dc / 25.4
    A_in   = A_eff / 645.16
    w_thou = 0.076 * beta * fs_ksi * (dc_in * A_in) ** (1 / 3)
    w_mm   = (w_thou / 1000) * 25.4

    return float(max(w_mm, 0.0)), float(fs)


def arrange_bars_into_layers(total_n, db, b, cover, stir_db):
    """จัดเหล็กเป็นชั้นๆ ตาม ACI minimum spacing"""
    if total_n <= 0:
        return []
    inner_w       = b - 2 * cover - 2 * stir_db
    min_spacing   = max(25.0, db)
    max_per_layer = int((inner_w + min_spacing) // (db + min_spacing))
    if max_per_layer < 2:
        max_per_layer = 2
    layers, rem = [], int(total_n)
    while rem > 0:
        take = min(rem, max_per_layer)
        layers.append({'n': take, 'db': db})
        rem -= take
    return layers


def design_flexure_auto(Mu_kNm, b, h, cover, stir_db, main_db, fc, fy):
    """
    Auto-design flexural reinforcement:
    As_req → arrange layers → compute d_actual → iterate until As_prov >= As_req
    """
    if Mu_kNm == 0:
        return [], float(h - cover - stir_db - main_db / 2), 0.0, 0.0, "OK", {}

    d_assume           = h - cover - stir_db - main_db / 2
    as_req, _, over, details = get_as_req(Mu_kNm, d_assume, fc, fy, b)
    if over:
        return [], float(d_assume), float(as_req), 0.0, \
               "FAIL (Section too small — needs compression steel)", details

    a_bar  = np.pi * (main_db / 2) ** 2
    n_bars = max(2, int(np.ceil(as_req / a_bar)))

    for _ in range(10):
        layers              = arrange_bars_into_layers(n_bars, main_db, b, cover, stir_db)
        d_actual, as_prov, _ = get_centroid_and_d(layers, h, cover, stir_db)
        as_req_new, _, _, details_new = get_as_req(Mu_kNm, d_actual, fc, fy, b)
        if as_prov >= as_req_new:
            details = details_new
            break
        n_bars += 1

    return layers, float(d_actual), float(as_req_new), float(as_prov), "OK", details
