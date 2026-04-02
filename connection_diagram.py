"""
Connection Diagram Generator
============================
Generates flat horizontal SVG diagrams for bolt connection visualization.
"""

DIM_STROKE = "#6b7686"
DIM_TEXT = "#6b7686"
DIM_W = 2.5
DIM_FONT = "system-ui, -apple-system, Segoe UI, Roboto, Arial"

def arrow_head(x, y, direction="right", size=8):
    """Generate triangle arrowhead points."""
    if direction == "right":
        return f"{x},{y} {x - size},{y - size/2} {x - size},{y + size/2}"
    if direction == "left":
        return f"{x},{y} {x + size},{y - size/2} {x + size},{y + size/2}"
    if direction == "down":
        return f"{x},{y} {x - size/2},{y - size} {x + size/2},{y - size}"
    return f"{x},{y} {x - size/2},{y + size} {x + size/2},{y + size}"

def generate_connection_svg(
    n_lines: int,
    bolts_per_line: int,
    pitch: float,
    gauge: float,
    edge_end: float,
    edge_trans: float,
    leg_width: float,
    thickness: float,
    hole_dia: float,
    show_fracture: bool = True,
    show_block_shear: bool = True,
    brace_angle: float = 35.0,
) -> str:
    """Generate a flat horizontal SVG diagram of the bolt connection."""
    
    VB_W = 580
    VB_H = 280
    
    plate_x = 150
    plate_y = 85
    plate_w = 300
    plate_h = 140
    
    if n_lines == 2:
        plate_h = 180
        plate_y = 60
    
    bolt_y = plate_y + 35
    bolt_spacing = 80
    bolt_xs = [plate_x + 35 + i * bolt_spacing for i in range(bolts_per_line)]
    bolt_outer_r = 12
    bolt_inner_r = 7
    
    if n_lines == 2:
        bolt_y_top = plate_y + 40
        bolt_y_bot = plate_y + plate_h - 40
        bolt_rows = [bolt_y_top, bolt_y_bot]
    else:
        bolt_rows = [bolt_y]
    
    support_x = 115
    support_y = 95
    support_w = 30
    support_h = 120
    
    if n_lines == 2:
        support_y = 70
        support_h = 160
    
    gusset_pts = "140,205 140,115 175,140 175,230"
    if n_lines == 2:
        gusset_pts = "140,225 140,85 175,110 175,250"
    
    frac_x = bolt_xs[0] - 5
    frac_y1 = plate_y + 5
    frac_y2 = plate_y + plate_h - 5
    
    block_x = plate_x + 20
    block_y = plate_y + 10
    block_w = min(plate_w - 40, (bolts_per_line - 1) * bolt_spacing + 70)
    block_h = 60
    
    if n_lines == 2:
        block_h = plate_h - 30
        block_y = plate_y + 15
    
    arrow_x1 = plate_x + plate_w + 10
    arrow_y = plate_y + plate_h / 2
    arrow_x2 = plate_x + plate_w + 50
    label_x = plate_x + plate_w + 5
    label_y = plate_y + plate_h / 2 - 12
    
    steel_fill = "#f2f2f2"
    steel_stroke = "#9a9a9a"
    fracture_stroke = "#ff4d57"
    block_stroke = "#f2a24a"
    block_fill = "rgba(242,162,74,0.25)"
    arrow_stroke = "#35c6b3"
    
    svg_parts = []
    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VB_W} {VB_H}">')
    
    svg_parts.append(f'''
<rect x="{support_x}" y="{support_y}" width="{support_w}" height="{support_h}" 
      fill="#d8d8d8" stroke="{steel_stroke}" stroke-width="3" />
''')
    
    svg_parts.append(f'''
<polygon points="{gusset_pts}" fill="#e9e9e9" stroke="{steel_stroke}" stroke-width="3" />
''')
    
    svg_parts.append(f'''
<rect x="{plate_x}" y="{plate_y}" width="{plate_w}" height="{plate_h}" 
      fill="{steel_fill}" stroke="{steel_stroke}" stroke-width="4" />
''')
    
    if show_block_shear:
        svg_parts.append(f'''
<rect x="{block_x}" y="{block_y}" width="{block_w}" height="{block_h}" 
      fill="{block_fill}" stroke="{block_stroke}" stroke-width="4" />
''')
    
    if show_fracture:
        svg_parts.append(f'''
<line x1="{frac_x}" y1="{frac_y1}" x2="{frac_x}" y2="{frac_y2}" 
      stroke="{fracture_stroke}" stroke-width="4" stroke-dasharray="10 8" />
''')
    
    for row_y in bolt_rows:
        for cx in bolt_xs:
            svg_parts.append(f'<circle cx="{cx}" cy="{row_y}" r="{bolt_outer_r}" fill="#333" />')
            svg_parts.append(f'<circle cx="{cx}" cy="{row_y}" r="{bolt_inner_r}" fill="#bbb" />')
            svg_parts.append(f'<circle cx="{cx}" cy="{row_y}" r="{bolt_outer_r}" fill="none" stroke="#eee" stroke-width="2" />')
    
    svg_parts.append(f'''
<text x="{label_x}" y="{label_y}" fill="#8f9aa7" font-size="18" 
      font-family="system-ui, -apple-system, Segoe UI, Roboto, Arial">T</text>
<line x1="{arrow_x1}" y1="{arrow_y}" x2="{arrow_x2}" y2="{arrow_y}" 
      stroke="{arrow_stroke}" stroke-width="5" stroke-linecap="round" />
<polygon points="{arrow_x2},{arrow_y} {arrow_x2 - 14},{arrow_y - 8} {arrow_x2 - 14},{arrow_y + 8}" 
         fill="{arrow_stroke}" />
''')
    
    if bolts_per_line >= 2:
        p_x1 = bolt_xs[0]
        p_x2 = bolt_xs[1]
        bolt_y_ref = bolt_rows[0]
        ext_y1 = bolt_y_ref + 18
        ext_y2 = bolt_y_ref + 55
        dim_y = bolt_y_ref + 55
        label_y = bolt_y_ref + 75
        
        svg_parts.append(f'<line x1="{p_x1}" y1="{ext_y1}" x2="{p_x1}" y2="{ext_y2}" stroke="{DIM_STROKE}" stroke-width="{DIM_W}" />')
        svg_parts.append(f'<line x1="{p_x2}" y1="{ext_y1}" x2="{p_x2}" y2="{ext_y2}" stroke="{DIM_STROKE}" stroke-width="{DIM_W}" />')
        
        svg_parts.append(f'<line x1="{p_x1}" y1="{dim_y}" x2="{p_x2}" y2="{dim_y}" stroke="{DIM_STROKE}" stroke-width="{DIM_W}" />')
        svg_parts.append(f'<polygon points="{arrow_head(p_x1, dim_y, "right", 8)}" fill="{DIM_STROKE}" />')
        svg_parts.append(f'<polygon points="{arrow_head(p_x2, dim_y, "left", 8)}" fill="{DIM_STROKE}" />')
        
        p_mid = (p_x1 + p_x2) / 2
        p_val = p_x2 - p_x1
        svg_parts.append(f'<text x="{p_mid}" y="{label_y}" fill="{DIM_TEXT}" font-size="16" font-family="{DIM_FONT}" text-anchor="middle">p = {pitch:.0f}</text>')
    
    if n_lines == 2:
        ext_x1 = plate_x + plate_w + 60
        ext_x2 = plate_x + plate_w + 90
        dim_x = plate_x + plate_w + 90
        label_x = plate_x + plate_w + 100
        
        svg_parts.append(f'<line x1="{ext_x1}" y1="{bolt_y_top}" x2="{ext_x2}" y2="{bolt_y_top}" stroke="{DIM_STROKE}" stroke-width="{DIM_W}" />')
        svg_parts.append(f'<line x1="{ext_x1}" y1="{bolt_y_bot}" x2="{ext_x2}" y2="{bolt_y_bot}" stroke="{DIM_STROKE}" stroke-width="{DIM_W}" />')
        
        svg_parts.append(f'<line x1="{dim_x}" y1="{bolt_y_top}" x2="{dim_x}" y2="{bolt_y_bot}" stroke="{DIM_STROKE}" stroke-width="{DIM_W}" />')
        svg_parts.append(f'<polygon points="{arrow_head(dim_x, bolt_y_top, "down", 8)}" fill="{DIM_STROKE}" />')
        svg_parts.append(f'<polygon points="{arrow_head(dim_x, bolt_y_bot, "up", 8)}" fill="{DIM_STROKE}" />')
        
        g_mid = (bolt_y_top + bolt_y_bot) / 2
        svg_parts.append(f'<text x="{label_x}" y="{g_mid}" fill="{DIM_TEXT}" font-size="16" font-family="{DIM_FONT}" dominant-baseline="middle">g = {gauge:.0f}</text>')
    
    legend_x = 12
    legend_y = VB_H - 35
    if show_fracture:
        svg_parts.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 20}" y2="{legend_y}" stroke="{fracture_stroke}" stroke-width="3" stroke-dasharray="6 4" />')
        svg_parts.append(f'<text x="{legend_x + 26}" y="{legend_y + 4}" fill="#8f9aa7" font-size="11" font-family="sans-serif">Net fracture</text>')
    if show_block_shear:
        svg_parts.append(f'<rect x="{legend_x}" y="{legend_y + 10}" width="20" height="12" fill="{block_fill}" stroke="{block_stroke}" stroke-width="2" />')
        svg_parts.append(f'<text x="{legend_x + 26}" y="{legend_y + 20}" fill="#8f9aa7" font-size="11" font-family="sans-serif">Block shear</text>')
    
    svg_parts.append('</svg>')
    
    return '\n'.join(svg_parts)
