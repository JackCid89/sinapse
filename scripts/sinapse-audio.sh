#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# SINAPSE · sinapse-audio.sh — UN comando para todo el audio.
#
# Hace, sin intervención: (1) prepara el entorno (venv + dependencias),
# (2) genera la narración con tu voz clonada (Chatterbox), (3) sube los MP3 a
# GitHub Releases, (4) conecta data-audio en los HTML, (5) valida y commitea.
# Es REANUDABLE: si un número ya tiene su audio publicado, lo salta. Podés
# cortarlo (Ctrl-C) y volver a correrlo; sigue donde quedó.
#
# Uso:
#   ./scripts/sinapse-audio.sh                 # todos los números que falten
#   ./scripts/sinapse-audio.sh n004-mayo-2026  # solo uno
#   ./scripts/sinapse-audio.sh --engine kokoro # motor rápido (voz NO clonada)
#   ./scripts/sinapse-audio.sh --force         # regenerar aunque ya exista
#   ./scripts/sinapse-audio.sh --no-push       # commitea pero no pushea
#
# Requisitos que el script NO puede instalar solo (te avisa si faltan):
#   · Homebrew  · gh (GitHub CLI) autenticado: gh auth login
# El resto (Python venv, chatterbox, ffmpeg vía brew) lo instala si falta.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.."                       # raíz del repo (sinapse/)

# ── parámetros ───────────────────────────────────────────────────────────────
ENGINE="qwen3"; FORCE=0; PUSH=1; ONLY=""
VENV="$HOME/.venvs/sinapse-tts"
VOCES="../editorial/voces"
LOG="/tmp/sinapse-audio.log"
for arg in "$@"; do
  case "$arg" in
    --engine) :;; chatterbox|kokoro) ENGINE="$arg";;
    --engine=*) ENGINE="${arg#*=}";;
    --force) FORCE=1;;
    --no-push) PUSH=0;;
    n[0-9]*) ONLY="$arg";;
    *) ;;
  esac
done

say(){ printf "\n\033[1m▸ %s\033[0m\n" "$1"; }
ok(){  printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn(){ printf "  \033[33m⚠\033[0m %s\n" "$1"; }
die(){ printf "  \033[31m✗ %s\033[0m\n" "$1"; exit 1; }

# ── 0 · chequeos que requieren acción tuya ──────────────────────────────────
say "Comprobando herramientas base"
command -v brew >/dev/null || die "Falta Homebrew. Instalalo: https://brew.sh"
command -v ffmpeg >/dev/null || { warn "Instalando ffmpeg…"; brew install ffmpeg; }
command -v gh >/dev/null || { warn "Instalando gh…"; brew install gh; }
gh auth status >/dev/null 2>&1 || die "GitHub CLI sin sesión. Corré: gh auth login"
ok "brew · ffmpeg · gh autenticado"

# ── 1 · entorno Python + Chatterbox ─────────────────────────────────────────
say "Preparando entorno de síntesis ($ENGINE)"
[ -d "$VENV" ] || { warn "Creando venv en $VENV…"; python3 -m venv "$VENV"; }
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -c "import chatterbox" 2>/dev/null || python -c "import kokoro_onnx" 2>/dev/null || {
  warn "Instalando dependencias (puede tardar varios minutos la primera vez)…"
  pip install -q --upgrade pip
  case "$ENGINE" in
    qwen3)      pip install -q mlx-audio soundfile numpy ;;
    chatterbox) pip install -q chatterbox-tts torch torchaudio ;;
    kokoro)     pip install -q kokoro-onnx soundfile ;;
  esac
}
case "$ENGINE" in
  qwen3)
    python -c "import mlx_audio" 2>/dev/null || die "No pude importar mlx-audio (¿Mac Apple Silicon?)."
    [ -f "$VOCES/jack-cid-es.wav" ] || die "Falta tu voz de referencia: $VOCES/jack-cid-es.wav"
    [ -f "$VOCES/jack-cid-es.txt" ] || warn "Sin transcripción $VOCES/jack-cid-es.txt: el clonado mejora si existe."
    [ -n "${HF_TOKEN:-}" ] || warn "Sin HF_TOKEN: la 1ª descarga del modelo puede ir lenta (export HF_TOKEN=...)."
    ok "Qwen3-TTS (MLX) listo · voz de referencia encontrada" ;;
  chatterbox)
    python -c "import chatterbox" 2>/dev/null || die "No pude importar chatterbox-tts."
    [ -f "$VOCES/jack-cid-es.wav" ] || die "Falta tu voz de referencia: $VOCES/jack-cid-es.wav"
    ok "Chatterbox listo · voz de referencia encontrada" ;;
  kokoro)
    python -c "import kokoro_onnx" 2>/dev/null || die "No pude importar kokoro-onnx."
    ok "Kokoro listo (voz NO clonada)" ;;
