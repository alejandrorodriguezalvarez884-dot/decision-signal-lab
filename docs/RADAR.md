# El radar de resultados

Desde el 2026-10-04 el producto del proyecto es el **radar**: lo que dicen los comunicados de
resultados del S&P 100, convertido en datos y publicado en la web. No predice nada.

## Qué hace

1. Toma de EDGAR los 8-K con Item 2.02 de las 99 empresas de `radar_universe.py` (la lista del
   S&P 100 de diciembre de 2020 que ya usaba el estudio) y su comunicado (EX-99.1).
2. Limpia el texto y oculta nombres y fechas, igual que el estudio.
3. Le hace al modelo las preguntas de texto de `questions.TEXT_QUESTIONS` y, si se piden, las
   temáticas de `questions.THEME_QUESTIONS`. Solo ve el comunicado: ninguna petición lleva
   precios ni la reacción del mercado.
4. Publica un comunicado si el modelo lo lee como comunicado de resultados
   (`is_earnings_release` ≥ 0.5) y la empresa no tiene otro publicado en los 20 días
   anteriores.
5. Escribe `radar/releases.json` (un comunicado por línea, el registro) y `radar/summary.json`
   (agregados por trimestre de publicación, por sector y por empresa; se regenera a partir del
   anterior).

`radar/` está en git, a diferencia de `data/`: es lo que lee el sitio.

## Comandos

```bash
uv run decisionsignal radar estimate   # coste de `build`, sin gastar
uv run decisionsignal radar build      # puntúa la descarga local (data/interim) y escribe radar/
uv run decisionsignal radar update     # busca en EDGAR lo publicado desde la última vez
uv run decisionsignal radar summary    # regenera summary.json
```

Todos aceptan `--no-themes`, que omite las preguntas temáticas (un tercio del coste por
comunicado). `build` reutiliza la caché: los comunicados ya puntuados no se vuelven a pagar.
Los topes `DECIDER_MAX_USD` y `DECIDER_TOTAL_MAX_USD` siguen aplicando.

## El sitio

`site/` es un sitio Astro estático que lee `radar/*.json` directamente del repositorio. Es una
herramienta para **analizar los últimos resultados de una empresa**:

- **Portada (`/`)**: buscador por nombre o ticker, los últimos comunicados publicados y la
  lista de las 99 empresas.
- **Ficha de empresa (`/company/<ticker>/`)**: el análisis del último comunicado. Qué dice
  (guidance, resultados, perspectivas, cautela), qué ha cambiado respecto al comunicado
  anterior, la probabilidad de cada respuesta de guidance, la comparación con la mediana de
  sus pares de sector, las preguntas de sí o no (márgenes, demanda y temas) y el histórico.
- **Market trends (`/trends/`)**: los agregados por trimestre y sector. Secundario.
- **Method (`/method/`)**: preguntas exactas, validación y el estudio que salió nulo.

Las frases de "qué ha cambiado" y la comparación con pares se calculan al compilar, en
`site/src/lib/radar.ts` (`changesSince`, `peersOf`). No se llama al modelo para eso.

```bash
cd site
npm install
npx astro dev --background   # http://localhost:4321/decision-signal-lab/
npm run build                # genera site/dist
```

## Publicación y dominio

GitHub Pages sirve la rama `gh-pages`. Hoy el sitio está en
https://alejandrorodriguezalvarez884-dot.github.io/decision-signal-lab/.

Para pasarlo a un dominio propio comprado en Cloudflare basta un archivo:

1. Crear `site/public/CNAME` con el dominio en una línea (por ejemplo `midominio.com`) y
   hacer push. `site/astro.config.mjs` lee ese archivo y compila con la raíz `/`; GitHub Pages
   lo lee para servir el dominio.
2. En Cloudflare, DNS del dominio: un registro `CNAME` con nombre `@` y destino
   `alejandrorodriguezalvarez884-dot.github.io`, y otro igual con nombre `www`. Con el proxy
   desactivado ("DNS only") hasta que GitHub emita el certificado.
3. En GitHub, Settings → Pages: comprobar que aparece el dominio y marcar "Enforce HTTPS".
4. Cambiar `liveUrl` de la tarjeta en `personal-website/src/data/profile.ts`.

## Actualizaciones: solo a mano

No hay nada programado. Los datos cambian únicamente cuando el usuario lo decide, por una de
estas dos vías:

- **Desde GitHub** (sirve desde el móvil): Actions → Radar → Run workflow. Busca filings
  nuevos, los puntúa, hace commit de `radar/` y publica el sitio. Necesita los secretos
  `PERPLEXITY_API_KEY` y `SEC_USER_AGENT` (Settings → Secrets and variables → Actions); si
  faltan, se salta la búsqueda y solo republica. Tope por ejecución: $0.25.
- **Desde este ordenador**: `uv run decisionsignal radar update`, revisar, y hacer commit y
  push de `radar/`.

Un push a `main` que toque `site/` o `radar/` recompila y publica el sitio, sin buscar nada ni
gastar en la API.

## Validación

`uv run decisionsignal validate sample` saca 48 comunicados estratificados por la respuesta del
modelo a la pregunta de guidance y escribe solo los pasajes relevantes, sin la respuesta.
`validate evaluate` cruza las etiquetas de `validation/guidance_labels.csv` con el modelo.

Resultado del 2026-10-04 (`validation/guidance_result.json`): de 45 comunicados con respuesta
determinable, coinciden 37 (82 %), 40 (89 %) aceptando una segunda etiqueta defendible, y 42
(93 %) en la dirección (sube, baja o ninguna). Los 9 "raised" del modelo son correctos; de los
9 "lowered", 2 no lo son.

Límites de esta validación: el segundo lector fue Claude, no una persona; mide el acierto
cuando el modelo da una respuesta, no cuántos comunicados de cada clase se le escapan; y solo
cubre la pregunta de guidance.

## Coste

| Concepto | Coste |
|---|---|
| Puntuar 2025–2026 con las preguntas de texto (754 comunicados, 2026-10-04) | $0.63 |
| Las 4 preguntas temáticas sobre todo el histórico (2.338 comunicados, 2026-10-04) | $0.99 |
| Un comunicado nuevo, con temáticas | ≈ $0.0013 |
