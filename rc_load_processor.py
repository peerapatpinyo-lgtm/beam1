# rc_load_processor.py  ── Fixed & Production-Ready Version
import pandas as pd
import numpy as np


def prepare_load_dataframe(user_loads_df, n_spans, spans, params,
                            f_dl=1.4, f_ll=1.7):
    """
    Apply load factors and format for solver.
    FIX: output now includes 'case' column (for FBD coloring) alongside 'case_origin'.
    Units in → kN or kN/m.  Units out → kN or kN/m (factored).
    """
    if user_loads_df is None or user_loads_df.empty:
        return pd.DataFrame(columns=['span_index', 'type', 'mag', 'dist', 'd_start', 'case'])

    processed = []
    for _, load in user_loads_df.iterrows():
        case_type = str(load.get('case', 'DL')).strip().upper()

        if case_type in ['DL', 'SW', 'DEAD', 'SUPERIMPOSED DEAD']:
            factor = f_dl
        elif case_type in ['LL', 'LIVE']:
            factor = f_ll
        else:
            factor = 1.0

        raw_mag_kN     = float(load['mag'])
        factored_mag   = raw_mag_kN * factor

        processed.append({
            'span_index':  int(load['span_index']),
            'type':        str(load['type']),
            'mag':         factored_mag,
            'dist':        float(load.get('dist',    0)),
            'd_start':     float(load.get('d_start', 0)),
            'case':        case_type,        # FIX: include 'case' for FBD coloring
            'case_origin': case_type,
        })

    return pd.DataFrame(processed)
