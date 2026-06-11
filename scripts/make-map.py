#!/usr/bin/env python3
"""
SINAPSE · make-map.py — generador de mapas SVG con geometría real.

Convierte world-atlas TopoJSON (countries-110m.json) en un SVG inline con
proyección Natural Earth, países resaltados por niveles (tiers) y tokens
CSS del sistema de diseño SINAPSE (var(--accent), var(--rule), …), de modo
que el mapa respeta paleta y tema (paper/sepia/eink) automáticamente.

Solo biblioteca estándar. Uso:

    python3 make-map.py --topo countries-110m.json --mode world \
        --hl "Bolivia:1,Chile:1,Argentina:1,China:2,India:2" --out mapa.svg

    python3 make-map.py --topo countries-110m.json --mode locator \
        --hl "Bolivia:1,Chile:1,Argentina:1" --pad 6 --out locator.svg

Tiers: 1 = acento pleno, 2 = acento 60%, 3 = acento 30%.
El SVG sale con role="img", aria-label, viewBox y sin width/height fijos
(cumple los checks ACCESSIBILITY y GEOMETRY de validate-issue.py) y con
data-viz="map" para que el validador pueda eximirlo de la heurística de
porcentajes de pies.
"""

import argparse
import json
import math
import sys

# ── Proyección Natural Earth I (Šavrič et al. 2011) ────────────────────────

def natural_earth(lon_deg, lat_deg):
    lam = math.radians(lon_deg)
    phi = math.radians(lat_deg)
    p2, p4 = phi * phi, phi ** 4
    x = lam * (0.8707 - 0.131979 * p2 - 0.013791 * p4
               + p4 * p4 * p2 * (0.003971 - 0.001529 * p2))
    y = phi * (1.007226 + 0.015085 * p2
               + p4 * p2 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4))
    return x, -y  # y invertida para coords de pantalla


# ── Decodificador TopoJSON (solo lo necesario) ──────────────────────────────

def decode_arcs(topo):
    scale = topo["transform"]["scale"]
    translate = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        points, x, y = [], 0, 0
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * scale[0] + translate[0],
                           y * scale[1] + translate[1]))
        arcs.append(points)
    return arcs


def ring_coords(arc_indexes, arcs):
    ring = []
    for idx in arc_indexes:
        pts = arcs[idx] if idx >= 0 else list(reversed(arcs[~idx]))
        ring.extend(pts if not ring else pts[1:])
    return ring


def geometry_rings(geom, arcs):
    """Devuelve lista de anillos (cada uno lista de (lon, lat))."""
    rings = []
    if geom["type"] == "Polygon":
        for r in geom["arcs"]:
            rings.append(ring_coords(r, arcs))
    elif geom["type"] == "MultiPolygon":
        for poly in geom["arcs"]:
            for r in poly:
                rings.append(ring_coords(r, arcs))
    return rings


# ── Generación SVG ──────────────────────────────────────────────────────────

def project_rings(rings):
    return [[natural_earth(lon, lat) for lon, lat in ring] for ring in rings]


def decimate(ring, tol=1.1):
    """Quita puntos a menos de `tol` px del último conservado (en coords ya
    escaladas al viewBox). Reduce ~70% del peso sin pérdida visible."""
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
                continue  # islote sub-píxel: fuera
        ring = decimate(ring, tol)
        if len(ring) < 4:
            continue
        parts.append("M" + "L".join(f"{x:.{r}f},{y:.{r}f}" for x, y in ring) + "Z")
    return "".join(parts)


def bbox_of(rings_list):
    xs = [x for rings in rings_list for ring in rings for x, _ in ring]
    ys = [y for rings in rings_list for ring in rings for _, y in ring]
    return min(xs), min(ys), max(xs), max(ys)


TIER_STYLE = {
    1: 'class="map-hl" fill="var(--accent)" fill-opacity="0.92"',
    2: 'class="map-hl" fill="var(--accent)" fill-opacity="0.58"',
    3: 'class="map-hl" fill="var(--accent)" fill-opacity="0.30"',
}
BASE_STYLE = 'class="map-base" fill="var(--paper-2)"'


