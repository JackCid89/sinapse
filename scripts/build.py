#!/usr/bin/env python3
"""
SINAPSE · build.py — genera artefactos derivados desde data/registro.json.

Idempotente y seguro: NO reescribe el cuerpo de los números. Sólo (a) inyecta
un bloque de <head> gestionado (canonical, hreflang, Open Graph, Twitter,
theme-color, favicon, JSON-LD y autodiscovery de feed) entre marcadores, (b)
pre-renderiza la lista de números en las dos home (progressive enhancement:
el JS sigue hidratando encima), (c) genera feed.xml (ES) y en/feed.xml (EN),
(d) genera sitemap.xml y robots.txt, (e) genera tarjetas sociales PNG por
número (si PIL está disponible; si no, degrada sin romper).

    python3 scripts/build.py --site .

Correr al final del ciclo semanal, DESPUÉS de escribir el número y ANTES de
validar. La validación (validate-pro.py) verifica el resultado.
"""

import argparse
import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

BASE = "https://jackcid89.github.io/sinapse/"
SITE_NAME = "SINAPSE"
AUTHOR = "Jack Cid"
THEME_COLOR = "#f6f6f9"          # paper aurora (chrome del navegador)
ACCENT_HEX = "#4b46c8"           # aproximación del acento aurora para tarjetas

MARK_START = "<!-- sinapse:meta v1 · generado por build.py, no editar a mano -->"
MARK_END = "<!-- /sinapse:meta -->"
LIST_START = "<!-- sinapse:issues v1 -->"
LIST_END = "<!-- /sinapse:issues -->"


# ── utilidades ──────────────────────────────────────────────────────────────

def esc(s):
    return html.escape(str(s or ""), quote=True)


def rfc3339(d: str) -> str:
    """fecha ISO (martes de publicación) → timestamp RFC3339 a las 12:00 UTC."""
    return datetime.fromisoformat(d).replace(hour=12, tzinfo=timezone.utc).isoformat()


def issue_url(lang, archivo):
    return BASE + ("issues/" if lang == "es" else "en/issues/") + archivo


def home_url(lang):
    return BASE + ("" if lang == "es" else "en/")


def load_registry(site: Path):
    return json.loads((site / "data" / "registro.json").read_text(encoding="utf-8"))


def numeros_desc(reg):
    return sorted(reg.get("numeros", []), key=lambda n: n["numero"], reverse=True)


def issue_meta(n):
    """normaliza los campos ES/EN de un número del registro."""
    es = n.get("portada", {})
    en = (n.get("i18n", {}).get("en", {}) or {})
    en_p = en.get("portada", {}) or es
    return {
        "numero": n["numero"],
        "num3": str(n["numero"]).zfill(3),
        "fecha": n.get("fecha", ""),
        "es_file": n["archivo"],
        "en_file": en.get("archivo") or n["archivo"],
        "es_title": es.get("titulo", ""),
        "en_title": en_p.get("titulo", es.get("titulo", "")),
        "es_disc": es.get("disciplina", ""),
        "en_disc": en_p.get("disciplina", es.get("disciplina", "")),
    }


# ── (a) bloque de <head> gestionado ─────────────────────────────────────────

def meta_block_issue(m, lang):
    title = m["en_title"] if lang == "en" else m["es_title"]
    disc = m["en_disc"] if lang == "en" else m["es_disc"]
    es_u, en_u = issue_url("es", m["es_file"]), issue_url("en", m["en_file"])
    self_u = en_u if lang == "en" else es_u
    locale = "en_US" if lang == "en" else "es_ES"
    alt_locale = "es_ES" if lang == "en" else "en_US"
    label = f"No. {m['num3']}" if lang == "en" else f"N.º {m['num3']}"
    desc = f"{label} · {title} — {disc}."
    og_img = BASE + f"assets/og/n{m['num3']}-{lang}.png"
    published = rfc3339(m["fecha"]) if m["fecha"] else ""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "inLanguage": lang,
        "datePublished": m["fecha"],
        "articleSection": disc,
        "isPartOf": {"@type": "Periodical", "name": SITE_NAME},
        "author": {"@type": "Person", "name": AUTHOR},
        "publisher": {"@type": "Organization", "name": SITE_NAME},
        "mainEntityOfPage": self_u,
        "image": og_img,
    }
    lines = [
        MARK_START,
        f'<link rel="canonical" href="{esc(self_u)}" />',
        f'<link rel="alternate" hreflang="es" href="{esc(es_u)}" />',
        f'<link rel="alternate" hreflang="en" href="{esc(en_u)}" />',
        f'<link rel="alternate" hreflang="x-default" href="{esc(es_u)}" />',
        f'<meta name="theme-color" content="{THEME_COLOR}" />',
        '<link rel="icon" href="' + BASE + 'assets/favicon.svg" type="image/svg+xml" />',
        f'<meta property="og:type" content="article" />',
        f'<meta property="og:site_name" content="{SITE_NAME}" />',
        f'<meta property="og:locale" content="{locale}" />',
        f'<meta property="og:locale:alternate" content="{alt_locale}" />',
        f'<meta property="og:title" content="{esc(title)}" />',
        f'<meta property="og:description" content="{esc(desc)}" />',
        f'<meta property="og:url" content="{esc(self_u)}" />',
        f'<meta property="og:image" content="{esc(og_img)}" />',
        f'<meta property="article:published_time" content="{esc(published)}" />',
        f'<meta property="article:section" content="{esc(disc)}" />',
        f'<meta property="article:author" content="{AUTHOR}" />',
        f'<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{esc(title)}" />',
        f'<meta name="twitter:description" content="{esc(desc)}" />',
        f'<meta name="twitter:image" content="{esc(og_img)}" />',
        '<script type="application/ld+json">' +
        json.dumps(jsonld, ensure_ascii=False) + "</script>",
        MARK_END,
    ]
    return "\n".join(lines)


