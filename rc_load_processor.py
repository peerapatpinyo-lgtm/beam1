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
        
        # [New Smart Check]: ปรับให้ทุกอย่างกลายเป็น kN
        if raw_mag > 500.0:
            # ถ้าค่ามาเป็นหลักพัน (เช่น Self-weight 3600 N/m) ให้หาร 1000 เพื่อเป็น kN/m
            mag_kN = raw_mag / 1000.0
        else:
            # ถ้าค่าน้อยๆ (เช่น User กรอก 10, 25) แสดงว่าเป็น kN/m อยู่แล้ว ไม่ต้องทำอะไร
            mag_kN = raw_mag

        # 3. คูณ Factor (Ultimate Load) ในหน่วย kN
        factored_mag_kN = mag_kN * factor

        # 4. เตรียมข้อมูลลง List
        processed_loads.append({
            'span_index': int(load['span_index']),
            'type': load['type'],                       
            'mag': factored_mag_kN,  # <--- แก้เป็น mag_kN (ส่งเป็น kN เข้า Solver)
            'dist': float(load.get('dist', 0)),         
            'd_start': float(load.get('d_start', 0)),   
            'case_origin': case_type                    
        })

    # ส่งค่ากลับเป็น DataFrame ใหม่สำหรับเข้า Solver
    return pd.DataFrame(processed_loads)
