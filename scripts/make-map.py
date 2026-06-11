#!/usr/bin/env python3
"""
SINAPSE · make-map.py — mapas SVG con geometría real + anotaciones.

Convierte world-atlas TopoJSON (countries-110m.json) en SVG inline con
proyección Natural Earth, países resaltados por niveles (tiers), tokens
CSS del sistema (var(--accent)…) y —opcional— ANOTACIONES con línea-guía:
cada país anotado dibuja un punto en su centroide, una línea hasta el
margen y una etiqueta con su nombre y una cifra clave.

Uso:
  python3 make-map.py --topo data/countries-110m.json --mode world \
      --hl "China:2,India:2" \
      --annotate "Chile|Chile · 66 proyectos;Bolivia|Bolivia · 23% reservas" \
      --out mapa.svg

  --annotate "Pais|Etiqueta;Pais|Etiqueta"   (los anotados se resaltan solos;
             tier opcional: "Pais|Etiqueta|2")

Tiers: 1 acento pleno · 2 acento 60% · 3 acento 30%.
SVG con role="img", aria-label, viewBox, sin width/height fijos y
data-viz="map" (cumple validate-issue.py / validate-pro.py).
"""

import argparse
import json
import math
import sys


# ── Proyección Natural Earth I ───────────────────────────────────────────────

def natural_earth(lon_deg, lat_deg):
    lam = math.radians(lon_deg); phi = math.radians(lat_deg)
    p2, p4 = phi * phi, phi ** 4
    x = lam * (0.8707 - 0.131979 * p2 - 0.013791 * p4
               + p4 * p4 * p2 * (0.003971 - 0.001529 * p2))
    y = phi * (1.007226 + 0.015085 * p2
               + p4 * p2 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4))
    return x, -y


# ── TopoJSON ─────────────────────────────────────────────────────────────────

def decode_arcs(topo):
    scale = topo["transform"]["scale"]; translate = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        pts, x, y = [], 0, 0
        for dx, dy in arc:
            x += dx; y += dy
            pts.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
        arcs.append(pts)
    return arcs


def ring_coords(idxs, arcs):
    ring = []
    for idx in idxs:
        pts = arcs[idx] if idx >= 0 else list(reversed(arcs[~idx]))
        ring.extend(pts if not ring else pts[1:])
    return ring


def geometry_rings(geom, arcs):
    rings = []
    if geom["type"] == "Polygon":
        for r in geom["arcs"]:
            rings.append(ring_coords(r, arcs))
    elif geom["type"] == "MultiPolygon":
        for poly in geom["arcs"]:
            for r in poly:
                rings.append(ring_coords(r, arcs))
    return rings


# ── SVG helpers ──────────────────────────────────────────────────────────────

def project_rings(rings):
    return [[natural_earth(lon, lat) for lon, lat in ring] for ring in rings]


def decimate(ring, tol=1.1):
    if len(ring) <= 4:
        return ring
    out = [ring[0]]
    for pt in ring[1:-1]:
        lx, ly = out[-1]
        if (pt[0] - lx) ** 2 + (pt[1] - ly) ** 2 >= tol * tol:
            out.append(pt)
    out.append(ring[-1])
    return out


def rings_to_path(rings, r=1, tol=1.1, min_extent=0.0):
    parts = []
    for ring in rings:
        if min_extent and len(ring) > 2:
            xs = [x for x, _ in ring]; ys = [y for _, y in ring]
            if (max(xs) - min(xs)) < min_extent and (max(ys) - min(ys)) < min_extent:
                continue
        ring = decimate(ring, tol)
        if len(ring) < 4:
            continue
        parts.append("M" + "L".join(f"{x:.{r}f},{y:.{r}f}" for x, y in ring) + "Z")
    return "".join(parts)


def bbox_of(rings_list):
    xs = [x for rings in rings_list for ring in rings for x, _ in ring]
    ys = [y for rings in rings_list for ring in rings for _, y in ring]
    return min(xs), min(ys), max(xs), max(ys)


def largest_ring_centroid(rings):
    """Centroide del anillo de mayor bbox (ignora islotes)."""
    best, best_area = None, -1
    for ring in rings:
        if len(ring) < 3:
            continue
        xs = [x for x, _ in ring]; ys = [y for _, y in ring]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if area > best_area:
            best_area, best = area, ring
    if not best:
        return None
    return (sum(x for x, _ in best) / len(best),
            sum(y for _, y in best) / len(best))


