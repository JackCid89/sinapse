#!/bin/bash
# SINAPSE · publicar-audio.sh — parte del ciclo de publicación semanal.
#
# Para un número: genera el guion, sintetiza ES+EN con la voz clonada de Jack
# (Chatterbox en MPS), sube los MP3 a GitHub Releases (gratis, streamable con
# range requests — no engordan el repo) e inyecta data-audio en los HTML.
#
# Uso (desde sinapse/, en el Mac):
#   ./scripts/publicar-audio.sh n005-junio-2026          # un número
#   ./scripts/publicar-audio.sh --todos                  # los 8 existentes
#   ENGINE=kokoro ./scripts/publicar-audio.sh n005-...   # motor rápido (sin clon)
#
# Requisitos (una vez):
#   brew install gh ffmpeg && gh auth login
#   python3 -m venv ~/.venvs/sinapse-tts && source ~/.venvs/sinapse-tts/bin/activate
#   pip install chatterbox-tts torch torchaudio
set -euo pipefail
cd "$(dirname "$0")/.."

ENGINE="${ENGINE:-chatterbox}"
VOCES="../editorial/voces"
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)

procesar () {
  local ES_FILE="issues/$1.html"
  [ -f "$ES_FILE" ] || { echo "✗ no existe $ES_FILE"; return 1; }
  local NUM=$(echo "$1" | grep -o '^n[0-9]*')
  local EN_FILE=$(ls en/issues/${NUM}-*.html 2>/dev/null | head -1)
  local TAG="audio-${NUM}"

  echo "── ${NUM} · guiones ─────────────────────────────"
  python3 scripts/make-podcast.py "$ES_FILE" --dry-run
  [ -n "$EN_FILE" ] && python3 scripts/make-podcast.py "$EN_FILE" --dry-run

  echo "── ${NUM} · síntesis (${ENGINE}) ────────────────"
  mkdir -p /tmp/sinapse-audio
  local REF_ES=""; local REF_EN=""
  if [ "$ENGINE" = "chatterbox" ]; then
    REF_ES="--ref $VOCES/jack-cid-es.wav"; REF_EN="--ref $VOCES/jack-cid-en.wav"
  fi
  python3 scripts/sinapse-tts-mac.py "${ES_FILE%.html}.guion-es.txt" \
      --engine "$ENGINE" $REF_ES --out "/tmp/sinapse-audio/${NUM}-es.mp3"
  [ -n "$EN_FILE" ] && python3 scripts/sinapse-tts-mac.py "${EN_FILE%.html}.guion-en.txt" \
      --engine "$ENGINE" $REF_EN --out "/tmp/sinapse-audio/${NUM}-en.mp3"

  echo "── ${NUM} · GitHub Release ──────────────────────"
  gh release view "$TAG" >/dev/null 2>&1 || \
      gh release create "$TAG" --title "Audio ${NUM}" \
          --notes "Narración con voz clonada (Chatterbox Multilingual, local)." 
  gh release upload "$TAG" /tmp/sinapse-audio/${NUM}-*.mp3 --clobber

  echo "── ${NUM} · inyectar data-audio ─────────────────"
  local BASE="https://github.com/${REPO}/releases/download/${TAG}"
  python3 - "$ES_FILE" "${BASE}/${NUM}-es.mp3" <<'PYEOF'
import re, sys
f, url = sys.argv[1], sys.argv[2]
s = open(f, encoding="utf-8").read()
if 'data-audio=' in s:
    s = re.sub(r'data-audio="[^"]*"', f'data-audio="{url}"', s)
else:
    s = re.sub(r'<body(?![^>]*data-audio)', f'<body data-audio="{url}"', s, count=1)
open(f, "w", encoding="utf-8").write(s)
print(f"  {f} → {url}")
PYEOF
  if [ -n "$EN_FILE" ]; then
    python3 - "$EN_FILE" "${BASE}/${NUM}-en.mp3" <<'PYEOF'
import re, sys
f, url = sys.argv[1], sys.argv[2]
s = open(f, encoding="utf-8").read()
if 'data-audio=' in s:
    s = re.sub(r'data-audio="[^"]*"', f'data-audio="{url}"', s)
else:
    s = re.sub(r'<body(?![^>]*data-audio)', f'<body data-audio="{url}"', s, count=1)
open(f, "w", encoding="utf-8").write(s)
print(f"  {f} → {url}")
PYEOF
  fi
  rm -f issues/*.guion-*.txt en/issues/*.guion-*.txt
}

if [ "${1:-}" = "--todos" ]; then
  for f in issues/n*.html; do procesar "$(basename "${f%.html}")"; done
else
  procesar "${1:?Uso: publicar-audio.sh n00N-mes-2026 | --todos}"
fi

echo
echo "Listo. Validar y publicar:"
echo "  python3 scripts/validate-pro.py --site . && git add -A && git commit -m 'audio: nuevos MP3' && git push"
