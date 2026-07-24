#!/usr/bin/env python3
"""
SINAPSE — validador de pre-publicación.

Verifica que cada HTML de número de SINAPSE cumpla las reglas operativas del
marco editorial y del marco de visualización antes de publicar. Usa solo la
biblioteca estándar de Python (sin pip install).

Uso:
    python3 scripts/validate-issue.py issues/n001-abril-2026.html
    python3 scripts/validate-issue.py issues/*.html en/issues/*.html
    python3 scripts/validate-issue.py --site sinapse-site/   # valida todo

Salida:
    Reporte por archivo en stdout, con marcas ✓ / ⚠ / ✗.
    Exit code 0 si todos pasan los checks duros; 1 si alguno falla.

Categorías:
    [STRUCTURE]       — secciones, TOC, paridad ES/EN
    [ACCESSIBILITY]   — SVG aria, lang, tamaño de texto
    [DATA INTEGRITY]  — sumas de %, citas, dimensiones del Atlas
    [GEOMETRY]        — viewBox, overflow básico
    [EDITORIAL]       — .plain en ítems densos, metadata oculta
    [REGISTRY]        — registro.json coherente con archivos en disco
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuración

REQUIRED_SECTIONS_ES = [
    ("pulso",      "Pulso"),
    ("portada",    "Portada"),
    ("papers",     "Papers"),
    ("tech",       "Tech"),
    ("industria",  "Industria"),
    ("columna",    "Columna"),
    ("contraste",  "Contraste"),
    ("dato",       "Dato"),
    ("apendice",   "Apéndice"),
]
REQUIRED_SECTIONS_EN = [
    ("pulse",         "Pulse"),
    ("cover",         "Cover"),
    ("papers",        "Papers"),
    ("tech",          "Tech"),
    ("industry",      "Industry"),
    ("column",        "Column"),
    ("counterpoint",  "Counterpoint"),
    ("datum",         "Datum"),
    ("appendix",      "Appendix"),
]

ATLAS_DIMENSIONS_ES = [
    "Países en el titular",
    "Países en la trama real",
    "Quién cobra",
    "Quién paga",
    r"Horizonte\s+5\s*/\s*10\s+años",
    "Brecha regulatoria",
    "Punto ciego",
]
ATLAS_DIMENSIONS_EN = [
    "Countries in the headline",
    "Countries in the actual story",
    "Who profits",
    "Who pays",
    r"5\s*/\s*10-year horizon",
    "Regulatory gap",
    "Blind spot",
]

# Jerga densa que sugiere que un ítem de Pulso/Tech debería tener .plain
DENSE_JARGON = [
    r"\bKLKB1\b", r"\bePPP\b", r"\bMOX\b", r"\bMWe\b", r"\bMWt\b",
    r"\bBSL-?[34]\b", r"\bLNP\b", r"\bhazard ratio\b",
    r"\bp-?value\b", r"\bbosónico\b", r"\bbosonic\b",
    r"\bQEC\b", r"\bCRISPR\b.*\bin\s+vivo\b",
    r"\bKV-?cache\b", r"\bFLOPs\b",
    r"\bBCS\b", r"\bfermion(e|i)?\b",
]

# Metadata interna que NO debe aparecer en HTML público
LEAKED_METADATA = [
    r"Tono:\s",
    r"Falacia:\s",
    r"Tipo de falacia:\s",
    r"Debate estructural:\s",
]


# ---------------------------------------------------------------------------
# Utilidades

class Result:
    """Resultado de un check individual."""
    LEVELS = {"pass": "✓", "warn": "⚠", "fail": "✗"}

    def __init__(self, name, level="pass", detail=""):
        assert level in self.LEVELS, f"Nivel inválido: {level}"
        self.name = name
        self.level = level
        self.detail = detail

    def is_fail(self):
        return self.level == "fail"

    def __str__(self):
        symbol = self.LEVELS[self.level]
        line = f"    {symbol} {self.name}"
        if self.detail:
            line += f" — {self.detail}"
        return line


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def is_english(html: str) -> bool:
    return bool(re.search(r'<html[^>]*\blang="en"', html))


# ---------------------------------------------------------------------------
# Checks individuales

def check_structure(html: str, file_label: str):
    results = []
    en = is_english(html)
    required = REQUIRED_SECTIONS_EN if en else REQUIRED_SECTIONS_ES
    label = "EN" if en else "ES"

    # Secciones
    missing = []
    for sec_id, sec_name in required:
        if not re.search(rf'<section[^>]+id="{sec_id}"', html):
            missing.append(f"{sec_name} (#{sec_id})")
    if missing:
        results.append(Result(
            f"[STRUCTURE/{label}] 9 secciones presentes",
            "fail",
            "faltan: " + ", ".join(missing)
        ))
    else:
        results.append(Result(f"[STRUCTURE/{label}] 9 secciones presentes con sus IDs"))

    # TOC enlaza a cada sección
    toc_links = re.findall(r'<a href="#([^"]+)"', html)
    expected_ids = [sec_id for sec_id, _ in required]
    if all(eid in toc_links for eid in expected_ids):
        results.append(Result(f"[STRUCTURE/{label}] TOC enlaza las 9 secciones"))
    else:
        missing_links = [eid for eid in expected_ids if eid not in toc_links]
        results.append(Result(
            f"[STRUCTURE/{label}] TOC enlaza las 9 secciones",
            "fail",
            "faltan enlaces a: " + ", ".join(missing_links)
        ))

    return results


def check_accessibility(html: str):
    results = []
    svgs = re.findall(r'<svg\b[^>]*>', html)
    if not svgs:
        # Diseño v2: gráficos HTML/CSS (.chart), no SVG. No es un problema.
        return results

    # Cada SVG con role="img" y aria-label no vacío
    bad = []
    for i, svg_tag in enumerate(svgs):
        has_role = bool(re.search(r'\brole="img"', svg_tag))
        aria = re.search(r'\baria-label="([^"]+)"', svg_tag)
        if not has_role or not aria or not aria.group(1).strip():
            bad.append(f"SVG #{i+1}")
    if bad:
        results.append(Result(
            "[ACCESSIBILITY] cada SVG con role+aria-label",
            "fail",
            "faltan: " + ", ".join(bad)
        ))
    else:
        results.append(Result(f"[ACCESSIBILITY] {len(svgs)} SVG con role+aria-label"))

    # <html lang>
    if re.search(r'<html[^>]+\blang="(es|en)"', html):
        results.append(Result("[ACCESSIBILITY] <html lang> declarado"))
    else:
        results.append(Result("[ACCESSIBILITY] <html lang> declarado", "fail",
                              "no se encontró lang='es' ni lang='en'"))

    # Tamaño de texto SVG: detectar font-size < 9
    small_text = re.findall(r'font-size="(\d+(?:\.\d+)?)"', html)
    too_small = [s for s in small_text if float(s) < 9]
    if too_small:
        results.append(Result(
            "[ACCESSIBILITY] texto SVG ≥ 9 px",
            "warn",
            f"{len(too_small)} ocurrencia(s) por debajo de 9 px: {sorted(set(too_small))[:5]}"
        ))
    else:
        results.append(Result("[ACCESSIBILITY] texto SVG ≥ 9 px en todas las ocurrencias"))

    return results


def check_data_integrity(html: str, file_label: str):
    results = []
    en = is_english(html)
    label = "EN" if en else "ES"

    # Sumas de %: si el SVG declara data-pie-pcts="…" o data-stacked-pcts="…",
    # usar esa lista como fuente de verdad. Si no, fallback a regex sobre el texto.
    svg_blocks = re.findall(r'<svg\b.*?</svg>', html, re.DOTALL)
    for i, svg in enumerate(svg_blocks):
        # 0) Mapas geográficos (data-viz="map"): exentos de la heurística de
        #    porcentajes — sus cifras viven en HTML adyacente, no en el SVG.
        if re.search(r'<svg\b[^>]*data-viz="(?:map|chart)"', svg):
            results.append(Result(
                f"[DATA INTEGRITY/{label}] SVG #{i+1} data-viz (map/chart) — exento de suma de %"
            ))
            continue
        # 1) Atributo declarativo (preferido)
        m = re.search(r'data-(?:pie|stacked)-pcts="([\d,\.\s]+)"', svg)
        if m:
            declared = [float(x) for x in re.split(r'[,\s]+', m.group(1).strip()) if x]
            total = sum(declared)
            if 99 <= total <= 101:
                results.append(Result(
                    f"[DATA INTEGRITY/{label}] SVG #{i+1} porcentajes declarados suman 100 ± 1 pp",
                    "pass",
                    f"suma = {total:.1f}; valores: {declared}"
                ))
            else:
                results.append(Result(
                    f"[DATA INTEGRITY/{label}] SVG #{i+1} porcentajes declarados suman 100 ± 1 pp",
                    "fail",
                    f"suma = {total:.1f}; valores: {declared}"
                ))
            continue

        # 2) Fallback: heurística sobre el texto del SVG
        pct_matches = re.findall(r'(?<!\d)(\d{1,3})\s*%', svg)
        if not pct_matches:
            continue
        pcts = [int(p) for p in pct_matches]
        non_total = [p for p in pcts if p != 100]
        if len(non_total) >= 3:
            total = sum(non_total)
            candidates = [total, total / 2, total / 3]  # repeticiones posibles: slice+leyenda+nota
            ok = any(99 <= c <= 101 for c in candidates)
            if not ok:
                results.append(Result(
                    f"[DATA INTEGRITY/{label}] SVG #{i+1} porcentajes suman 100 ± 1 pp (heurística)",
                    "fail",
                    f"suma={total}, /2={total/2:.1f}, /3={total/3:.1f}; cifras: {sorted(non_total)}; "
                    "considera añadir data-pie-pcts / data-stacked-pcts al <svg>"
                ))
            else:
                divisor = next(d for d, c in zip([1, 2, 3], candidates) if 99 <= c <= 101)
                results.append(Result(
                    f"[DATA INTEGRITY/{label}] SVG #{i+1} porcentajes suman 100 ± 1 pp",
                    "pass",
                    f"heurística suma/{divisor} = {total/divisor:.1f}"
                ))

    # Atlas: dimensiones obligatorias (diseño v2: <section class="sec contraste">)
    atlas_dims = ATLAS_DIMENSIONS_EN if en else ATLAS_DIMENSIONS_ES
    # v2 primero, fallback a v1
    contraste = re.search(
        r'<section[^>]*class="sec[^"]*contraste"[^>]*>(.*?)</section>',
        html, re.DOTALL
    )
    if not contraste:
        contraste = re.search(r'<div class="contraste">(.*?)</div>\s*</section>', html, re.DOTALL)

    if contraste:
        body = contraste.group(1)
        if 'class="atlas"' in body:
            missing_dims = []
            for dim_pattern in atlas_dims:
                if not re.search(dim_pattern, body):
                    missing_dims.append(dim_pattern)
            if missing_dims:
                results.append(Result(
                    f"[DATA INTEGRITY/{label}] Atlas con 7 dimensiones obligatorias",
                    "fail",
                    "faltan: " + ", ".join(missing_dims)
                ))
            else:
                results.append(Result(f"[DATA INTEGRITY/{label}] Atlas con 7 dimensiones obligatorias"))
        else:
            results.append(Result(
                f"[DATA INTEGRITY/{label}] Atlas presente en Contraste",
                "warn",
                "el Contraste no tiene bloque .atlas (¿número sin Atlas?)"
            ))

        # Refs/citas: v2 puede usar .refs (v1) o citas inline en .prose / .appendix-paper (v2).
        # Aceptamos si hay ≥3 URLs en el cuerpo del Contraste O en cualquier .appendix-paper.
        all_urls = re.findall(r'href="(https?://[^"]+)"', body)
        appendix_urls = re.findall(
            r'<article class="appendix-paper">.*?</article>',
            html, re.DOTALL
        )
        appendix_url_count = sum(len(re.findall(r'href="(https?://[^"]+)"', a)) for a in appendix_urls)
        total_urls = len(all_urls) + appendix_url_count
        if total_urls >= 3:
            results.append(Result(
                f"[DATA INTEGRITY/{label}] referencias externas presentes",
                "pass",
                f"{total_urls} URLs en Contraste + Apéndice"
            ))
        else:
            results.append(Result(
                f"[DATA INTEGRITY/{label}] referencias externas presentes",
                "warn",
                f"solo {total_urls} URL(s)"
            ))
    else:
        results.append(Result(
            f"[DATA INTEGRITY/{label}] sección Contraste",
            "warn",
            "no se encontró <section class='sec contraste'> (¿número sin Contraste?)"
        ))

    return results


def check_geometry(html: str):
    results = []
    svgs = re.findall(r'<svg\b[^>]*>', html)

    # viewBox declarado
    no_vb = [s for s in svgs if not re.search(r'\bviewBox="', s)]
    if no_vb:
        results.append(Result("[GEOMETRY] viewBox declarado en cada SVG",
                              "fail", f"{len(no_vb)} SVG(s) sin viewBox"))
    else:
        results.append(Result(f"[GEOMETRY] viewBox declarado en {len(svgs)} SVG(s)"))

    # No width/height fijos (responsive)
    fixed = [s for s in svgs if re.search(r'<svg\b[^>]+\bwidth="\d', s)]
    if fixed:
        results.append(Result("[GEOMETRY] sin width/height fijos en SVG",
                              "warn", f"{len(fixed)} SVG(s) con width/height numérico"))
    else:
        results.append(Result("[GEOMETRY] SVG escalables (sin width/height fijos)"))

    return results


def check_editorial(html: str, file_label: str):
    results = []
    en = is_english(html)
    label = "EN" if en else "ES"

    # Metadata leakage
    leaks = []
    for pattern in LEAKED_METADATA:
        if re.search(pattern, html):
            leaks.append(pattern)
    if leaks:
        results.append(Result(
            f"[EDITORIAL/{label}] sin metadata interna expuesta",
            "fail",
            "encontrado: " + ", ".join(leaks)
        ))
    else:
        results.append(Result(f"[EDITORIAL/{label}] sin metadata interna expuesta"))

    # .plain heurística: si un .pulse .item contiene jerga densa, debería tener .plain
    items = re.findall(r'<div class="item">(.*?)</div>\s*</div>', html, re.DOTALL)
    if not items:
        # Fallback más robusto: buscar bloques que comienzan con <div class="nb">
        items = re.findall(r'<div class="nb">.*?(?=<div class="item">|</section>)',
                           html, re.DOTALL)
    needs_plain = 0
    has_plain = 0
    for item in items:
        if any(re.search(p, item, re.IGNORECASE) for p in DENSE_JARGON):
            needs_plain += 1
            if 'class="plain"' in item:
                has_plain += 1
    if needs_plain == 0:
        results.append(Result(f"[EDITORIAL/{label}] .plain — sin ítems densos detectados"))
    elif has_plain == needs_plain:
        results.append(Result(
            f"[EDITORIAL/{label}] .plain en ítems con jerga densa",
            "pass",
            f"{has_plain}/{needs_plain} ítems densos cubiertos"
        ))
    else:
        results.append(Result(
            f"[EDITORIAL/{label}] .plain en ítems con jerga densa",
            "warn",
            f"{has_plain}/{needs_plain} ítems densos tienen .plain (revisar)"
        ))

    return results


def check_registry(site_dir: Path):
    results = []
    reg_path = site_dir / "data" / "registro.json"
    if not reg_path.exists():
        return [Result("[REGISTRY] data/registro.json existe", "fail")]

    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [Result("[REGISTRY] JSON válido", "fail", str(e))]
    results.append(Result("[REGISTRY] JSON válido"))

    issues_es = site_dir / "issues"
    issues_en = site_dir / "en" / "issues"

    missing_files = []
    missing_i18n = []
    for n in data.get("numeros", []):
        es_file = issues_es / n.get("archivo", "")
        if not es_file.exists():
            missing_files.append(f"ES: {es_file.name}")
        en_archivo = n.get("i18n", {}).get("en", {}).get("archivo", "")
        if en_archivo:
            en_file = issues_en / en_archivo
            if not en_file.exists():
                missing_files.append(f"EN: {en_archivo}")
        else:
            missing_i18n.append(f"N°{n.get('numero')}")

    if missing_files:
        results.append(Result(
            "[REGISTRY] todos los archivos en disco",
            "fail",
            "faltan: " + ", ".join(missing_files)
        ))
    else:
        results.append(Result(f"[REGISTRY] {len(data.get('numeros', []))} número(s) con archivo en disco"))

    if missing_i18n:
        results.append(Result(
            "[REGISTRY] i18n.en presente para cada número",
            "warn",
            "sin i18n.en: " + ", ".join(missing_i18n)
        ))
    else:
        results.append(Result("[REGISTRY] i18n.en presente para cada número"))

    return results


# ---------------------------------------------------------------------------
# Orquestación

def validate_file(path: Path):
    html = read_text(path)
    # Saltar archivos basura / de referencia / vacíos
    if not html.strip():
        return [Result(f"[SKIP] {path.name}", "warn", "archivo vacío (omitido)")]
    if any(s in path.name for s in ("-redesign-ref", "-backup", ".bak.")):
        return [Result(f"[SKIP] {path.name}", "warn", "archivo de referencia/backup (omitido)")]
    results = []
    results += check_structure(html, path.name)
    results += check_accessibility(html)
    results += check_data_integrity(html, path.name)
    results += check_geometry(html)
    results += check_editorial(html, path.name)
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("files", nargs="*", help="Archivos HTML a validar")
    p.add_argument("--site", help="Validar todo un directorio sinapse-site/")
    args = p.parse_args()

    files = []
    site_dir = None

    if args.site:
        site_dir = Path(args.site)
        files += sorted((site_dir / "issues").glob("n*.html"))
        files += sorted((site_dir / "en" / "issues").glob("n*.html"))
    else:
        files = [Path(f) for f in args.files]
        # Detectar el directorio raíz para chequeo de registro
        for f in files:
            if "sinapse-site" in str(f):
                site_dir = Path(*f.parts[:f.parts.index("sinapse-site") + 1])
                break
        if not site_dir and files:
            # Asumir que el primer archivo está dentro
            for parent in files[0].parents:
                if (parent / "data" / "registro.json").exists():
                    site_dir = parent
                    break

    if not files:
        print("Sin archivos para validar. Uso: --site sinapse-site/  o pasa archivos.", file=sys.stderr)
        return 1

    print(f"SINAPSE validador · {len(files)} archivo(s) HTML\n")
    overall_fail = False

    for path in files:
        print(f"[{path.name}]")
        results = validate_file(path)
        for r in results:
            print(r)
            if r.is_fail():
                overall_fail = True
        print()

    if site_dir:
        print(f"[registro.json]")
        for r in check_registry(site_dir):
            print(r)
            if r.is_fail():
                overall_fail = True
        print()

    summary = "FAIL" if overall_fail else "OK"
    print(f"Resultado global: {summary}")
    return 1 if overall_fail else 0


if __name__ == "__main__":
    sys.exit(main())
