#!/usr/bin/env python3
"""
SINAPSE · make-chart.py — gráficos SVG themeables, generados (no dibujados a
mano), siguiendo el Visual Vocabulary del Financial Times (nueve intenciones:
desviación, correlación, ranking, distribución, cambio en el tiempo,
magnitud, parte-todo, espacial, flujo).

Filosofía: igual que make-map.py con los mapas, los gráficos de líneas/puntos
(donde el CSS puro pierde precisión) se GENERAN con este script y salen con
`data-viz="chart"` — exentos de la heurística de porcentajes del validador,
con role="img" + aria-label + viewBox y SIN width/height fijos, para respetar
paleta y tema (usan var(--accent, #4b46c8), var(--ink, #222230), var(--rule, #cfcfda)…). Los gráficos de
barras/waffle/bullet siguen siendo CSS puro (ver assets/sinapse.css).

Regla editorial: no repetir el mismo formato de viz dos números seguidos
(rotación, análoga al tono de columna). El menú semanal vive en
editorial/viz-menu.html y el catálogo en editorial/viz-catalog.json.

Uso:
    python3 scripts/make-chart.py --spec editorial/chart-006.json --out /tmp/chart.svg
    python3 scripts/make-chart.py --demo slope --out /tmp/demo.svg

Tipos: slope · line · sparkline · lollipop · dumbbell · scatter
Cada uno se define con un JSON pequeño (ver --demo <tipo> para un ejemplo).
"""

import argparse
import json
import sys
from pathlib import Path

# Lienzo base (coordenadas de usuario; el SVG escala por viewBox).
W, H = 760, 340
M = {"t": 46, "r": 130, "b": 52, "l": 64}   # márgenes (r ancho: etiquetas directas)


def _scale(dmin, dmax, lo, hi):
    if dmax == dmin:
        dmax = dmin + 1
    return lambda v: lo + (v - dmin) / (dmax - dmin) * (hi - lo)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _svg_open(aria, h=None):
    hh = h if h is not None else H
    return (f'<svg data-viz="chart" role="img" aria-label="{_esc(aria)}" '
            f'viewBox="0 0 {W} {hh}" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="var(--mono, monospace)">')


def _frame(title="", note="", h=None):
    """ejes mínimos; devuelve (header_svg, footer_svg)."""
    hh = h if h is not None else H
    head = ""
    if title:
        head += (f'<text x="{M["l"]}" y="24" font-size="15" '
                 f'font-family="var(--serif, Georgia, serif)" fill="var(--ink, #222230)">'
                 f'{_esc(title)}</text>')
    foot = ""
    if note:
        foot += (f'<text x="{M["l"]}" y="{hh-16}" font-size="12" '
                 f'fill="var(--ink-3, #7a7a90)">{_esc(note)}</text>')
    return head, foot


CAT = {  # paleta editorial por rol (misma familia que los mapas --map-c1..c4)
    1: "var(--map-c1, #3b5bdb)", 2: "var(--map-c2, #2f9e44)",
    3: "var(--map-c3, #e8973a)", 4: "var(--map-c4, #c2255c)",
    0: "var(--accent, #4b46c8)",
}


# ── slope · cambio en el tiempo / ranking (dos momentos) ────────────────────