def meta_block_home(lang):
    self_u = home_url(lang)
    es_u, en_u = home_url("es"), home_url("en")
    locale = "en_US" if lang == "en" else "es_ES"
    if lang == "en":
        title = "SINAPSE — weekly magazine of science, technology, and industry"
        desc = "Weekly magazine in English on science, technology, and industry. No hype, with context, paper-first."
        feed = "./feed.xml"
    else:
        title = "SINAPSE — revista semanal de ciencia, tecnología e industria"
        desc = "Revista semanal en español sobre ciencia, tecnología e industria. Sin hype, con contexto, paper-first."
        feed = "./feed.xml"
    og_img = BASE + "assets/og/home.png"
    lines = [
        MARK_START,
        f'<link rel="canonical" href="{esc(self_u)}" />',
        f'<link rel="alternate" hreflang="es" href="{esc(es_u)}" />',
        f'<link rel="alternate" hreflang="en" href="{esc(en_u)}" />',
        f'<link rel="alternate" hreflang="x-default" href="{esc(es_u)}" />',
        f'<meta name="theme-color" content="{THEME_COLOR}" />',
        '<link rel="icon" href="./assets/favicon.svg" type="image/svg+xml" />'
        if lang == "es" else
        '<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml" />',
        f'<link rel="alternate" type="application/atom+xml" title="SINAPSE ({lang})" href="{feed}" />',
        f'<meta property="og:type" content="website" />',
        f'<meta property="og:site_name" content="{SITE_NAME}" />',
        f'<meta property="og:locale" content="{locale}" />',
        f'<meta property="og:title" content="{esc(title)}" />',
        f'<meta property="og:description" content="{esc(desc)}" />',
        f'<meta property="og:url" content="{esc(self_u)}" />',
        f'<meta property="og:image" content="{esc(og_img)}" />',
        f'<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{esc(title)}" />',
        f'<meta name="twitter:description" content="{esc(desc)}" />',
        f'<meta name="twitter:image" content="{esc(og_img)}" />',
        MARK_END,
    ]
    return "\n".join(lines)


def inject_block(path: Path, block: str, start=MARK_START, end=MARK_END):
    txt = path.read_text(encoding="utf-8")
    if start in txt and end in txt:
        new = re.sub(re.escape(start) + r".*?" + re.escape(end), block, txt,
                     flags=re.DOTALL)
    else:
        # insertar tras la etiqueta <meta name="description" ...>
        m = re.search(r'<meta name="description"[^>]*>\s*', txt)
        anchor = m.end() if m else txt.index("</head>")
        new = txt[:anchor] + block + "\n" + txt[anchor:]
    if new != txt:
        path.write_text(new, encoding="utf-8")
        return True
    return False


# ── (b) pre-render de la lista de números en las home ───────────────────────

def render_list_static(items, lang):
    rows = []
    for m in items:
        num = m["num3"]
        if lang == "en":
            href = f"./issues/{m['en_file']}"
            kicker, title, disc = f"Issue {num}", m["en_title"], m["en_disc"]
        else:
            href = f"./issues/{m['es_file']}"
            kicker, title, disc = f"N.º {num}", m["es_title"], m["es_disc"]
        rows.append(
            f'<a href="{esc(href)}" style="display:grid;grid-template-columns:90px 1fr 180px;'
            'gap:18px;padding:18px 0;border-bottom:1px solid var(--rule-2);align-items:baseline;'
            'text-decoration:none;color:var(--ink)">'
            f'<div style="font-family:var(--mono);font-size:13px;color:var(--accent);'
            f'letter-spacing:.1em;text-transform:uppercase">{esc(kicker)}</div>'
            '<div>'
            f'<h3 style="font-family:var(--display);font-style:italic;font-size:24px;'
            f'margin:0 0 6px;font-weight:400;line-height:1.25;color:var(--ink)">{esc(title)}</h3>'
            f'<div style="font-family:var(--mono);font-size:11px;color:var(--ink-3);'
            f'letter-spacing:.05em">{esc(disc)}</div></div>'
            f'<div style="font-family:var(--mono);font-size:12px;text-align:right;'
            f'color:var(--ink-3)">{esc(m["fecha"])}</div></a>'
        )
    return "\n".join(rows)


