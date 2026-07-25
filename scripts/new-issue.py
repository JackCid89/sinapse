#!/usr/bin/env python3
"""
SINAPSE · new-issue.py — genera el borrador HTML de un número desde un
único `numero.json` bilingüe, en vez de copiar el número anterior a mano.

Motivo: el ciclo «copiar N-1 y editar» arrastraba datos del número previo
(bugs reales: titulares ES en la home EN, «Por qué importa» duplicado). Con
un generador, la estructura es idéntica por construcción y NO hay restos del
número anterior: cada número parte de su propio JSON de contenido.

    python3 scripts/new-issue.py editorial/numero-006.json --site .

Escribe issues/<es_file> y en/issues/<en_file>. Luego:
    python3 scripts/build.py --site .        # inyecta meta, feed, sitemap…
    python3 scripts/validate-pro.py --site . # gate de publicación

NOTA sobre el mapa del Contraste: si el número es geográfico, el generador
deja el contenedor `.atlas-map-v2` con un comentario-slot. El SVG se sigue
generando aparte con scripts/make-map.py y se pega en ese slot (flujo actual
de CLAUDE.md §3.4). El generador NO dibuja mapas.

Las 7 dimensiones del Atlas son fijas (el validador las exige literales); el
JSON sólo aporta el VALOR de cada una, no el nombre.
"""

import argparse
import html
import json
from pathlib import Path

ATLAS_DIMS = {
    "es": ["Países en el titular", "Países en la trama real", "Quién cobra",
           "Quién paga", "Horizonte 5 / 10 años", "Brecha regulatoria",
           "Punto ciego"],
    "en": ["Countries in the headline", "Countries in the actual story",
           "Who profits", "Who pays", "5 / 10-year horizon",
           "Regulatory gap", "Blind spot"],
}
ATLAS_HEAD = {"es": "Atlas del problema · 7 dimensiones",
              "en": "Atlas of the problem · 7 dimensions"}
SEC_TITLES = {
    "es": ["Pulso", "Portada", "Papers", "Tech", "Industria", "Columna",
           "Contraste", "Dato de la semana", "Apéndice · fichas técnicas"],
    "en": ["Pulse", "Cover", "Papers", "Tech", "Industry", "Column",
           "Counterpoint", "Datum of the week", "Appendix · technical notes"],
}
TOC_LABELS = {
    "es": ["Pulso", "Portada", "Papers", "Tech", "Industria", "Columna",
           "Contraste", "Dato", "Apéndice"],
    "en": ["Pulse", "Cover", "Papers", "Tech", "Industry", "Column",
           "Counterpoint", "Datum", "Appendix"],
}
SEC_IDS = {
    "es": ["pulso", "portada", "papers", "tech", "industria", "columna",
           "contraste", "dato", "apendice"],
    "en": ["pulse", "cover", "papers", "tech", "industry", "column",
           "counterpoint", "datum", "appendix"],
}
CSSV = "20260724f"


def e(s):
    return html.escape(str(s or ""), quote=True)


def raw(s):
    """el contenido ya trae HTML editorial (em, strong, br); se deja crudo."""
    return str(s or "")


# ── secciones ────────────────────────────────────────────────────────────────

def sec_head(n, title):
    return (f'  <div class="sec-head"><span class="sec-num">§ {n:02d}</span>'
            f'<h2 class="sec-title">{e(title)}</h2></div>')


def render_pulso(items, lang, n):
    sid = SEC_IDS[lang]
    out = [f'  <section class="sec" id="{sid[0]}">', sec_head(1, SEC_TITLES[lang][0])]
    for i, it in enumerate(items, 1):
        tags = "".join(f'<span class="tag">{e(t)}</span>' for t in it.get("tags", []))
        enclaro = (f'\n        <aside class="enclaro">{raw(it["enclaro"])}</aside>'
                   if it.get("enclaro") else "")
        out.append(
            '    <article class="pulso-item">\n'
            f'      <div class="pulso-num"><span class="ord">{i:02d}</span>P-{i:02d}</div>\n'
            '      <div class="pulso-body">\n'
            f'        <div class="tags">{tags}</div>\n'
            f'        <h3>{raw(it["titulo"])}</h3>\n'
            f'        <p>{raw(it["cuerpo"])}</p>{enclaro}\n'
            '      </div>\n'
            '    </article>')
    out.append('  </section>')
    return "\n".join(out)


