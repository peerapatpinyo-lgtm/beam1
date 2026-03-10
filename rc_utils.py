# rc_utils.py
import numpy as np

def normalize_section_units(b_input, h_input):
    """
    ตรวจสอบและแปลงหน่วยอัตโนมัติ (Meters -> Millimeters)
    ถ้าค่าที่ใส่มาน้อยกว่า 10 สันนิษฐานว่าเป็นเมตร และคูณ 1000
    """
    # จัดการความกว้าง (b)
    if b_input < 10:
        b_mm = b_input * 1000
    else:
        b_mm = b_input
        
    # จัดการความลึก (h)
    if h_input < 10:
        h_mm = h_input * 1000
    else:
        h_mm = h_input
        
    return b_mm, h_mm

def get_beta1(fc):
    """
    Calculate Beta1 factor according to ACI 318 (Metric)
    """
    if fc <= 28: # ACI uses 28 MPa as the threshold
        return 0.85
    elif fc >= 55:
        return 0.65
    else:
        return 0.85 - 0.05 * (fc - 28) / 7