def prerender_home(path: Path, items, lang):
    n = len(items)
    if lang == "en":
        meta_txt = f"{n} issue{'s' if n != 1 else ''} in archive."
    else:
        meta_txt = f"{n} número{'s' if n != 1 else ''} en archivo."
    listing = LIST_START + "\n" + render_list_static(items, lang) + "\n" + LIST_END
    txt = path.read_text(encoding="utf-8")
    # lista dentro de #issue-list (replacements por función: evita colisión con \g)
    if LIST_START in txt:
        txt = re.sub(re.escape(LIST_START) + r".*?" + re.escape(LIST_END),
                     lambda _: listing, txt, flags=re.DOTALL)
    else:
        txt = re.sub(r'<div id="issue-list">\s*</div>',
                     lambda _: f'<div id="issue-list">\n{listing}\n</div>',
                     txt, count=1)
    # texto de #meta-line (server-rendered; el JS lo re-escribe)
    txt = re.sub(r'(<p class="sec-desc" id="meta-line">).*?(</p>)',
                 lambda _: f'<p class="sec-desc" id="meta-line">{esc(meta_txt)}</p>',
                 txt, count=1, flags=re.DOTALL)
    path.write_text(txt, encoding="utf-8")


# ── (c) feeds Atom ──────────────────────────────────────────────────────────

def build_feed(items, lang):
    self_u = home_url(lang) + "feed.xml"
    site_u = home_url(lang)
    title = "SINAPSE" + ("" if lang == "es" else " (EN)")
    subtitle = ("revista semanal de ciencia, tecnología e industria" if lang == "es"
                else "weekly magazine of science, technology, and industry")
    updated = rfc3339(items[0]["fecha"]) if items else datetime.now(timezone.utc).isoformat()
    entries = []
    for m in items:
        u = issue_url(lang, m["en_file"] if lang == "en" else m["es_file"])
        t = m["en_title"] if lang == "en" else m["es_title"]
        d = m["en_disc"] if lang == "en" else m["es_disc"]
        entries.append(
            "  <entry>\n"
            f"    <title>{esc(t)}</title>\n"
            f'    <link href="{esc(u)}" />\n'
            f"    <id>{esc(u)}</id>\n"
            f"    <updated>{rfc3339(m['fecha'])}</updated>\n"
            f"    <published>{rfc3339(m['fecha'])}</published>\n"
            f"    <category term=\"{esc(d)}\" />\n"
            f"    <author><name>{AUTHOR}</name></author>\n"
            f"    <summary>{esc(d)}</summary>\n"
            "  </entry>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <title>{esc(title)}</title>\n"
        f"  <subtitle>{esc(subtitle)}</subtitle>\n"
        f'  <link href="{esc(site_u)}" />\n'
        f'  <link rel="self" href="{esc(self_u)}" />\n'
        f"  <id>{esc(site_u)}</id>\n"
        f"  <updated>{updated}</updated>\n"
        f"  <author><name>{AUTHOR}</name></author>\n"
        + "\n".join(entries) + "\n</feed>\n"
    )


# ── (d) sitemap + robots ────────────────────────────────────────────────────

def build_sitemap(items):
    def url(loc, es_alt, en_alt):
        return (
            "  <url>\n"
            f"    <loc>{esc(loc)}</loc>\n"
            f'    <xhtml:link rel="alternate" hreflang="es" href="{esc(es_alt)}" />\n'
            f'    <xhtml:link rel="alternate" hreflang="en" href="{esc(en_alt)}" />\n'
            f'    <xhtml:link rel="alternate" hreflang="x-default" href="{esc(es_alt)}" />\n'
            "  </url>"
        )
    rows = [url(home_url("es"), home_url("es"), home_url("en")),
            url(home_url("en"), home_url("es"), home_url("en"))]
    for m in items:
        es_u, en_u = issue_url("es", m["es_file"]), issue_url("en", m["en_file"])
        rows.append(url(es_u, es_u, en_u))
        rows.append(url(en_u, es_u, en_u))
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(rows) + "\n</urlset>\n"
    )


def build_robots():
    return (
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {BASE}sitemap.xml\n"
    )


# ── (e) tarjetas sociales PNG (opcional, degrada sin PIL) ────────────────────