def render_portada(p, lang):
    body = []
    for i, blk in enumerate(p.get("cuerpo", [])):
        if "h3" in blk:
            body.append(f'      <h3>{raw(blk["h3"])}</h3>')
        else:
            cls = ' class="dropcap"' if i == 0 else ""
            body.append(f'      <p{cls}>{raw(blk["p"])}</p>')
    return (f'  <section class="sec" id="{SEC_IDS[lang][1]}">\n' + sec_head(2, SEC_TITLES[lang][1]) + "\n\n"
            f'    <p class="portada-meta">{e(p["meta"])}</p>\n'
            f'    <h1 class="article-title">{raw(p["titulo_html"])}</h1>\n'
            f'    <p class="article-deck">{raw(p["deck"])}</p>\n'
            f'    <p class="byline"><span>{e(p["byline_autor"])}</span>'
            f'<span>{e(p["byline_fecha"])}</span></p>\n\n'
            '    <div class="prose">\n' + "\n\n".join(body) + '\n    </div>\n  </section>')


def render_papers(items, lang):
    out = [f'  <section class="sec" id="{SEC_IDS[lang][2]}">', sec_head(3, SEC_TITLES[lang][2]),
           f'    <p class="sec-desc">{e_desc(lang, "papers")}</p>']
    for it in items:
        tags = "".join(f'<span class="tag">{e(t)}</span>' for t in it.get("tags", []))
        out.append(
            '    <article class="paper">\n'
            f'      <div class="tags">{tags}</div>\n'
            f'      <h3>{raw(it["titulo"])}</h3>\n'
            f'      <p class="cite">{raw(it["cite"])}</p>\n'
            f'      <p>{raw(it["cuerpo"])}</p>\n'
            f'      <p class="why">{raw(it["why"])}</p>\n'
            '    </article>')
    out.append('  </section>')
    return "\n".join(out)


def render_ti(items, lang, sec_i, sec_id):
    out = [f'  <section class="sec" id="{sec_id}">', sec_head(sec_i + 1, SEC_TITLES[lang][sec_i]),
           f'    <p class="sec-desc">{e_desc(lang, sec_id)}</p>', '    <div class="ti-grid">']
    for it in items:
        out.append(
            '      <article class="ti-item">\n'
            f'        <div class="ti-cat">{raw(it["cat"])}</div>\n'
            '        <div class="ti-body">\n'
            f'          <h3>{raw(it["titulo"])}</h3>\n'
            f'          <p>{raw(it["cuerpo"])}</p>\n'
            '        </div>\n'
            '      </article>')
    out.append('    </div>\n  </section>')
    return "\n".join(out)


def render_columna(c, lang):
    body = []
    for i, blk in enumerate(c.get("cuerpo", [])):
        if "h3" in blk:
            body.append(f'      <h3>{raw(blk["h3"])}</h3>')
        else:
            cls = ' class="dropcap"' if i == 0 else ""
            body.append(f'      <p{cls}>{raw(blk["p"])}</p>')
    return (f'  <section class="sec columna" id="{SEC_IDS[lang][5]}">\n' + sec_head(6, SEC_TITLES[lang][5]) + "\n\n"
            f'    <h1 class="article-title">{raw(c["titulo_html"])}</h1>\n'
            f'    <p class="byline"><span>{e(c["byline_autor"])}</span>'
            f'<span>{e(c["byline_fecha"])}</span></p>\n\n'
            '    <div class="prose">\n' + "\n\n".join(body) + '\n    </div>\n  </section>')


def render_contraste(c, lang):
    dims = ATLAS_DIMS[lang]
    vals = c.get("atlas", [])
    rows = "\n".join(f'        <dt>{e(dims[i])}</dt>\n        <dd>{raw(vals[i])}</dd>'
                     for i in range(min(len(dims), len(vals))))
    body = "\n\n".join(f'      <p>{raw(b["p"])}</p>' for b in c.get("cuerpo", []))
    map_block = ""
    if c.get("geografico"):
        map_block = (
            '\n    <div class="atlas-map-v2">\n'
            '      <!-- SLOT MAPA: pegar aquí el <svg data-viz="map"> de make-map.py + <ul class="amap-stats"> -->\n'
            '    </div>\n')
    return (f'  <section class="sec contraste" id="{SEC_IDS[lang][6]}">\n' + sec_head(7, SEC_TITLES[lang][6]) + "\n\n"
            f'    <h1 class="article-title">{raw(c["titulo_html"])}</h1>\n'
            f'    <p class="article-deck">{raw(c["deck"])}</p>\n'
            f'    <p class="byline"><span>{e(c["byline_autor"])}</span>'
            f'<span>{e(c["byline_fecha"])}</span></p>\n{map_block}\n'
            '    <div class="prose">\n' + body + '\n    </div>\n\n'
            '    <div class="atlas">\n'
            f'      <div class="atlas-head">{e(ATLAS_HEAD[lang])}</div>\n'
            '      <dl>\n' + rows + '\n      </dl>\n    </div>\n  </section>')


