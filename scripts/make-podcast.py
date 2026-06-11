#!/usr/bin/env python3
"""
SINAPSE · make-podcast.py — pipeline de audio (la revista como podcast).

Convierte un número HTML en (1) un guion de narración y (2) opcionalmente un
MP3 con voces neuronales. Diseñado para el plan híbrido: el sitio usa la voz
del navegador por defecto y, si existe assets/audio/n00N-{es,en}.mp3, el
reproductor lo prefiere.

Uso:
  # Solo guion + estimación de costo (sin red, sin API key):
  python3 scripts/make-podcast.py issues/n004-mayo-2026.html --dry-run

  # Generar MP3 con OpenAI TTS (export OPENAI_API_KEY=...):
  python3 scripts/make-podcast.py issues/n004-mayo-2026.html \
      --engine openai --voice nova --out assets/audio/n004-es.mp3

Costos de referencia (junio 2026): OpenAI TTS ≈ $15 / millón de caracteres;
ElevenLabs Flash ≈ $60 / M; Multilingual ≈ $120 / M; Google/Polly estándar ≈ $4 / M.
Un número SINAPSE ronda 7–9 k caracteres ⇒ ~$0.11–0.14 por idioma con OpenAI.

Solo stdlib (html.parser, urllib). El MP3 multi-trozo se concatena binario
(válido para MP3 CBR del mismo encoder); si hay ffmpeg, se usa para re-mux.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# ── Extracción de texto narrable ─────────────────────────────────────────────

VOID_TAGS = {"br", "img", "hr", "meta", "link", "input", "source", "wbr"}
SKIP_TAGS = {"script", "style", "nav", "svg", "figure", "aside"}
BLOCK_TAGS = {"h1", "h2", "h3", "p", "li", "dt", "dd", "blockquote"}
# Clases cuyo subárbol NO se narra (metadata visual, charts, navegación).
SKIP_CLASSES = {"toc", "reader-prefs", "tags", "chart", "atlas-map",
                "bars", "bar-row", "refs", "masthead-meta", "sec-num",
                "pulso-num", "ti-cat", "ord", "pnum"}


class Extractor(HTMLParser):
    """Recorre el HTML y produce [(section_id, tag, texto)] en orden.

    Usa una pila de tags para saber exactamente cuándo termina un subárbol
    saltado por clase (un <div class="tags">…</div> cierra con su </div>),
    evitando el bug de un skip_depth que nunca baja."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.section = None
        self.stack = []          # [(tag, skip_bool)]
        self.skip_depth = 0
        self.cur_tag = None
        self.buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if tag == "section" and a.get("id"):
            self.section = a["id"]

        skip_here = (tag in SKIP_TAGS) or bool(classes & SKIP_CLASSES)
        if tag not in VOID_TAGS:
            self.stack.append((tag, skip_here))
        if skip_here:
            self.skip_depth += 1
            return
        if self.skip_depth == 0 and tag in BLOCK_TAGS:
            self._flush()
            self.cur_tag = tag

    def handle_startendtag(self, tag, attrs):
        pass  # self-closing: nada que narrar

    def handle_endtag(self, tag):
        if self.cur_tag and tag == self.cur_tag:
            self._flush()
        # Desapilar hasta (e incluyendo) el tag que cierra.
        while self.stack:
            t, skip = self.stack.pop()
            if skip:
                self.skip_depth = max(0, self.skip_depth - 1)
            if t == tag:
                break

    def handle_data(self, data):
        if self.skip_depth == 0 and self.cur_tag:
            self.buf.append(data)

    def _flush(self):
        if self.buf and self.cur_tag:
            text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if len(text) > 2:
                self.out.append((self.section, self.cur_tag, text))
        self.buf, self.cur_tag = [], None


SECTION_INTROS_ES = {
    "pulso": "Pulso. La semana en señales.",
    "portada": "Portada.",
    "papers": "Papers de la semana.",
    "tech": "Tecnología.",
    "industria": "Industria.",
    "columna": "La columna.",
    "contraste": "Contraste, por Passiflora Caerulea.",
    "dato": "El dato de la semana.",
    "apendice": "Apéndice metodológico.",
}
SECTION_INTROS_EN = {
    "pulse": "Pulse. The week in signals.", "cover": "Cover story.",
    "papers": "Papers of the week.", "tech": "Technology.",
    "industry": "Industry.", "column": "The column.",
    "counterpoint": "Counterpoint, by Passiflora Caerulea.",
    "datum": "Datum of the week.", "appendix": "Methodological appendix.",
}


