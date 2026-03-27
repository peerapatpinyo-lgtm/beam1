import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io
import numpy as np
import textwrap

def auto_arrange_bars(total_n, db, b, cover, stir_db):
    """
    [NEW] คำนวณและจัดเรียงเหล็กเป็นชั้นๆ ตามข้อกำหนดระยะห่างของ ACI Code
    """
    if total_n <= 0:
        return []
        
    inner_w = b - (2 * cover) - (2 * stir_db)
    min_spacing = max(25.0, db) # ระยะห่างช่องไฟขั้นต่ำ 25 mm หรือเท่ากับขนาดเหล็ก
    
    # คำนวณจำนวนเหล็กสูงสุดที่ใส่ได้ใน 1 ชั้น
    max_per_layer = int((inner_w + min_spacing) // (db + min_spacing))
    if max_per_layer < 2: 
        max_per_layer = 2 # อย่างน้อยต้องมีเหล็กมุม 2 เส้น
        
    layers = []
    rem = int(total_n)
    while rem > 0:
        take = min(rem, max_per_layer)
        layers.append({'n': take, 'db': db})
        rem -= take
    return layers

def get_normalized_layers(res, side, b, cover, stir_db):
    """ [NEW] ดึงข้อมูลชั้นเหล็ก ถ้าไม่มีให้คำนวณจัดชั้นอัตโนมัติ """
    layers = res.get(f'{side}_layers')
    if not layers:
        if res.get(side) and 'all_layers' in res[side]:
            layers = res[side]['all_layers']
        else:
            n = int(res.get(f'{side}_n', 0))
            db = float(res.get(f'{side}_db', 12))
            layers = auto_arrange_bars(n, db, b, cover, stir_db)
    return layers

def plot_longitudinal_section_detailed(spans, sup_df, design_res, h_mm, cover_mm):
    """
    วาดรูปตัดยาวคาน พร้อมรายละเอียดเหล็กเสริมและเหล็กปลอก
    """
    spans_mm = [s * 1000 for s in spans]
    total_L = sum(spans_mm)
    v_h = 400  # Visual Height (Fixed for drawing scale)
    fig_w = max(16, total_L / 300)
    fig, ax = plt.subplots(figsize=(fig_w, 5))
    
    # 1. วาดตัวคาน
    beam = patches.Rectangle((0, 0), total_L, v_h, lw=2, ec='black', fc='#fdfdfd', zorder=5)
    ax.add_patch(beam)
    
    # 2. วาด Grid Line
    x_curr = 0
    for i, s_mm in enumerate(spans_mm + [0]):
        ax.plot([x_curr, x_curr], [-650, v_h + 450], color='#bdc3c7', ls='--', lw=1, zorder=1)
        ax.annotate(chr(65+i), xy=(x_curr, v_h + 500), ha='center', va='center',
                    bbox=dict(boxstyle='circle', fc='white', ec='black', lw=1.5), 
                    fontsize=14, fontweight='bold')
        if i < len(spans_mm):
            ax.annotate('', xy=(x_curr, v_h + 250), xytext=(x_curr + s_mm, v_h + 250),
                        arrowprops=dict(arrowstyle='<->', color='#34495e', lw=1.2))
            ax.text(x_curr + s_mm/2, v_h + 300, f"{s_mm/1000:.2f} m", ha='center', fontweight='bold')
            x_curr += s_mm

    # 3. วาด Support
    if not sup_df.empty:
        for _, row in sup_df.iterrows():
            sx = row['x'] * 1000
            stype = str(row.get('type', 'PIN')).upper()
            if stype == 'FIXED':
                ax.add_patch(patches.Rectangle((sx-120, -300), 240, 300, fc='#dfe6e9', ec='black', lw=1.5, hatch='///', zorder=4))
            elif stype == 'ROLLER':
                ax.add_patch(patches.Polygon([[sx, 0], [sx-100, -180], [sx+100, -180]], fc='white', ec='black', lw=1.5, zorder=4))
                ax.add_patch(patches.Circle((sx, -220), 40, fc='black', zorder=4))
            else: # PIN
                ax.add_patch(patches.Polygon([[sx, 0], [sx-100, -200], [sx+100, -200]], fc='#2c3e50', ec='black', lw=1.5, zorder=4))
            ax.text(sx, -450, f"S{row['id']}\n({stype})", ha='center', fontweight='bold', fontsize=9)

    # 4. วาดเหล็กเสริม
    x_curr = 0
    for i, span_L in enumerate(spans_mm):
        res = design_res[i]
        b_mm = float(res.get('b', 200)) # ดึงความกว้างคานมาใช้คำนวณชั้น
        stir_db = float(res.get('stir_db', 9))
        stir_s = res.get('stir_s') or res.get('shear', {}).get('s', 150)
        
        # --- Prepare Layers ---
        top_layers = get_normalized_layers(res, 'top', b_mm, cover_mm, stir_db)
        bot_layers = get_normalized_layers(res, 'bot', b_mm, cover_mm, stir_db)

        # วาดเหล็กบน
        curr_y_top = v_h - (cover_mm + stir_db)
        t_labels = []
        for l_idx, layer in enumerate(top_layers):
            if layer['n'] > 0:
                t_labels.append(f"L{l_idx+1}: {int(layer['n'])}DB{int(layer['db'])}")
                db_size = layer['db']
                
                if l_idx == 0: 
                    x_s, x_e = x_curr, x_curr + span_L
                    ax.plot([x_s, x_e], [curr_y_top, curr_y_top], color='#d30000', lw=2.5, zorder=10)
                else:
                    cut_off = span_L * 0.25 
                    ax.plot([x_curr, x_curr + cut_off], [curr_y_top, curr_y_top], color='#d30000', lw=2.5, zorder=10)
                    ax.plot([x_curr + span_L - cut_off, x_curr + span_L], [curr_y_top, curr_y_top], color='#d30000', lw=2.5, zorder=10)
                
                curr_y_top -= (db_size + 25.0) # ขยับชั้นลงตามความจริง
        
        # วาดเหล็กล่าง
        curr_y_bot = cover_mm + stir_db
        b_labels = [] 
        for l_idx, layer in enumerate(bot_layers):
            if layer['n'] > 0:
                b_labels.append(f"L{l_idx+1}: {int(layer['n'])}DB{int(layer['db'])}")
                db_size = layer['db']
                
                if l_idx == 0: 
                    x_s, x_e = x_curr + 50, x_curr + span_L - 50 
                else:
                    offset = span_L * 0.125
                    x_s, x_e = x_curr + offset, x_curr + span_L - offset
                
                ax.plot([x_s, x_e], [curr_y_bot, curr_y_bot], color='#008c00', lw=2.5, zorder=10)
                curr_y_bot += (db_size + 25.0) # ขยับชั้นขึ้นตามความจริง
        
        mid = x_curr + span_L/2
        
        # Labels
        if t_labels:
            ax.text(mid, v_h + 80, "\n".join(t_labels), color='#d30000', ha='center', va='bottom', fontsize=9, fontweight='bold')
        if b_labels:
            ax.text(mid, -120, "\n".join(reversed(b_labels)), color='#008c00', ha='center', va='top', fontsize=9, fontweight='bold')
        
        # Stirrup Tag
        ax.text(mid, v_h/2, f"STIRRUPS:\nRB{int(stir_db)} @ {stir_s/1000:.2f} m", 
                color='#34495e', ha='center', va='center', fontsize=9, fontweight='bold', 
                bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='#34495e', lw=1, alpha=0.9))
        
        x_curr += span_L

    ax.set_aspect('auto')
    ax.axis('off')
    ax.set_xlim(-500, total_L + 500)
    ax.set_ylim(-800, v_h + 800) 
    
    f_svg = io.StringIO()
    fig.savefig(f_svg, format="svg", bbox_inches='tight', pad_inches=0.1, transparent=True)
    plt.close(fig)
    return f_svg.getvalue(), None

