#!/usr/bin/env python3
"""
SINAPSE · sinapse-tts-mac.py — síntesis local en Apple Silicon (M4 Pro).

Convierte el guion generado por make-podcast.py (--dry-run) en un MP3 usando
modelos 100% locales. Dos motores:

  chatterbox  Chatterbox Multilingual (ResembleAI, MIT, 23 idiomas incl. es)
              → la mejor calidad local; corre en MPS (GPU del M4 Pro).
              Permite FIJAR LA VOZ de la revista con --ref voz.wav (clonado):
              graba 10-20 s de una voz (o usa una libre) y todos los números
              sonarán igual. ~1-2× tiempo real en M4 Pro; un número de 23 min
              tarda ~25-45 min. RAM: ~6-8 GB (sobra con 24 GB).

  kokoro      Kokoro-82M (Apache-2.0) vía ONNX → 82M params, ~6× más rápido
              que tiempo real INCLUSO en CPU; voces es: ef_dora / em_alex /
              em_santa. Calidad muy digna, prosodia más plana.

Instalación (una vez, en el Mac):

    python3 -m venv ~/.venvs/sinapse-tts && source ~/.venvs/sinapse-tts/bin/activate

    # Motor calidad (Chatterbox en MPS):
    pip install chatterbox-tts torch torchaudio

    # Motor rápido (Kokoro ONNX):
    pip install kokoro-onnx soundfile
    curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
    curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

    # ffmpeg para el MP3 final:
    brew install ffmpeg

Uso (ciclo semanal):

    python3 scripts/make-podcast.py issues/n005-junio-2026.html --dry-run
    python3 sinapse-tts-mac.py issues/n005-junio-2026.guion-es.txt \
        --engine chatterbox --lang es --ref editorial/voces/sinapse-es.wav \
        --out sinapse/assets/audio/n005-es.mp3

La primera ejecución descarga los pesos de Chatterbox (~4 GB) a ~/.cache/huggingface.
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_CHARS = 280   # Chatterbox rinde mejor con trozos cortos


def chunk_text(text: str, max_chars=MAX_CHARS):
    """Párrafos → frases → trozos ≤ max_chars (corta en comas si hace falta)."""
    chunks = []
    for para in [p.strip() for p in text.split("\n") if p.strip()]:
        sentences = re.findall(r"[^.!?…]+[.!?…]+\s*|[^.!?…]+$", para)
        cur = ""
        for s in sentences:
            s = s.strip()
            while len(s) > max_chars:                       # frase kilométrica
                cut = s.rfind(",", 0, max_chars)
                if cut < max_chars // 3:
                    cut = s.rfind(" ", 0, max_chars)
                chunks.append(s[:cut + 1].strip())
                s = s[cut + 1:].strip()
            if len(cur) + len(s) + 1 > max_chars:
                if cur:
                    chunks.append(cur)
                cur = s
            else:
                cur = (cur + " " + s).strip()
        if cur:
            chunks.append(cur)
        chunks.append("")                                   # marca de pausa
    return [c for i, c in enumerate(chunks)
            if c or (i + 1 < len(chunks) and chunks[i + 1])]


def engine_chatterbox(chunks, lang, ref, workdir):
    import torch
    import torchaudio
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"[chatterbox] device={device} · {len(chunks)} trozos")
    model = ChatterboxMultilingualTTS.from_pretrained(device=device)
    sr = model.sr
    files, silence = [], None
    for i, c in enumerate(chunks):
        if not c:                                           # pausa entre párrafos
            if silence is None:
                silence = workdir / "sil.wav"
                torchaudio.save(str(silence),
                                torch.zeros(1, int(sr * 0.55)), sr)
            files.append(silence)
            continue
        kw = {"language_id": lang}
        if ref:
            kw["audio_prompt_path"] = str(ref)
        wav = model.generate(c, **kw)
        f = workdir / f"seg{i:04d}.wav"
        torchaudio.save(str(f), wav, sr)
        files.append(f)
        print(f"  {i + 1}/{len(chunks)} · {len(c)} chars")
    return files


def engine_kokoro(chunks, lang, voice, workdir):
    import soundfile as sf
    from kokoro_onnx import Kokoro

    here = Path(__file__).parent
    model = next((p for p in [here / "kokoro-v1.0.onnx",
                              Path("kokoro-v1.0.onnx")] if p.exists()), None)
    voices = next((p for p in [here / "voices-v1.0.bin",
                               Path("voices-v1.0.bin")] if p.exists()), None)
    if not model or not voices:
        sys.exit("Faltan kokoro-v1.0.onnx / voices-v1.0.bin (ver instalación).")
    k = Kokoro(str(model), str(voices))
    voice = voice or ("ef_dora" if lang == "es" else "af_heart")
    print(f"[kokoro] voz={voice} · {len(chunks)} trozos")
    files = []
    for i, c in enumerate(chunks):
        if not c:
            continue                                        # kokoro pausa solo
        samples, sr = k.create(c, voice=voice, speed=1.0, lang=lang)
        f = workdir / f"seg{i:04d}.wav"
        sf.write(str(f), samples, sr)
        files.append(f)
        print(f"  {i + 1}/{len(chunks)}")
    return files


def stitch(files, out: Path):
    lst = out.with_suffix(".list.txt")
    lst.write_text("".join(f"file '{f.resolve()}'\n" for f in files))
    subprocess.run(["ffmpeg", "-y", "-v", "quiet", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-af", "loudnorm=I=-18:TP=-2",
                    "-codec:a", "libmp3lame", "-qscale:a", "3", str(out)],
                   check=True)
    lst.unlink()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("guion", help=".guion-es.txt / .guion-en.txt de make-podcast.py")
    p.add_argument("--engine", choices=["chatterbox", "kokoro"], default="chatterbox")
    p.add_argument("--lang", default=None, help="es/en (default: del nombre del guion)")
    p.add_argument("--ref", default=None,
                   help="chatterbox: wav/flac de 10-20 s con la voz fija de la revista")
    p.add_argument("--voice", default=None, help="kokoro: ef_dora/em_alex/em_santa/af_heart…")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    guion = Path(args.guion)
    text = guion.read_text(encoding="utf-8")
    lang = args.lang or ("en" if "guion-en" in guion.name else "es")
    out = Path(args.out or guion.with_suffix(".mp3"))
    out.parent.mkdir(parents=True, exist_ok=True)

    chunks = chunk_text(text)
    n = sum(len(c) for c in chunks)
    print(f"{guion.name}: {n:,} chars → {len(chunks)} trozos → {out}")

    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        if args.engine == "chatterbox":
            files = engine_chatterbox(chunks, lang, args.ref, wd)
        else:
            files = engine_kokoro(chunks, lang, args.voice, wd)
        stitch(files, out)
    print(f"OK → {out} ({out.stat().st_size / 1048576:.1f} MB)")


if __name__ == "__main__":
    main()