esac

# ── 2 · loop por número ─────────────────────────────────────────────────────
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
[ -n "$ONLY" ] && LIST=("issues/$ONLY.html") || LIST=(issues/n*.html)
GENERATED=0

asset_exists(){ gh release view "$1" --json assets -q '.assets[].name' 2>/dev/null | grep -qx "$2"; }

for ES_FILE in "${LIST[@]}"; do
  [ -f "$ES_FILE" ] || { warn "no existe $ES_FILE"; continue; }
  NUM=$(basename "$ES_FILE" | grep -o '^n[0-9]*')
  EN_FILE=$(ls en/issues/${NUM}-*.html 2>/dev/null | head -1)
  TAG="audio-${NUM}"
  BASE="https://github.com/${REPO}/releases/download/${TAG}"

  if [ "$FORCE" = 0 ] && asset_exists "$TAG" "${NUM}-es.mp3"; then
    ok "${NUM}: ya publicado, lo salto (usá --force para regenerar)"
    # asegurar que el HTML quede conectado aunque venga de otra máquina
    grep -q 'data-audio=' "$ES_FILE" || python3 scripts/_inject_audio.py "$ES_FILE" "${BASE}/${NUM}-es.mp3"
    continue
  fi

  say "${NUM}: generando audio ($ENGINE)"
  mkdir -p /tmp/sinapse-audio
  python3 scripts/make-podcast.py "$ES_FILE" --dry-run >>"$LOG" 2>&1
  [ -n "$EN_FILE" ] && python3 scripts/make-podcast.py "$EN_FILE" --dry-run >>"$LOG" 2>&1

  REF_ES=""; REF_EN=""
  case "$ENGINE" in qwen3|chatterbox) REF_ES="--ref $VOCES/jack-cid-es.wav"; REF_EN="--ref $VOCES/jack-cid-en.wav";; esac

  [ "$ENGINE" = qwen3 ] && EST="~3-5 min con MLX" || EST="puede tardar 30-45 min"
  echo "  · sintetizando ES ($EST)…"
  python3 scripts/sinapse-tts-mac.py "${ES_FILE%.html}.guion-es.txt" \
      --engine "$ENGINE" $REF_ES --out "/tmp/sinapse-audio/${NUM}-es.mp3" \
      || die "Falló la síntesis ES de ${NUM} (ver $LOG)"
  if [ -n "$EN_FILE" ]; then
    echo "  · sintetizando EN…"
    python3 scripts/sinapse-tts-mac.py "${EN_FILE%.html}.guion-en.txt" \
        --engine "$ENGINE" $REF_EN --out "/tmp/sinapse-audio/${NUM}-en.mp3" \
        || die "Falló la síntesis EN de ${NUM}"
  fi

  echo "  · subiendo a GitHub Releases ($TAG)…"
  gh release view "$TAG" >/dev/null 2>&1 || \
    gh release create "$TAG" --title "Audio ${NUM}" \
      --notes "Narración SINAPSE · voz clonada de Jack Cid (Chatterbox, local)."
  gh release upload "$TAG" /tmp/sinapse-audio/${NUM}-*.mp3 --clobber

  python3 scripts/_inject_audio.py "$ES_FILE" "${BASE}/${NUM}-es.mp3"
  [ -n "$EN_FILE" ] && python3 scripts/_inject_audio.py "$EN_FILE" "${BASE}/${NUM}-en.mp3"
  rm -f issues/*.guion-*.txt en/issues/*.guion-*.txt
  ok "${NUM} publicado y conectado"
  GENERATED=$((GENERATED+1))
done

# ── 3 · validar + commit + push ─────────────────────────────────────────────
say "Validando el sitio"
python3 scripts/validate-pro.py --site . || die "La validación falló — NO commiteo."

if git diff --quiet && git diff --cached --quiet; then
  ok "Sin cambios que commitear (todo estaba al día)."
else
  git add issues/*.html en/issues/*.html
  git commit -m "audio: narración con voz clonada (${GENERATED:-0} número(s) nuevos)" \
      --author "Jack Cid <j.andres.cid@gmail.com>"
  if [ "$PUSH" = 1 ]; then
    git push origin main && ok "Pusheado. Pages desplegará en 1-2 min."
  else
    ok "Commiteado (no pusheado, usaste --no-push). Subilo con: git push origin main"
  fi
fi
say "Listo."
