#!/usr/bin/env python3
"""Inyecta o actualiza data-audio="URL" en el <body> de un número. Idempotente."""
import re, sys
f, url = sys.argv[1], sys.argv[2]
s = open(f, encoding="utf-8").read()
if "data-audio=" in s:
    s = re.sub(r'data-audio="[^"]*"', f'data-audio="{url}"', s, count=1)
else:
    s = re.sub(r"<body(?![^>]*data-audio)", f'<body data-audio="{url}"', s, count=1)
open(f, "w", encoding="utf-8").write(s)
print(f"  data-audio → {f}")