def chart_slope(spec):
    """spec: {title, note, left_label, right_label, series:[{name,l,r,cat?}]}"""
    xs = spec.get("series", [])
    vals = [s["l"] for s in xs] + [s["r"] for s in xs]
    y = _scale(min(vals), max(vals), H - M["b"], M["t"])
    xL, xR = M["l"] + 40, W - M["r"] - 10
    head, foot = _frame(spec.get("title", ""), spec.get("note", ""))
    p = [head]
    p.append(f'<line x1="{xL}" y1="{M["t"]-8}" x2="{xL}" y2="{H-M["b"]}" '
             f'stroke="var(--rule, #cfcfda)" stroke-width="1"/>')
    p.append(f'<line x1="{xR}" y1="{M["t"]-8}" x2="{xR}" y2="{H-M["b"]}" '
             f'stroke="var(--rule, #cfcfda)" stroke-width="1"/>')
    p.append(f'<text x="{xL}" y="{M["t"]-16}" font-size="12" text-anchor="middle" '
             f'fill="var(--ink-3, #7a7a90)">{_esc(spec.get("left_label",""))}</text>')
    p.append(f'<text x="{xR}" y="{M["t"]-16}" font-size="12" text-anchor="middle" '
             f'fill="var(--ink-3, #7a7a90)">{_esc(spec.get("right_label",""))}</text>')
    for s in xs:
        c = CAT.get(s.get("cat", 0), CAT[0])
        yl, yr = y(s["l"]), y(s["r"])
        p.append(f'<line x1="{xL}" y1="{yl:.1f}" x2="{xR}" y2="{yr:.1f}" '
                 f'stroke="{c}" stroke-width="2.5" opacity="0.9"/>')
        p.append(f'<circle cx="{xL}" cy="{yl:.1f}" r="4" fill="{c}"/>')
        p.append(f'<circle cx="{xR}" cy="{yr:.1f}" r="4" fill="{c}"/>')
        p.append(f'<text x="{xL-10}" y="{yl+4:.1f}" font-size="12" text-anchor="end" '
                 f'fill="var(--ink-2, #45455a)">{_esc(s["l"])}</text>')
        p.append(f'<text x="{xR+10}" y="{yr+4:.1f}" font-size="12" '
                 f'fill="var(--ink, #222230)">{_esc(s["name"])} · {_esc(s["r"])}</text>')
    p.append(foot)
    return _svg_open(spec.get("aria", spec.get("title", "slope chart"))) + "".join(p) + "</svg>"


# ── line · cambio en el tiempo (serie continua, multi) ──────────────────────