def build_og_cards(site: Path, items):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("  – PIL no disponible; se omiten las tarjetas OG (og:image apuntará a PNG ausente)")
        return
    outdir = site / "assets" / "og"
    outdir.mkdir(parents=True, exist_ok=True)

    def font(paths, size):
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
        return ImageFont.load_default()

    SERIF = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
             "/usr/share/fonts/truetype/lato/Lato-Medium.ttf"]
    MONO = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/lato/Lato-Medium.ttf"]
    W, H, PAD = 1200, 630, 80
    PAPER, INK, INK3 = (246, 246, 249), (34, 34, 48), (120, 120, 140)
    ACCENT = (75, 70, 200)

    def wrap(draw, text, fnt, maxw):
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=fnt) <= maxw:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines[:4]

    def card(path, kicker, title, disc):
        img = Image.new("RGB", (W, H), PAPER)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 14, H], fill=ACCENT)
        f_word = font(SERIF, 46)
        f_kick = font(MONO, 26)
        f_title = font(SERIF, 64)
        f_disc = font(MONO, 24)
        d.text((PAD, PAD), "sinapse", font=f_word, fill=INK)
        wl = d.textlength("sinapse", font=f_word)
        d.text((PAD + wl, PAD), ".", font=f_word, fill=ACCENT)
        d.text((PAD, PAD + 70), kicker, font=f_kick, fill=ACCENT)
        y = 250
        for line in wrap(d, title, f_title, W - 2 * PAD):
            d.text((PAD, y), line, font=f_title, fill=INK)
            y += 78
        d.text((PAD, H - PAD - 6), disc.upper(), font=f_disc, fill=INK3)
        img.save(path, "PNG")

    for m in items:
        card(outdir / f"n{m['num3']}-es.png",
             f"N.º {m['num3']} · {m['fecha']}", m["es_title"], m["es_disc"])
        card(outdir / f"n{m['num3']}-en.png",
             f"No. {m['num3']} · {m['fecha']}", m["en_title"], m["en_disc"])
    # tarjeta genérica de la home
    card(outdir / "home.png", "revista semanal",
         "Ciencia, tecnología e industria", "sin hype · con contexto · paper-first")
    print(f"  ✓ {len(items) * 2 + 1} tarjetas OG en assets/og/")


# ── favicon ─────────────────────────────────────────────────────────────────

FAVICON = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="#f6f6f9"/>
  <text x="10" y="46" font-family="Georgia, 'Times New Roman', serif" font-style="italic"
        font-size="40" fill="#222230">s<tspan fill="#4b46c8">.</tspan></text>
</svg>
'''


def write_favicon(site: Path):
    p = site / "assets" / "favicon.svg"
    if not p.exists() or p.read_text(encoding="utf-8") != FAVICON:
        p.write_text(FAVICON, encoding="utf-8")
        return True
    return False


# ── main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=".")
    ap.add_argument("--no-og", action="store_true", help="no regenerar tarjetas PNG")
    args = ap.parse_args()
    site = Path(args.site).resolve()
    reg = load_registry(site)
    items = [issue_meta(n) for n in numeros_desc(reg)]

    print(f"\nSINAPSE · build · {site}\n")

    # (a) meta en cada número
    changed = 0
    for m in items:
        for lang, rel in (("es", f"issues/{m['es_file']}"),
                          ("en", f"en/issues/{m['en_file']}")):
            f = site / rel
            if f.exists() and inject_block(f, meta_block_issue(m, lang)):
                changed += 1
    print(f"  ✓ meta inyectada/actualizada en números ({changed} archivos tocados)")

    # (a) meta en las home
    for lang, rel in (("es", "index.html"), ("en", "en/index.html")):
        f = site / rel
        if f.exists():
            inject_block(f, meta_block_home(lang))
            prerender_home(f, items, lang)
    print("  ✓ meta + lista pre-renderizada en index.html y en/index.html")

    # (c) feeds
    (site / "feed.xml").write_text(build_feed(items, "es"), encoding="utf-8")
    (site / "en").mkdir(exist_ok=True)
    (site / "en" / "feed.xml").write_text(build_feed(items, "en"), encoding="utf-8")
    print("  ✓ feed.xml (ES) y en/feed.xml (EN)")

    # (d) sitemap + robots
    (site / "sitemap.xml").write_text(build_sitemap(items), encoding="utf-8")
    (site / "robots.txt").write_text(build_robots(), encoding="utf-8")
    print("  ✓ sitemap.xml y robots.txt")

    # favicon
    write_favicon(site)
    print("  ✓ assets/favicon.svg")

    # (e) tarjetas OG
    if not args.no_og:
        build_og_cards(site, items)

    print("\nbuild OK\n")


if __name__ == "__main__":
    main()