def plot_cross_section(res):
    """
    วาดรูปตัดขวางคาน: แสดงรายละเอียดเหล็ก 2 ชั้นให้ตรงความจริง
    """
    b, h = float(res.get('b', 200)), float(res.get('h', 400))
    cover = float(res.get('cover', 25))
    stir_db = float(res.get('stir_db', 9))
    stir_s = res.get('stir_s') or res.get('shear', {}).get('s') or res.get('s')
    
    # ดึงข้อมูลเหล็กด้วยระบบอัตโนมัติ (ได้เป็นชั้นๆ ชัวร์)
    top_layers = get_normalized_layers(res, 'top', b, cover, stir_db)
    bot_layers = get_normalized_layers(res, 'bot', b, cover, stir_db)
    
    fig, ax = plt.subplots(figsize=(6, 5)) 
    x0, y0 = -b/2, -h/2
    
    # วาดหน้าตัดคอนกรีต
    ax.add_patch(patches.Rectangle((x0, y0), b, h, fc='white', ec='black', lw=2.5, zorder=1))
    s_x, s_y, s_w, s_h = x0+cover, y0+cover, b-2*cover, h-2*cover
    ax.add_patch(patches.Rectangle((s_x, s_y), s_w, s_h, fill=False, ec='#34495e', lw=1.5, zorder=2))
    
    warnings = []
    
    # คำนวณ Smax
    s_max_limit = 0
    if stir_s:
        s_val = float(stir_s)
        d_eff = h - cover - stir_db - 12 
        s_max_limit = min(600, d_eff / 2)
        if s_val > s_max_limit:
            warnings.append(f"Stirrup S={int(s_val)} > Smax={int(s_max_limit)}mm")

    # [NEW] ขอบเขตซ้ายขวาของเหล็กเส้น (เพื่อจัดให้ตรงกันทุกชั้น)
    left_cx = (-b/2) + cover + stir_db
    right_cx = (b/2) - cover - stir_db

    # วาดเหล็กบน
    curr_y_top = (h/2) - cover - stir_db
    for idx, l in enumerate(top_layers):
        n, db = int(l.get('n', 0)), float(l.get('db', 16))
        if n > 0:
            y_p = curr_y_top - (db/2)
            if n > 1:
                x_p = np.linspace(left_cx + (db/2), right_cx - (db/2), n)
            else:
                x_p = [0] # ตรงกลาง

            for x in x_p: 
                ax.add_patch(patches.Circle((x, y_p), db/2, color='#d30000', zorder=10))
            curr_y_top -= (db + 25.0) # ระยะห่างระหว่างชั้น (Clear Spacing 25mm)

    # วาดเหล็กล่าง
    curr_y_bot = (-h/2) + cover + stir_db
    for idx, l in enumerate(bot_layers):
        n, db = int(l.get('n', 0)), float(l.get('db', 16))
        if n > 0:
            y_p = curr_y_bot + (db/2)
            if n > 1:
                x_p = np.linspace(left_cx + (db/2), right_cx - (db/2), n)
            else:
                x_p = [0] # ตรงกลาง
                
            for x in x_p: 
                ax.add_patch(patches.Circle((x, y_p), db/2, color='#008c00', zorder=10))
            curr_y_bot += (db + 25.0) # ระยะห่างระหว่างชั้น (Clear Spacing 25mm)

    # Label ข้อมูล
    text_x = b/2 + 25
    top_t = " + ".join([f"{int(l['n'])}DB{int(l['db'])}" for l in top_layers if int(l.get('n',0)) > 0])
    bot_t = " + ".join([f"{int(l['n'])}DB{int(l['db'])}" for l in bot_layers if int(l.get('n',0)) > 0])
    
    if top_t:
        ax.text(text_x, h/2 - 10, f"Top:\n{textwrap.fill(top_t, 18)}", color='#d30000', va='top', fontweight='bold', fontsize=9)
    if bot_t:
        ax.text(text_x, -h/2 + 10, f"Bot:\n{textwrap.fill(bot_t, 18)}", color='#008c00', va='bottom', fontweight='bold', fontsize=9)
    
    if stir_s:
        stir_color = '#d30000' if float(stir_s) > s_max_limit else '#34495e'
        stir_label = (
            f"Shear Reinforcement:\n"
            f"RB{int(stir_db)} @ {int(stir_s)} mm\n"
            f"-------------------\n"
            f"S_max Limit: {int(s_max_limit)} mm"
        )
        ax.text(text_x, 0, stir_label, color=stir_color, va='center', fontweight='bold', fontsize=9,
                bbox=dict(boxstyle='round,pad=0.5', fc='#f8f9fa', ec=stir_color, lw=1))
        
    ax.text(0, h/2 + 20, f"SECTION {int(b)}x{int(h)}", ha='center', va='bottom', fontweight='black', fontsize=11)

    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_xlim(-b*0.8, b*2.4)
    ax.set_ylim(y0 - (h*0.2), h/2 + (h*0.25)) 
    
    f = io.StringIO()
    fig.savefig(f, format="svg", bbox_inches='tight', pad_inches=0.1, transparent=True)
    plt.close(fig)
    return f.getvalue()