def render_dato(d, lang):
    return (f'  <section class="sec" id="{SEC_IDS[lang][7]}">\n' + sec_head(8, SEC_TITLES[lang][7]) + "\n\n"
            '    <div class="dato">\n'
            f'      <p class="dato-num">{raw(d["num_html"])}</p>\n'
            f'      <p class="dato-lbl">{raw(d["lbl"])}</p>\n'
            f'      <p class="dato-body">{raw(d["body_html"])}</p>\n'
            '    </div>\n  </section>')


def render_apendice(items, lang):
    out = [f'  <section class="sec" id="{SEC_IDS[lang][8]}">', sec_head(9, SEC_TITLES[lang][8]),
           f'    <p class="sec-desc">{e_desc(lang, "apendice")}</p>']
    lbl = {"es": ("Disciplina", "Región", "Publicación", "Resumen", "Metodología",
                  "Limitaciones", "Enlace"),
           "en": ("Discipline", "Region", "Publication", "Summary", "Methodology",
                  "Limitations", "Link")}[lang]
    for it in items:
        out.append(
            '    <article class="appendix-paper">\n'
            f'      <h3><span class="pnum">{e(it["pnum"])}</span>{raw(it["titulo"])}</h3>\n'
            '      <div class="appendix-meta">\n'
            f'        <div>{lbl[0]}<strong>{raw(it["disciplina"])}</strong></div>\n'
            f'        <div>{lbl[1]}<strong>{raw(it["region"])}</strong></div>\n'
            f'        <div>{lbl[2]}<strong>{raw(it["publicacion"])}</strong></div>\n'
            '      </div>\n'
            '      <dl>\n'
            f'        <dt>{lbl[3]}</dt><dd>{raw(it["resumen"])}</dd>\n'
            f'        <dt>{lbl[4]}</dt><dd>{raw(it["metodologia"])}</dd>\n'
            f'        <dt>{lbl[5]}</dt><dd>{raw(it["limitaciones"])}</dd>\n'
            f'        <dt>{lbl[6]}</dt><dd><a href="{e(it["enlace_url"])}" target="_blank" '
            f'rel="noopener">{e(it["enlace_text"])}</a></dd>\n'
            '      </dl>\n    </article>')
    out.append('  </section>')
    return "\n".join(out)


DESCS = {
    "es": {"papers": "Lecturas comentadas de la semana.",
           "tech": "Lo que se mueve en hardware, software e infraestructura esta semana.",
           "industria": "Capital, cadenas y capacidad.",
           "apendice": "Detalle de los papers de la sección 03."},
    "en": {"papers": "Annotated reads of the week.",
           "tech": "What's moving in hardware, software and infrastructure this week.",
           "industria": "Capital, supply chains and capacity.",
           "apendice": "Detail on the papers from section 03."},
}


def e_desc(lang, key):
    norm = {"industry": "industria", "appendix": "apendice", "cover": "portada",
            "counterpoint": "contraste", "datum": "dato", "pulse": "pulso",
            "column": "columna"}.get(key, key)
    return e(DESCS[lang].get(norm, ""))


# ── documento completo ───────────────────────────────────────────────────────

def toc(lang):
    lis = []
    for i, (sid, lab) in enumerate(zip(SEC_IDS[lang], TOC_LABELS[lang]), 1):
        lis.append(f'      <li><a href="#{sid}"><span class="num">{i:02d}</span>'
                   f'<span class="lead"></span><span>{e(lab)}</span></a></li>')
    label = "Índice" if lang == "es" else "Contents"
    return (f'  <nav class="toc" aria-label="{label}">\n    <ol>\n'
            + "\n".join(lis) + '\n    </ol>\n  </nav>')