# Categorías con COLOR propio (no opacidad). Tokens en sinapse.css (--map-c1..c4),
# theme-aware. El número de categoría = el rol editorial (productor, procesador…).
CAT_FILL = {1: 'var(--map-c1)', 2: 'var(--map-c2)', 3: 'var(--map-c3)', 4: 'var(--map-c4)'}
def cat_style(t):
    return f'class="map-hl map-c{t}" fill="{CAT_FILL.get(t, CAT_FILL[1])}"'
BASE_STYLE = 'class="map-base" fill="var(--paper-2)"'


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_svg(topo, highlights, mode="world", pad_deg=6.0, aria=None,
              annotations=None, skip=("Antarctica",)):
    annotations = annotations or {}
    # los países anotados se resaltan solos (tier 1 por defecto)
    for name, (label, tier) in annotations.items():
        highlights.setdefault(name, tier or 1)

    arcs = decode_arcs(topo)
    geoms = topo["objects"]["countries"]["geometries"]

    countries, hl_geo_rings = [], []
    for g in geoms:
        name = g.get("properties", {}).get("name", "")
        if name in skip and mode == "world":
            continue
        rings = geometry_rings(g, arcs)
        tier = highlights.get(name)
        countries.append((name, tier, rings))
        if tier:
            hl_geo_rings.append(rings)

    if highlights and not hl_geo_rings:
        known = sorted(g.get("properties", {}).get("name", "") for g in geoms)
        sys.exit("Ningún país de --hl/--annotate coincide. Ejemplos válidos: "
                 + ", ".join(n for n in known if n)[:400])

    if mode == "locator":
        lons = [lon for rings in hl_geo_rings for ring in rings for lon, _ in ring]
        lats = [lat for rings in hl_geo_rings for ring in rings for _, lat in ring]
        lon0, lon1 = min(lons) - pad_deg, max(lons) + pad_deg
        lat0, lat1 = min(lats) - pad_deg, max(lats) + pad_deg

        def visible(rings):
            return any(lon0 <= lon <= lon1 and lat0 <= lat <= lat1
                       for ring in rings for lon, lat in ring)
        countries = [(n, t, r) for n, t, r in countries if visible(r)]

    projected = [(n, t, project_rings(r)) for n, t, r in countries]

    if mode == "locator":
        corner = [[[natural_earth(lon0, lat0), natural_earth(lon1, lat0),
                    natural_earth(lon1, lat1), natural_earth(lon0, lat1)]]]
        x0, y0, x1, y1 = bbox_of(corner)
    else:
        x0, y0, x1, y1 = bbox_of([r for _, _, r in projected])

    w_geo, h_geo = x1 - x0, y1 - y0
    W = 1000.0
    H = W * h_geo / w_geo
    sf = W / w_geo

    def tx(rings):
        return [[((x - x0) * sf, (y - y0) * sf) for x, y in ring] for ring in rings]

    if mode == "world":
        kw = dict(r=0, tol=2.0, min_extent=3.0)
        kw_hl = dict(r=0, tol=1.2, min_extent=0.0)
    else:
        kw = kw_hl = dict(r=1, tol=0.8, min_extent=0.0)

    base_paths, hl_paths, centroids = [], [], {}
    for name, tier, rings in projected:
        scaled = tx(rings)
        d = rings_to_path(scaled, **(kw_hl if tier else kw))
        if not d:
            continue
        if tier:
            hl_paths.append(f'  <path d="{d}" {cat_style(tier)}>'
                            f'<title>{esc(name)}</title></path>')
        else:
            base_paths.append(f'  <path d="{d}" {BASE_STYLE}/>')
        if name in annotations:
            c = largest_ring_centroid(scaled)
            if c:
                centroids[name] = c

    # ── Anotaciones con línea-guía + color por categoría ─────────────────
    anno_svg, ML, MR = "", 0.0, 0.0
    if annotations and centroids:
        # (name, label, centroide, categoría)
        items = [(n, annotations[n][0], centroids[n], annotations[n][1] or 1)
                 for n in annotations if n in centroids]
        left = sorted([it for it in items if it[2][0] < W / 2], key=lambda t: t[2][1])
        right = sorted([it for it in items if it[2][0] >= W / 2], key=lambda t: t[2][1])

        FS = max(22.0, H / 16)
        CW = FS * 0.60                       # ancho de carácter monospace (exacto)
        longest = max((len(l) for _, l, _, _ in items), default=10)
        MARGIN = longest * CW + 18
        ML = MARGIN if left else 0.0
        MR = MARGIN if right else 0.0
        GAP = max(FS * 1.7, H / 12)

        def place(group):
            ys = [c[1] for _, _, c, _ in group]
            for i in range(1, len(ys)):
                if ys[i] - ys[i - 1] < GAP:
                    ys[i] = ys[i - 1] + GAP
            over = ys[-1] - (H - FS) if ys else 0
            if over > 0:
                ys = [y - over for y in ys]
            return [max(FS, y) for y in ys]

        def render(group, side):
            ys = place(group)
            out = []
            for (name, label, (cx, cy), tier), ly in zip(group, ys):
                color = CAT_FILL.get(tier, CAT_FILL[1])
                width = len(label) * CW
                if side == "L":              # etiqueta termina a la izq. del mapa
                    x_start = -10 - width; edge = -8
                else:                        # etiqueta empieza a la der. del mapa
                    x_start = W + 10; edge = W + 8
                out.append(
                    f'  <polyline points="{cx:.0f},{cy:.0f} {edge:.0f},{ly:.0f}" '
                    f'fill="none" stroke="var(--ink-3)" stroke-width="1" '
                    f'stroke-linejoin="round"/>')
                out.append(f'  <circle cx="{cx:.0f}" cy="{cy:.0f}" r="3.6" '
                           f'fill="{color}"/>')
                head, tail = (label.split(" · ", 1) + [""])[:2]
                # x EXPLÍCITA en cada tspan: no dependemos del auto-avance de
                # tspan (algunos renderers no lo aplican). Monospace lo hace exacto.
                t = (f'  <text y="{ly:.0f}" text-anchor="start" '
                     f'font-family="var(--mono), monospace" font-size="{FS:.0f}" '
                     f'dominant-baseline="middle">'
                     f'<tspan x="{x_start:.0f}" fill="var(--ink)" '
                     f'font-weight="600">{esc(head)}</tspan>')
                if tail:
                    tail_x = x_start + len(head + " · ") * CW
                    t += (f'<tspan x="{tail_x:.0f}" fill="{color}">'
                          f'{esc(" · " + tail)}</tspan>')
                out.append(t + '</text>')
            return "\n".join(out)

        anno_svg = ("\n <g class=\"map-anno\">\n"
                    + (render(left, "L") + "\n" if left else "")
                    + (render(right, "R") if right else "")
                    + "\n </g>")

    vb = f'{-ML:.0f} 0 {W + ML + MR:.0f} {H:.0f}'
    aria = aria or ("Mapa con países resaltados: " + ", ".join(sorted(highlights)))
    svg = (
        f'<svg viewBox="{vb}" role="img" aria-label="{esc(aria)}" '
        f'data-viz="map" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;display:block">\n'
        f' <g stroke="var(--rule)" stroke-width="0.6" stroke-linejoin="round">\n'
        + "\n".join(base_paths) +
        '\n </g>\n'
        f' <g stroke="var(--paper)" stroke-width="0.8" stroke-linejoin="round">\n'
        + "\n".join(hl_paths) +
        '\n </g>'
        + anno_svg +
        '\n</svg>'
    )
    return svg


