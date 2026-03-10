import pandas as pd
import numpy as np

def prepare_load_dataframe(user_loads_df, n_spans, spans, params, f_dl=1.4, f_ll=1.7):
    """
    Processor สำหรับจัดการ Load:
    หน้าที่:
    1. รับ Load รวม (User Input + Self-weight ที่ส่งมาจาก app.py)
    2. แปลงหน่วยให้เป็น N (Newton) ทั้งหมด (ป้องกันการปนกันระหว่าง kN และ N)
    3. คูณ Load Factor (1.4 สำหรับ DL/SW, 1.7 สำหรับ LL)
    4. จัด Format ให้ตรงกับที่ Solver ต้องการ
    """
    
    # กรณีไม่มีข้อมูล Load เลย ให้ส่งตารางว่างกลับไป
    if user_loads_df is None or user_loads_df.empty:
        return pd.DataFrame(columns=['span_index', 'type', 'mag', 'dist', 'd_start'])

    processed_loads = []

    # วนลูปจัดการ Load ทีละรายการ
    for _, load in user_loads_df.iterrows():
        
        # 1. เช็คประเภท Load เพื่อระบุ Factor
        # 'case' จะรับค่ามาจาก app.py ('DL', 'LL', 'SW')
        case_type = load.get('case', 'DL') 
        
        if case_type in ['DL', 'SW', 'Dead', 'Superimposed Dead']:
            factor = f_dl  # Dead Load / Self-weight (ปกติ 1.4)
        elif case_type in ['LL', 'Live']:
            factor = f_ll  # Live Load (ปกติ 1.7)
        else:
            factor = 1.0   # กรณีอื่นๆ

        # 2. จัดการเรื่องหน่วย (Unit Conversion)
        raw_mag = float(load['mag'])
        
        # [Smart Check]
        # Self-weight จาก app.py มักมาเป็นหน่วย N/m (ค่าหลักพัน เช่น 3600)
        # User Input มักกรอกเป็น kN/m (ค่าหลักสิบ เช่น 10, 25)
        # เราใช้เงื่อนไขนี้แยกแยะเพื่อแปลงให้เป็น N ทั้งหมด
        if raw_mag > 500.0:
            # ค่าเยอะ -> สันนิษฐานว่าเป็น N แล้ว (เช่น SW)
            mag_N = raw_mag
        else:
            # ค่าน้อย -> สันนิษฐานว่าเป็น kN -> คูณ 1000 เป็น N
            mag_N = raw_mag * 1000.0

        # 3. คูณ Factor (Ultimate Load)
        factored_mag_N = mag_N * factor

        # 4. เตรียมข้อมูลลง List
        processed_loads.append({
            'span_index': int(load['span_index']),
            'type': load['type'],                       # 'P' หรือ 'U'
            'mag': factored_mag_N,                      # ค่า Load (N) ที่คูณ Factor แล้ว
            'dist': float(load.get('dist', 0)),         # ความยาว Load (ถ้ามี)
            'd_start': float(load.get('d_start', 0)),   # จุดเริ่ม Load
            'case_origin': case_type                    # เก็บไว้ตรวจสอบ
        })

    # ส่งค่ากลับเป็น DataFrame ใหม่สำหรับเข้า Solver
    return pd.DataFrame(processed_loads)