def document(meta, lang, audio_rel=None):
    c = meta[lang]
    num3 = str(meta["numero"]).zfill(3)
    label = f"No. {num3}" if lang == "en" else f"N.º {num3}"
    title_tag = (f"SINAPSE · {label} · {meta.get('titulo_mes', '')}").strip(" ·")
    up = "../" if lang == "es" else "../../"
    other = (f'../en/issues/{meta["en_file"]}' if lang == "es"
             else f'../../issues/{meta["es_file"]}')
    self_href = f'./{meta["es_file"]}' if lang == "es" else f'./{meta["en_file"]}'
    body_open = (f'<body data-audio="{audio_rel}">' if (lang == "en" and audio_rel)
                 else "<body>")
    listen = (f'\n<script src="{up}assets/listen-mode.js?v={CSSV}" defer></script>'
              if (lang == "en" and audio_rel) else "")
    sub_science = "Ciencia · Tecnología · Industria" if lang == "es" else "Science · Technology · Industry"
    edic = (f"Edición semanal · español" if lang == "es" else "Weekly edition · English")

    sections = "\n\n".join([
        render_pulso(c["pulso"], lang, meta["numero"]),
        render_portada(c["portada"], lang),
        render_papers(c["papers"], lang),
        render_ti(c["tech"], lang, 3, SEC_IDS[lang][3]),
        render_ti(c["industria"], lang, 4, SEC_IDS[lang][4]),
        render_columna(c["columna"], lang),
        render_contraste(c["contraste"], lang),
        render_dato(c["dato"], lang),
        render_apendice(c["apendice"], lang),
    ])

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{e(title_tag)}</title>
<meta name="description" content="{e(c.get('description',''))}" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,300..900;1,8..60,300..900&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
<link rel="stylesheet" href="{up}assets/sinapse.css?v={CSSV}" />
</head>
{body_open}

<div class="progress" aria-hidden="true"><div class="bar" id="progBar"></div></div>

<main class="page" id="top">

  <header class="masthead">
    <h1 class="wordmark"><a href="{up}index.html">sinapse<span class="dot">.</span></a></h1>
    <div class="meta">
      <strong>{label}</strong><br>
      {e(c.get('masthead_semana',''))}<br>
      {edic}
    </div>
  </header>

  <div class="sub">
    <span>{sub_science}</span>
    <span class="lang">
      <a href="{self_href}" aria-current="page">{('ES' if lang=='es' else 'EN')}</a> · <a href="{other}">{('EN' if lang=='es' else 'ES')}</a>
    </span>
  </div>

  <p class="lede">
    {raw(c['lede'])}
  </p>

{toc(lang)}

{sections}

  <footer class="colofon">
    <p><strong>SINAPSE</strong> — {('revista semanal de ciencia, tecnología e industria.' if lang=='es' else 'weekly magazine of science, technology, and industry.')}</p>
    <p>{('Editor: Jack Cid · publicado vía GitHub Pages · sin tracking, sin cookies.' if lang=='es' else 'Editor: Jack Cid · published via GitHub Pages · no tracking, no cookies.')}</p>
  </footer>

</main>

<script src="{up}assets/reader-preferences.js?v={CSSV}" defer></script>
<script src="{up}assets/toc-observer.js?v={CSSV}" defer></script>{listen}
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("numero_json")
    ap.add_argument("--site", default=".")
    ap.add_argument("--out", default=None,
                    help="dir alterno de salida (para borradores; por defecto el repo)")
    args = ap.parse_args()
    site = Path(args.site).resolve()
    meta = json.loads(Path(args.numero_json).read_text(encoding="utf-8"))

    audio_rel = None
    if meta.get("audio"):
        audio_rel = f'../../assets/audio/{meta["en_file"].replace(".html", ".mp3")}?v={CSSV}'

    es_html = document(meta, "es")
    en_html = document(meta, "en", audio_rel=audio_rel)

    if args.out:
        base = Path(args.out)
        (base / "issues").mkdir(parents=True, exist_ok=True)
        (base / "en" / "issues").mkdir(parents=True, exist_ok=True)
        es_path = base / "issues" / meta["es_file"]
        en_path = base / "en" / "issues" / meta["en_file"]
    else:
        es_path = site / "issues" / meta["es_file"]
        en_path = site / "en" / "issues" / meta["en_file"]

    es_path.write_text(es_html, encoding="utf-8")
    en_path.write_text(en_html, encoding="utf-8")
    print(f"  ✓ {es_path}")
    print(f"  ✓ {en_path}")
    print("Siguiente: si es geográfico, pegá el SVG de make-map.py en .atlas-map-v2;")
    print("luego  python3 scripts/build.py --site .  y  validate-pro.py --site .")


if __name__ == "__main__":
    main()