def chart_line(spec):
    """spec: {title,note,x:[labels], series:[{name,values,cat?}]}"""
    xlab = spec["x"]
    series = spec["series"]
    allv = [v for s in series for v in s["values"]]
    y = _scale(min(allv + [0]), max(allv), H - M["b"], M["t"])
    x = _scale(0, len(xlab) - 1, M["l"], W - M["r"])
    head, foot = _frame(spec.get("title", ""), spec.get("note", ""))
    p = [head]
    p.append(f'<line x1="{M["l"]}" y1="{H-M["b"]}" x2="{W-M["r"]}" y2="{H-M["b"]}" '
             f'stroke="var(--rule, #cfcfda)"/>')
    for i, lab in enumerate(xlab):
        if i % max(1, len(xlab)//6) == 0 or i == len(xlab)-1:
            p.append(f'<text x="{x(i):.1f}" y="{H-M["b"]+18}" font-size="11" '
                     f'text-anchor="middle" fill="var(--ink-3, #7a7a90)">{_esc(lab)}</text>')
    for s in series:
        c = CAT.get(s.get("cat", 0), CAT[0])
        pts = " ".join(f'{x(i):.1f},{y(v):.1f}' for i, v in enumerate(s["values"]))
        p.append(f'<polyline points="{pts}" fill="none" stroke="{c}" '
                 f'stroke-width="2.5"/>')
        lv = s["values"][-1]
        p.append(f'<circle cx="{x(len(s["values"])-1):.1f}" cy="{y(lv):.1f}" r="4" fill="{c}"/>')
        p.append(f'<text x="{W-M["r"]+8}" y="{y(lv)+4:.1f}" font-size="12" '
                 f'fill="var(--ink, #222230)">{_esc(s["name"])}</text>')
    p.append(foot)
    return _svg_open(spec.get("aria", spec.get("title", "line chart"))) + "".join(p) + "</svg>"


# ── sparkline · micro-serie inline (sin ejes) ───────────────────────────────

def chart_sparkline(spec):
    """spec: {values, note?}  · viewBox compacto."""
    vals = spec["values"]
    w, h = 220, 54
    y = _scale(min(vals), max(vals), h - 6, 6)
    x = _scale(0, len(vals) - 1, 2, w - 2)
    pts = " ".join(f'{x(i):.1f},{y(v):.1f}' for i, v in enumerate(vals))
    last = f'<circle cx="{x(len(vals)-1):.1f}" cy="{y(vals[-1]):.1f}" r="3" fill="var(--accent, #4b46c8)"/>'
    return (f'<svg data-viz="chart" role="img" aria-label="{_esc(spec.get("aria","sparkline"))}" '
            f'viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
            f'<polyline points="{pts}" fill="none" stroke="var(--accent, #4b46c8)" stroke-width="2"/>'
            f'{last}</svg>')


# ── lollipop · ranking (muchas categorías) ──────────────────────────────────

def chart_lollipop(spec):
    """spec: {title,note,items:[{name,value,cat?}]} (ordenar antes de pasar)."""
    items = spec["items"]
    vmax = max(i["value"] for i in items)
    x = _scale(0, vmax, M["l"] + 120, W - M["r"])
    Hd = M["t"] + M["b"] + max(1, len(items)) * 56
    rowh = (Hd - M["t"] - M["b"]) / max(1, len(items))
    head, foot = _frame(spec.get("title", ""), spec.get("note", ""), h=Hd)
    p = [head]
    x0 = M["l"] + 120
    for k, it in enumerate(items):
        yc = M["t"] + rowh * (k + 0.5)
        c = CAT.get(it.get("cat", 0), CAT[0])
        p.append(f'<text x="{x0-12}" y="{yc+4:.1f}" font-size="12" text-anchor="end" '
                 f'fill="var(--ink-2, #45455a)">{_esc(it["name"])}</text>')
        p.append(f'<line x1="{x0}" y1="{yc:.1f}" x2="{x(it["value"]):.1f}" y2="{yc:.1f}" '
                 f'stroke="var(--rule, #cfcfda)" stroke-width="2"/>')
        p.append(f'<circle cx="{x(it["value"]):.1f}" cy="{yc:.1f}" r="5" fill="{c}"/>')
        p.append(f'<text x="{x(it["value"])+10:.1f}" y="{yc+4:.1f}" font-size="12" '
                 f'fill="var(--ink, #222230)">{_esc(it["value"])}</text>')
    p.append(foot)
    return _svg_open(spec.get("aria", spec.get("title", "lollipop chart")), h=Hd) + "".join(p) + "</svg>"


# ── dumbbell · desviación / brecha entre dos valores por categoría ──────────

def chart_dumbbell(spec):
    """spec: {title,note,a_label,b_label,items:[{name,a,b}]}"""
    items = spec["items"]
    vals = [v for it in items for v in (it["a"], it["b"])]
    x = _scale(min(vals), max(vals), M["l"] + 120, W - M["r"])
    Hd = M["t"] + M["b"] + max(1, len(items)) * 74
    rowh = (Hd - M["t"] - M["b"]) / max(1, len(items))
    head, foot = _frame(spec.get("title", ""), spec.get("note", ""), h=Hd)
    p = [head]
    ca, cb = CAT[3], CAT[1]
    p.append(f'<text x="{W-M["r"]}" y="{M["t"]-16}" font-size="11" text-anchor="end" '
             f'fill="var(--ink-3, #7a7a90)"><tspan fill="{ca}">●</tspan> {_esc(spec.get("a_label","A"))} '
             f'<tspan fill="{cb}">●</tspan> {_esc(spec.get("b_label","B"))}</text>')
    for k, it in enumerate(items):
        yc = M["t"] + rowh * (k + 0.5)
        xa, xb = x(it["a"]), x(it["b"])
        p.append(f'<text x="{M["l"]+108}" y="{yc+4:.1f}" font-size="12" text-anchor="end" '
                 f'fill="var(--ink-2, #45455a)">{_esc(it["name"])}</text>')
        p.append(f'<line x1="{xa:.1f}" y1="{yc:.1f}" x2="{xb:.1f}" y2="{yc:.1f}" '
                 f'stroke="var(--rule, #cfcfda)" stroke-width="3"/>')
        p.append(f'<circle cx="{xa:.1f}" cy="{yc:.1f}" r="5" fill="{ca}"/>')
        p.append(f'<circle cx="{xb:.1f}" cy="{yc:.1f}" r="5" fill="{cb}"/>')
    p.append(foot)
    return _svg_open(spec.get("aria", spec.get("title", "dumbbell chart")), h=Hd) + "".join(p) + "</svg>"


# ── scatter · correlación ───────────────────────────────────────────────────

def chart_scatter(spec):
    """spec: {title,note,x_label,y_label,points:[{x,y,name?,cat?}]}"""
    pts = spec["points"]
    xs = [pt["x"] for pt in pts]
    ys = [pt["y"] for pt in pts]
    x = _scale(min(xs), max(xs), M["l"], W - M["r"])
    y = _scale(min(ys), max(ys), H - M["b"], M["t"])
    head, foot = _frame(spec.get("title", ""), spec.get("note", ""))
    p = [head]
    p.append(f'<line x1="{M["l"]}" y1="{H-M["b"]}" x2="{W-M["r"]}" y2="{H-M["b"]}" stroke="var(--rule, #cfcfda)"/>')
    p.append(f'<line x1="{M["l"]}" y1="{M["t"]}" x2="{M["l"]}" y2="{H-M["b"]}" stroke="var(--rule, #cfcfda)"/>')
    p.append(f'<text x="{(M["l"]+W-M["r"])/2:.0f}" y="{H-14}" font-size="12" text-anchor="middle" '
             f'fill="var(--ink-3, #7a7a90)">{_esc(spec.get("x_label",""))}</text>')
    p.append(f'<text x="16" y="{(M["t"]+H-M["b"])/2:.0f}" font-size="12" '
             f'transform="rotate(-90 16 {(M["t"]+H-M["b"])/2:.0f})" text-anchor="middle" '
             f'fill="var(--ink-3, #7a7a90)">{_esc(spec.get("y_label",""))}</text>')
    for pt in pts:
        c = CAT.get(pt.get("cat", 0), CAT[0])
        p.append(f'<circle cx="{x(pt["x"]):.1f}" cy="{y(pt["y"]):.1f}" r="5" fill="{c}" opacity="0.85"/>')
        if pt.get("name"):
            p.append(f'<text x="{x(pt["x"])+8:.1f}" y="{y(pt["y"])+4:.1f}" font-size="11" '
                     f'fill="var(--ink-2, #45455a)">{_esc(pt["name"])}</text>')
    p.append(foot)
    return _svg_open(spec.get("aria", spec.get("title", "scatter plot"))) + "".join(p) + "</svg>"


BUILDERS = {"slope": chart_slope, "line": chart_line, "sparkline": chart_sparkline,
            "lollipop": chart_lollipop, "dumbbell": chart_dumbbell, "scatter": chart_scatter}

DEMOS = {
    "slope": {"type": "slope", "title": "Coste por MWh solar, 2019 → 2025",
              "left_label": "2019", "right_label": "2025", "note": "USD/MWh · fuente demo",
              "series": [{"name": "India", "l": 68, "r": 26, "cat": 1},
                         {"name": "Chile", "l": 55, "r": 21, "cat": 2},
                         {"name": "Alemania", "l": 82, "r": 48, "cat": 3}]},
    "line": {"type": "line", "title": "Índice demo", "note": "2020–2025",
             "x": ["2020", "2021", "2022", "2023", "2024", "2025"],
             "series": [{"name": "A", "values": [10, 22, 18, 35, 44, 60], "cat": 1},
                        {"name": "B", "values": [12, 14, 20, 19, 25, 30], "cat": 3}]},
    "sparkline": {"type": "sparkline", "values": [3, 5, 4, 8, 7, 12, 11, 18]},
    "lollipop": {"type": "lollipop", "title": "Proyectos por país (demo)",
                 "items": [{"name": "China", "value": 90, "cat": 1},
                           {"name": "EE. UU.", "value": 61, "cat": 3},
                           {"name": "India", "value": 44},
                           {"name": "Chile", "value": 28, "cat": 2}]},
    "dumbbell": {"type": "dumbbell", "title": "Brecha 2019 vs 2025 (demo)",
                 "a_label": "2019", "b_label": "2025",
                 "items": [{"name": "Región A", "a": 20, "b": 62},
                           {"name": "Región B", "a": 35, "b": 41},
                           {"name": "Región C", "a": 10, "b": 55}]},
    "scatter": {"type": "scatter", "title": "Correlación demo",
                "x_label": "PIB per cápita", "y_label": "Patentes/millón",
                "points": [{"x": 20, "y": 15, "name": "A", "cat": 1},
                           {"x": 45, "y": 38, "name": "B", "cat": 2},
                           {"x": 70, "y": 66, "name": "C", "cat": 3}]},
}


def render(spec):
    t = spec.get("type")
    if t not in BUILDERS:
        sys.exit(f"tipo de gráfico desconocido: {t} (opciones: {', '.join(BUILDERS)})")
    return BUILDERS[t](spec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", help="JSON con la especificación del gráfico")
    ap.add_argument("--demo", choices=list(DEMOS), help="renderizar un ejemplo")
    ap.add_argument("--out", default="-")
    args = ap.parse_args()
    if args.demo:
        spec = DEMOS[args.demo]
    elif args.spec:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    else:
        sys.exit("usa --spec <json> o --demo <tipo>")
    svg = render(spec)
    if args.out == "-":
        print(svg)
    else:
        Path(args.out).write_text(svg, encoding="utf-8")
        print(f"  ✓ {args.out}  ({len(svg)} bytes, data-viz=chart)")


if __name__ == "__main__":
    main()
