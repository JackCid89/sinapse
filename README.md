# SINAPSE

Revista semanal en español sobre ciencia, tecnología e industria. Generada automáticamente cada semana por un *scheduled task* y publicada como sitio estático vía **GitHub Pages**.

Editor: Jack Cid · contacto: <j.andres.cid@gmail.com>

---

## Estructura del repo

```
sinapse-site/
├── index.html              # landing — lista de números (lee data/registro.json)
├── assets/
│   └── sinapse.css         # hoja de estilos compartida por todos los HTML
├── issues/                 # un archivo por número
│   └── n001-abril-2026.html
├── editorial/
│   └── guia.html           # guía editorial (interna, pero pública)
├── data/
│   └── registro.json       # registro maestro de números publicados (fuente de verdad)
├── .nojekyll               # evita procesado Jekyll en GitHub Pages
├── .github/workflows/
│   └── pages.yml           # deploy automatizado a Pages
└── README.md
```

## Cómo se genera cada número

1. El *scheduled task* `sinapse-semanal` se dispara cada martes.
2. Lee `data/registro.json` para conocer las disciplinas, regiones y tonos cubiertos en los últimos números.
3. Hace búsqueda web sobre la actividad científica/tecnológica/industrial de la semana.
4. Aplica reglas de rotación (ver [`editorial/guia.html`](./editorial/guia.html)).
5. Escribe `issues/nXXX-[mes]-2026.html` reutilizando `assets/sinapse.css`.
6. Añade la entrada correspondiente al array `numeros` de `data/registro.json`.
7. (Opcional) `git add . && git commit && git push` — el workflow de Pages despliega.

`index.html` lee `data/registro.json` con `fetch` en el cliente y dibuja la lista de números — no hay que tocar el HTML cuando sale uno nuevo.

## Vista previa local

Por la carga de JSON vía `fetch`, abrir `index.html` con doble clic (`file://`) **no funcionará** para listar los números. Hay que servirlo:

```bash
cd sinapse-site
python3 -m http.server 8000
# abre http://localhost:8000
```

Los archivos individuales en `issues/` sí se ven bien con doble clic — solo el índice necesita servidor.

## Deploy en GitHub Pages

### Opción A — automatizada con GitHub Actions (recomendada)

El workflow incluido en `.github/workflows/pages.yml` se dispara en cada push a `main` y publica el sitio. En el repo de GitHub:

1. *Settings → Pages → Build and deployment → Source: GitHub Actions*.
2. `git push origin main`. El workflow corre y queda publicado en `https://<usuario>.github.io/<repo>/`.

### Opción B — Pages "branch deployment" sin Actions

1. *Settings → Pages → Build and deployment → Source: Deploy from a branch*.
2. Branch: `main`, carpeta `/` (root).
3. GitHub sirve el contenido tal cual; `.nojekyll` impide que intente procesarlo como Jekyll.

### Dominio personalizado (opcional)

Si quieres servir bajo un dominio propio (p. ej. `sinapse.jackcid.dev`):

1. Crea un archivo `CNAME` en la raíz con el host (`echo sinapse.jackcid.dev > CNAME`).
2. En tu DNS, apunta un `CNAME` (o `ALIAS`/`ANAME`) al `<usuario>.github.io`.

## Política editorial

Resumen mínimo (detalle en [`editorial/guia.html`](./editorial/guia.html)):

- **Sin hype.** Nada de "revolucionario" o "sin precedentes" sin datos detrás.
- **Paper-first.** Siempre enlazar la fuente primaria.
- **Contexto siempre.** Qué había antes, qué problema resuelve, cuáles son las limitaciones.
- **Rotación.** Ni la portada ni los papers repiten disciplinas de los dos números anteriores; al menos 1 fuente asiática por número; tonos rotativos en la columna.

## Licencia

Texto editorial: derechos reservados © Jack Cid.
Código del sitio (CSS, JS, plantillas): MIT.