def build_svg(topo, highlights, mode="world", pad_deg=6.0, aria=None,
              skip=("Antarctica",)):
    arcs = decode_arcs(topo)
    geoms = topo["objects"]["countries"]["geometries"]

    countries = []  # (name, tier, projected_rings)
    hl_geo_rings = []
    for g in geoms:
        name = g.get("properties", {}).get("name", "")
        if name in skip and mode == "world":
            continue
        rings = geometry_rings(g, arcs)
        tier = highlights.get(name)
        countries.append((name, tier, rings))
        if tier:
            hl_geo_rings.append(rings)

    if not hl_geo_rings and highlights:
        known = sorted(g.get("properties", {}).get("name", "") for g in geoms)
        sys.exit("Ningún país de --hl coincide. Nombres válidos p.ej.: "
                 + ", ".join(n for n in known if n)[:400])

    # Recorte en modo locator: bbox geográfica de los resaltados + padding
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
        corner_rings = [[[natural_earth(lon0, lat0), natural_earth(lon1, lat0),
                          natural_earth(lon1, lat1), natural_earth(lon0, lat1)]]]
        x0, y0, x1, y1 = bbox_of(corner_rings)
    else:
        x0, y0, x1, y1 = bbox_of([r for _, _, r in projected])

    # Normalizar a un viewBox de ancho 1000
    w_geo, h_geo = x1 - x0, y1 - y0
    W = 1000.0
    H = W * h_geo / w_geo
    sf = W / w_geo

    def tx(rings):
        return [[((x - x0) * sf, (y - y0) * sf) for x, y in ring] for ring in rings]

    # Mundo: enteros, decimación agresiva y sin islotes sub-píxel.
    # Locator: 1 decimal y decimación suave (hay zoom).
    if mode == "world":
        kw = dict(r=0, tol=2.0, min_extent=3.0)
        kw_hl = dict(r=0, tol=1.2, min_extent=0.0)
    else:
        kw = kw_hl = dict(r=1, tol=0.8, min_extent=0.0)

    base_paths, hl_paths = [], []
    for name, tier, rings in projected:
        d = rings_to_path(tx(rings), **(kw_hl if tier else kw))
        if not d:
            continue
        if tier:
            hl_paths.append(f'  <path d="{d}" {TIER_STYLE.get(tier, TIER_STYLE[1])}>'
                            f'<title>{name}</title></path>')
        else:
            base_paths.append(f'  <path d="{d}" {BASE_STYLE}/>')

    aria = aria or ("Mapa con países resaltados: "
                    + ", ".join(sorted(highlights)))
    svg = (
        f'<svg viewBox="0 0 {W:.0f} {H:.0f}" role="img" aria-label="{aria}" '
        f'data-viz="map" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;display:block">\n'
        f' <g stroke="var(--rule)" stroke-width="0.6" stroke-linejoin="round">\n'
        + "\n".join(base_paths) +
        '\n </g>\n'
        f' <g stroke="var(--paper)" stroke-width="0.8" stroke-linejoin="round">\n'
        + "\n".join(hl_paths) +
        '\n </g>\n</svg>'
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topo", required=True)
    p.add_argument("--mode", choices=["world", "locator"], default="world")
    p.add_argument("--hl", default="", help='"Bolivia:1,Chile:2,…"')
    p.add_argument("--pad", type=float, default=6.0)
    p.add_argument("--aria", default=None)
    p.add_argument("--out", default="-")
    args = p.parse_args()

    topo = json.load(open(args.topo, encoding="utf-8"))
    svg = build_svg(topo, parse_hl(args.hl), args.mode, args.pad, args.aria)
    if args.out == "-":
        print(svg)
    else:
        open(args.out, "w", encoding="utf-8").write(svg)
        print(f"OK → {args.out} ({len(svg)/1024:.1f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