def build_script(html: str):
    en = bool(re.search(r'<html[^>]*\blang="en"', html))
    intros = SECTION_INTROS_EN if en else SECTION_INTROS_ES
    ex = Extractor()
    ex.feed(html)
    ex._flush()

    title = next((t for s, tag, t in ex.out if tag == "h1"), "SINAPSE")
    title = re.sub(r"^sinapse[\s.·—-]*", "", title, flags=re.I).strip(" .·—-") or "el número de esta semana"
    parts, seen = [], set()
    if en:
        parts.append(f"This is SINAPSE, your weekly science and technology review. {title}.")
    else:
        parts.append(f"Esto es SINAPSE, tu revista semanal de ciencia y tecnología. {title}.")

    for sec, tag, text in ex.out:
        if tag == "h1":
            continue
        if sec and sec not in seen and sec in intros:
            seen.add(sec)
            parts.append("")           # pausa
            parts.append(intros[sec])
        parts.append(text)

    parts.append("")
    parts.append("Thanks for listening. SINAPSE returns next Tuesday."
                 if en else
                 "Gracias por escuchar. SINAPSE vuelve el próximo martes.")
    return "\n".join(parts), ("en" if en else "es")


# ── Motores TTS ──────────────────────────────────────────────────────────────

def tts_openai(text: str, voice: str, out_path: Path, model="gpt-4o-mini-tts"):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("Falta OPENAI_API_KEY en el entorno.")
    chunks, cur = [], ""
    for para in text.split("\n"):
        if len(cur) + len(para) > 3800:
            chunks.append(cur)
            cur = para
        else:
            cur += ("\n" if cur else "") + para
    if cur:
        chunks.append(cur)

    seg_files = []
    for i, chunk in enumerate(chunks):
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/speech",
            data=json.dumps({"model": model, "voice": voice,
                             "input": chunk, "response_format": "mp3"}).encode(),
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"})
        seg = out_path.with_suffix(f".part{i}.mp3")
        with urllib.request.urlopen(req, timeout=120) as r:
            seg.write_bytes(r.read())
        seg_files.append(seg)
        print(f"  · segmento {i + 1}/{len(chunks)} ({len(chunk)} chars)")

    if shutil.which("ffmpeg") and len(seg_files) > 1:
        lst = out_path.with_suffix(".list.txt")
        lst.write_text("".join(f"file '{s.resolve()}'\n" for s in seg_files))
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c", "copy", str(out_path)],
                       check=True, capture_output=True)
        lst.unlink()
    else:
        out_path.write_bytes(b"".join(s.read_bytes() for s in seg_files))
    for s in seg_files:
        s.unlink()


# ── CLI ──────────────────────────────────────────────────────────────────────

PRICES = {"openai": 15, "elevenlabs-flash": 60, "elevenlabs-multi": 120,
          "google-standard": 4}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("issue", help="HTML del número (ES o EN)")
    p.add_argument("--engine", choices=["openai"], default=None)
    p.add_argument("--voice", default="nova",
                   help="OpenAI: alloy/echo/nova/onyx/shimmer…")
    p.add_argument("--out", default=None, help="MP3 de salida")
    p.add_argument("--dry-run", action="store_true",
                   help="solo guion + costo estimado")
    args = p.parse_args()

    html = Path(args.issue).read_text(encoding="utf-8")
    script, lang = build_script(html)
    n_chars = len(script)

    guion = Path(args.issue).with_suffix(f".guion-{lang}.txt")
    guion.write_text(script, encoding="utf-8")
    print(f"Guion → {guion}  ({n_chars:,} caracteres, ~{n_chars // 950} min de audio)")
    print("Costo: $0.00 — la síntesis es local (sinapse-tts-mac.py · Chatterbox/Kokoro).")
    if os.environ.get("SHOW_CLOUD_PRICES"):
        print("Referencia nube (si algún día se usa --engine openai):")
        for name, usd_m in PRICES.items():
            print(f"  {name:<18} ${n_chars * usd_m / 1e6:.3f}")

    if args.dry_run or not args.engine:
        return

    out = Path(args.out or Path(args.issue).with_suffix(f"-{lang}.mp3"))
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Generando MP3 con {args.engine} (voz {args.voice}) → {out}")
    tts_openai(script, args.voice, out)
    print(f"OK → {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
