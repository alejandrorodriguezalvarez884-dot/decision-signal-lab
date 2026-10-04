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

`site/` es un sitio Astro estático que lee `radar/*.json` directamente del repositorio. Se
publica en GitHub Pages, en un enlace propio:

**https://alejandrorodriguezalvarez884-dot.github.io/decision-signal-lab/**

Tiene cuatro tipos de página: resumen, empresas, ficha por empresa (`/company/<ticker>/`) y
método. La web personal (`personal-website`) solo lo enlaza desde la tarjeta del proyecto.

```bash
cd site
npm install
npx astro dev --background   # http://localhost:4321/decision-signal-lab/
npm run build                # genera site/dist
```

Todos los enlaces internos pasan por `link()` (`site/src/lib/radar.ts`), que antepone la ruta
base `/decision-signal-lab`. Si el sitio se moviera a un dominio propio, basta con cambiar
`site` y `base` en `site/astro.config.mjs`.

## Actualización y despliegue automáticos

`.github/workflows/radar.yml` se ejecuta dos veces al día (13:30 y 22:30 UTC), y también al
hacer push a `main` de cambios en `site/` o `radar/`:

1. `radar update`: busca filings nuevos, los puntúa y hace commit de `radar/` si hay algo.
   Este paso necesita dos secretos en GitHub (Settings → Secrets and variables → Actions):
   `PERPLEXITY_API_KEY` y `SEC_USER_AGENT`. Si faltan, el paso se salta con un aviso y el
   resto sigue. En un push no se ejecuta.
2. Compila `site/`.
3. Publica `site/dist` en la rama `gh-pages`, que es la que sirve GitHub Pages
   (Settings → Pages → Deploy from a branch → `gh-pages`).

En GitHub no hay caché de respuestas, así que el tope total no cuenta lo gastado antes; el tope
por ejecución es $0.25.

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