def parse_hl(s):
    out = {}
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        name, _, tier = part.partition(":")
        out[name.strip()] = int(tier) if tier else 1
    return out


def parse_annotations(s):
    """ "Chile|Chile · 66 proyectos;Bolivia|Bolivia · 23%|2" """
    out = {}
    for part in s.split(";"):
        part = part.strip()
        if not part:
            continue
        bits = part.split("|")
        name = bits[0].strip()
        label = bits[1].strip() if len(bits) > 1 else name
        tier = int(bits[2]) if len(bits) > 2 and bits[2].strip() else 1
        out[name] = (label, tier)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topo", required=True)
    p.add_argument("--mode", choices=["world", "locator"], default="world")
    p.add_argument("--hl", default="")
    p.add_argument("--annotate", default="",
                   help='"Pais|Etiqueta · cifra;Pais|Etiqueta|tier"')
    p.add_argument("--pad", type=float, default=6.0)
    p.add_argument("--aria", default=None)
    p.add_argument("--out", default="-")
    args = p.parse_args()

    topo = json.load(open(args.topo, encoding="utf-8"))
    svg = build_svg(topo, parse_hl(args.hl), args.mode, args.pad, args.aria,
                    parse_annotations(args.annotate) if args.annotate else None)
    if args.out == "-":
        print(svg)
    else:
        open(args.out, "w", encoding="utf-8").write(svg)
        print(f"OK → {args.out} ({len(svg) / 1024:.1f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
