import pandas as pd
import numpy as np

def prepare_load_dataframe(user_loads_df, n_spans, spans, params, f_dl=1.4, f_ll=1.7):
    """
    Processor สำหรับจัดการ Load:
    หน้าที่:
    1. รับ Load รวม (User Input + Self-weight) ซึ่งตอนนี้เป็นหน่วย kN มาจาก app.py แล้ว 100%
    2. คูณ Load Factor (1.4 สำหรับ DL/SW, 1.7 สำหรับ LL)
    3. จัด Format ให้ตรงกับที่ Solver ต้องการ (ส่งต่อเป็น kN)
    """
    
    # กรณีไม่มีข้อมูล Load เลย ให้ส่งตารางว่างกลับไป
    if user_loads_df is None or user_loads_df.empty:
        return pd.DataFrame(columns=['span_index', 'type', 'mag', 'dist', 'd_start'])

    processed_loads = []

    # วนลูปจัดการ Load ทีละรายการ
    for _, load in user_loads_df.iterrows():
        
        # 1. เช็คประเภท Load เพื่อระบุ Factor
        case_type = load.get('case', 'DL') 
        
        if case_type in ['DL', 'SW', 'Dead', 'Superimposed Dead']:
            factor = f_dl  # Dead Load / Self-weight (ปกติ 1.4)
        elif case_type in ['LL', 'Live']:
            factor = f_ll  # Live Load (ปกติ 1.7)
        else:
            factor = 1.0   # กรณีอื่นๆ

        # 2. ดึงค่า Load (ตอนนี้เรารับมาเป็น kN แน่นอน ไม่ต้องหาร 1000 แล้ว)
        raw_mag_kN = float(load['mag'])

        # 3. คูณ Factor (Ultimate/Service Load) ในหน่วย kN
        factored_mag_kN = raw_mag_kN * factor

        # 4. เตรียมข้อมูลลง List
        processed_loads.append({
            'span_index': int(load['span_index']),
            'type': load['type'],                       
            'mag': factored_mag_kN,  # ส่งเป็น kN เข้า Solver ตรงๆ
            'dist': float(load.get('dist', 0)),         
            'd_start': float(load.get('d_start', 0)),   
            'case_origin': case_type                    
        })

    # ส่งค่ากลับเป็น DataFrame ใหม่สำหรับเข้า Solver
    return pd.DataFrame(processed_loads)
