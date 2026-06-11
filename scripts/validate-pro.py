#!/usr/bin/env python3
"""
SINAPSE · validate-pro.py — pipeline de validación por capas (v1).

Orquesta herramientas profesionales y degrada con gracia: cada capa corre
solo si su herramienta está disponible; las capas REQUIRED fallan el build,
las OPTIONAL solo avisan. Pensado para correr local y en GitHub Actions.

    python3 scripts/validate-pro.py --site .
    python3 scripts/validate-pro.py --site . --external   # también URLs externas

Capas:
  1 STANDARDS   html5validator/vnu (W3C Nu Checker)          REQUIRED*
  2 EDITORIAL   scripts/validate-issue.py (reglas SINAPSE)   REQUIRED
  3 DATA        jsonschema sobre data/registro.json          REQUIRED*
                + fecha en martes + numeración consecutiva
  4 LINKS       internos: anclas y rutas relativas (stdlib)  REQUIRED
                externos: lychee si existe, si no urllib     OPTIONAL
  5 A11Y        pa11y (WCAG 2.1 AA) si existe                OPTIONAL

  * degradan a OPTIONAL con aviso si falta la herramienta (vnu necesita
    Java; jsonschema es pip). En CI siempre están instaladas.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

C_OK, C_WARN, C_FAIL, C_DIM, C_END = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"
results = []  # (capa, estado, detalle)   estado ∈ ok|warn|fail|skip


def report(layer, state, detail=""):
    results.append((layer, state, detail))
    sym = {"ok": f"{C_OK}✓{C_END}", "warn": f"{C_WARN}⚠{C_END}",
           "fail": f"{C_FAIL}✗{C_END}", "skip": f"{C_DIM}–{C_END}"}[state]
    print(f" {sym} [{layer}] {detail}")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def issue_files(site: Path):
    return sorted((site / "issues").glob("n*.html")) + \
           sorted((site / "en" / "issues").glob("n*.html"))


# ── Capa 1 · STANDARDS (vnu) ────────────────────────────────────────────────

def layer_standards(site: Path):
    exe = shutil.which("html5validator")
    if not exe:
        report("STANDARDS", "warn",
               "html5validator no instalado (pip install html5validator; necesita Java) — capa omitida")
        return
    r = run([exe, "--root", str(site), "--match", "n*.html", "index.html",
             "--blacklist", "example", "node_modules"])
    if r.returncode == 0:
        report("STANDARDS", "ok", "W3C Nu Checker: HTML válido en todos los archivos")
    else:
        errors = (r.stdout + r.stderr).strip().splitlines()
        report("STANDARDS", "fail",
               f"Nu Checker encontró problemas ({len(errors)} líneas):")
        print("\n".join("      " + e for e in errors[:15]))


# ── Capa 2 · EDITORIAL (validador propio existente) ─────────────────────────

def layer_editorial(site: Path):
    script = site / "scripts" / "validate-issue.py"
    if not script.exists():
        report("EDITORIAL", "fail", "scripts/validate-issue.py no encontrado")
        return
    r = run([sys.executable, str(script), "--site", str(site)])
    if r.returncode == 0:
        report("EDITORIAL", "ok", "reglas SINAPSE (estructura, atlas, .plain, registry)")
    else:
        report("EDITORIAL", "fail", "validate-issue.py reporta fallas:")
        fails = [l for l in r.stdout.splitlines() if "✗" in l]
        print("\n".join("      " + l.strip() for l in fails[:15]))


# ── Capa 3 · DATA (schema + reglas de calendario) ───────────────────────────

def layer_data(site: Path):
    reg_path = site / "data" / "registro.json"
    schema_path = site / "data" / "registro.schema.json"
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception as e:
        report("DATA", "fail", f"registro.json ilegible: {e}")
        return

    if schema_path.exists():
        try:
            import jsonschema
            jsonschema.validate(data, json.loads(schema_path.read_text(encoding="utf-8")))
            report("DATA", "ok", "registro.json valida contra registro.schema.json")
        except ImportError:
            report("DATA", "warn", "jsonschema no instalado (pip install jsonschema) — schema omitido")
        except Exception as e:
            msg = getattr(e, "message", str(e))
            report("DATA", "fail", f"schema: {msg}")
    else:
        report("DATA", "warn", "data/registro.schema.json no existe — schema omitido")

    # Reglas de calendario y secuencia (independientes del schema)
    nums = data.get("numeros", [])
    bad_day = [n["numero"] for n in nums
               if date.fromisoformat(n["fecha"]).weekday() != 1]
    if bad_day:
        report("DATA", "fail", f"fechas que no caen en martes: N° {bad_day}")
    else:
        report("DATA", "ok", "todas las fechas caen en martes")

    seq = [n["numero"] for n in nums]
    if seq != list(range(min(seq), min(seq) + len(seq))) and \
       seq != list(range(max(seq), max(seq) - len(seq), -1)):
        report("DATA", "fail", f"numeración no consecutiva: {seq}")
    else:
        report("DATA", "ok", f"numeración consecutiva ({min(seq)}…{max(seq)})")


# ── Capa 4 · LINKS ──────────────────────────────────────────────────────────

def layer_links(site: Path, external: bool):
    # 4a · internos con stdlib: anclas #id y rutas relativas
    broken = []
    for f in issue_files(site) + [site / "index.html", site / "en" / "index.html"]:
        if not f.exists():
            continue
        html = f.read_text(encoding="utf-8")
        ids = set(re.findall(r'\bid="([^"]+)"', html))
        for anchor in re.findall(r'href="#([^"]+)"', html):
            if anchor not in ids:
                broken.append(f"{f.name}: #{anchor}")
        for rel in re.findall(r'(?:href|src)="(?!https?:|#|mailto:|data:)([^"]+)"', html):
            if "${" in rel:      # template literal de JS (index renderiza con fetch)
                continue
            target = (f.parent / rel.split("#")[0].split("?")[0]).resolve()
            if not target.exists():
                broken.append(f"{f.name}: {rel}")
    if broken:
        report("LINKS", "fail", f"{len(broken)} enlaces internos rotos:")
        print("\n".join("      " + b for b in broken[:12]))
    else:
        report("LINKS", "ok", "anclas y rutas relativas íntegras")

    # 4b · externos (opcional, lento)
    if not external:
        report("LINKS", "skip", "externos omitidos (usar --external)")
        return
    lychee = shutil.which("lychee")
    if lychee:
        r = run([lychee, "--no-progress", "--exclude-mail", str(site / "issues"),
                 str(site / "en" / "issues")])
        state = "ok" if r.returncode == 0 else "warn"
        report("LINKS", state, "lychee (externos): " +
               ("sin enlaces rotos" if state == "ok" else "ver salida"))
        if state == "warn":
            print(r.stdout[-1500:])
    else:
        urls = set()
        for f in issue_files(site):
            urls |= set(re.findall(r'href="(https?://[^"]+)"',
                                   f.read_text(encoding="utf-8")))
        bad = []
        for u in sorted(urls):
            try:
                req = urllib.request.Request(u, method="HEAD",
                                             headers={"User-Agent": "sinapse-validator"})
                urllib.request.urlopen(req, timeout=10)
            except Exception as e:
                bad.append(f"{u} — {getattr(e, 'code', e)}")
        if bad:
            report("LINKS", "warn", f"{len(bad)}/{len(urls)} URLs externas con problema:")
            print("\n".join("      " + b for b in bad[:12]))
        else:
            report("LINKS", "ok", f"{len(urls)} URLs externas responden")


# ── Capa 5 · A11Y (opcional) ────────────────────────────────────────────────

def layer_a11y(site: Path):
    pa11y = shutil.which("pa11y")
    if not pa11y:
        report("A11Y", "skip",
               "pa11y no instalado (npm i -g pa11y) — en CI sí corre")
        return
    worst = "ok"
    for f in issue_files(site)[-2:]:   # último número ES+EN basta en local
        r = run([pa11y, "--standard", "WCAG2AA", "--reporter", "json", str(f)])
        try:
            issues = json.loads(r.stdout or "[]")
        except json.JSONDecodeError:
            issues = []
        errs = [i for i in issues if i.get("type") == "error"]
        if errs:
            worst = "fail"
            report("A11Y", "fail", f"{f.name}: {len(errs)} errores WCAG 2.1 AA")
            for e in errs[:5]:
                print(f"      {e.get('code', '')} — {e.get('message', '')[:90]}")
    if worst == "ok":
        report("A11Y", "ok", "WCAG 2.1 AA sin errores en los últimos números")


# ── Resumen ─────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--site", default=".")
    p.add_argument("--external", action="store_true",
                   help="verificar también URLs externas (lento)")
    args = p.parse_args()
    site = Path(args.site).resolve()

    print(f"\nSINAPSE · validate-pro · {site}\n")
    layer_standards(site)
    layer_editorial(site)
    layer_data(site)
    layer_links(site, args.external)
    layer_a11y(site)

    fails = [r for r in results if r[1] == "fail"]
    warns = [r for r in results if r[1] == "warn"]
    print(f"\nResumen: {len(results)} checks · "
          f"{C_FAIL}{len(fails)} fail{C_END} · {C_WARN}{len(warns)} warn{C_END}")
    print("PUBLICAR: " + (f"{C_FAIL}NO{C_END}" if fails else f"{C_OK}OK{C_END}") + "\n")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
