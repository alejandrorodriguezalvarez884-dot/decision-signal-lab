# Estado del proyecto y cómo continuar

Última actualización: 2026-10-04 (noche). Este documento basta para retomar el trabajo en otro
ordenador o en otra sesión de agente, sin el historial de la conversación.

## 0. Estado actual: el radar (giro del 2026-10-04)

### Dentro de Market Hub (2026-10-05)

- **Estilo nuevo**: el de Market Hub (tema oscuro inspirado en TradingView; tokens en
  `site/src/styles/global.css`, variables `--radar-*` en `RadarStyles.astro` con la paleta oscura).
  La cabecera lleva `HubBar.astro`: vuelta al hub y el usuario, si hay login.
- **Dos despliegues del mismo código**, que comparten bucket y por tanto el contador y los topes
  de gasto (0,25 $/día, 4 $ en total, entre los dos):
  - `make deploy` → servicio `earnings-radar`, **público**, en `earningsradar.app`. No se ha
    redesplegado: sigue con la revisión anterior al estilo nuevo. Si se redespliega (`make deploy`
    o `make publish`), coge el estilo nuevo pero sigue público.
  - `make deploy-hub` → servicio `earnings-radar-hub`, para `radar.themarkethub.app`. Con
    `HUB_URL` solo entra quien tenga sesión en Market Hub (`src/decisionsignal/hubauth.py` lee la
    cookie `mh_session` del hub y comprueba su firma con `market-hub-session-secret`; no la escribe
    ni guarda nada del usuario). Sin límite por IP (decisión del usuario); los topes siguen.
  - El script se niega a poner el login en `earnings-radar`, y reutiliza la clave de Perplexity
    que ya está en Secret Manager si `.env` no la trae.

### Dentro de My Hub (2026-10-06; desplegado como `earnings-radar-hub-00004-t82`)

El usuario pidió que, dentro de Market Hub, el radar quede integrado en el área privada del portal,
porque solo se consulta desde ahí. La cabecera pública del portal ya no lo nombra.

- `components/HubNav.astro` sustituye a `HubBar.astro`: es la navegación de My Hub (la misma que
  `App.astro` en `market-hub-landing`): barra lateral en pantallas anchas con "Your space", "Tools"
  ("Earnings" marcada) y "Explore", y una barra arriba en pantallas estrechas. Va marcada
  `hub-only`: en `earningsradar.app` no aparece y el radar conserva su cabecera con su nombre.
- `Page.astro`: encima de cada página queda la barra propia del radar (nombre, sus tres páginas y
  el buscador), la misma en los dos despliegues. Un cambio en la navegación de My Hub se hace en
  los tres repos.

### Diseño del portal y cabecera compartida (2026-10-05, noche; desplegado en el hub)

- `site/src/styles/global.css` es el del portal Market Hub (tipografía IBM Plex, sin cajas, sin
  color de marca). Las variables `--radar-*` de `RadarStyles.astro` apuntan a esos tokens: una
  lectura se dibuja en el color del texto, y el verde y el rojo quedan para "guidance raised" y
  "lowered".
- **El mismo build tiene dos cabeceras.** `layouts/Layout.astro` marca la página con `.in-hub`
  antes de pintar cuando el dominio es `themarkethub.app` (o con `?hub` en local); lo que solo
  sale en un modo lleva `hub-only` o `standalone-only`. Dentro del hub: cabecera del portal
  (`Markets · Fundamentals · Earnings`), y en el análisis las pestañas `Price · Fundamentals ·
  Results release` de la empresa. En `earningsradar.app`: su nombre y su navegación, sin nada
  del hub.
- El buscador va en la cabecera (`CompanySearch compact`); la portada está rehecha sin tarjetas.
- 72 tests en verde y el sitio compila. Revisado en local en los dos modos; el resultado de un
  análisis se revisó con un sustituto que responde desde `radar/releases.json` (gasto cero).
- Subido a `main` y desplegado con `make deploy-hub` como `earnings-radar-hub-00002-h8z`.
  **`make deploy` no se ha lanzado**: `earningsradar.app` sigue en `earnings-radar-00003-msk`; si
  algún día se redespliega, cogerá este diseño en su modo propio.

El usuario decidió el 2026-10-04 dejar de intentar predecir retornos (el diseño salió nulo, ver
apartado 2) y usar el mismo modelo para lo que hace bien: leer. El producto es ahora el **radar
de resultados**, descrito en [RADAR.md](RADAR.md). Las secciones 1 a 6 de este documento
describen el estudio cerrado y se conservan como contexto.

Decisiones del usuario ese día:
- El radar se publica como **sitio propio en un enlace aparte**, no como sección de su web
  personal. La web personal solo lo referencia desde la tarjeta del proyecto.
- Aprobó lanzar las 4 preguntas temáticas sobre todo el histórico.
- El foco del sitio es **analizar los últimos resultados de una empresa**. Los agregados y el
  estudio se pueden ver, pero son secundarios.
- **Sin actualizaciones programadas y sin GitHub Actions.** Todo se ejecuta en local y lo
  orquesta el `Makefile`: `make check`, `make update`, `make deploy`, `make publish`.
- Compró el dominio **`earningsradar.app`** en Cloudflare el 2026-10-04 y quedó asignado al
  servicio de Cloud Run ese mismo día.
- **Lo principal es ejecutar la metodología para la empresa que el visitante quiera**, bajo
  demanda, descargando el comunicado en ese momento. Lo ya ejecutado alimenta las tendencias.
- Alojado en **Cloud Run**, con el mismo patrón que `lease-lens` (un contenedor con web y API,
  `make deploy`).
- **Rediseño del sitio (2026-10-04, noche):** el análisis en vivo no usa el dataset del estudio,
  que queda solo para Market trends; se tiene que ver que el cálculo ocurre en el momento;
  gráficas de tendencias más grandes y más insights; Method habla del modelo de Perplexity (qué
  es, cómo está construido, por qué se usa), sin la validación y con poco espacio para los puntos
  débiles.

| Hecho | Pendiente |
|---|---|
| Estudio cerrado como nulo sin `lock`; nota de cierre en `PREREGISTRATION.md` | |
| `radar.py`, `radar_universe.py`, `validation.py`, comandos `radar` y `validate`, 9 tests nuevos (51 en verde) | |
| Validación del guidance con un segundo lector (Claude, a ciegas, 48 comunicados): 82 % de acuerdo estricto, 93 % en la dirección. Los "lowered" son el punto débil (7 de 9) | Que una persona repase `validation/guidance_labels.csv`. Las demás preguntas, incluidas las temáticas, están sin validar |
| Comunicados de 2025–2026 puntuados con las preguntas de texto: 754 peticiones, $0.63 reales ($0.79 estimados) | |
| Preguntas temáticas (aranceles, IA, cadena de suministro, reestructuración) sobre todo el histórico: 2.338 peticiones, $0.99 reales ($1.24 estimados). **Gasto acumulado del proyecto: $4.98 de $10** | |
| Dataset en `radar/`: 2.238 comunicados de 99 empresas, de 2021-01-13 a 2026-10-01; 79 filings descartados por no ser de resultados y 21 por duplicados | |
| `radar update` probado contra EDGAR en local: 20 segundos, no encuentra nada nuevo y deja el dataset igual | |
| Análisis bajo demanda (`ondemand.py`, `api.py`, 13 tests): busca los últimos Item 2.02 de cualquier empresa, lee el último comunicado de resultados y el anterior, y guarda cada lectura. Probado en local con AMD el 2026-10-04: 1,9 s y $0.0016 | Solo empresas que presentan resultados en un 8-K (quedan fuera casi todas las extranjeras). La comparación de una empresa de fuera del estudio es contra las 99 del estudio, no contra su sector |
| Topes del servicio: $0.25 al día, $4 en total, $0.03 por petición, 30 análisis por IP y hora, 2 instancias | El límite por IP vive en la memoria de cada instancia; el que protege de verdad es el tope diario, que se guarda en el bucket |
| Sitio Astro (103 páginas): portada con buscador de cualquier empresa, `/analyze/`, fichas del estudio, `/trends/`, `/method/` | |
| Rediseño del 2026-10-04 (noche), **desplegado esa noche** (commit `c38937c`, revisión `earnings-radar-00003-msk`): `Analyser.run()` emite los pasos reales y la API los sirve en `/api/analysis/{ticker}/stream`; el análisis ya no consulta `radar/`; portada reducida al buscador; página de análisis con panel en vivo, frase resumen y "What stands out"; tendencias con gráficas grandes, destacados automáticos, mapa de calor por sector y "quién dijo qué"; ficha de empresa convertida en histórico; Method reescrito con el modelo. 69 tests en verde, sitio compilado y revisado en el navegador con un sustituto del modelo (EDGAR real, gasto cero) | Comprobado en producción: páginas, búsqueda y el análisis de AMD por streaming servido desde el bucket sin gasto. Una lectura nueva con el modelo real no se ha probado tras el cambio (cuesta ≈ $0.0015). Las razones de "Why this model" en Method las redactó el agente: que el usuario las revise |
| | Con el cambio, cada empresa del estudio cuesta ≈ $0.0015 la primera vez que alguien la pide (antes salía gratis del dataset): como mucho ≈ $0.15 por las 99, dentro de los topes, que no se han tocado |
| `Makefile`: `api`, `dev`, `serve`, `deploy` (Cloud Run), `check`, `update`, `save`, `publish`. Sin GitHub Actions | `make update` no se ha probado con comunicados nuevos reales |
| **Desplegado el 2026-10-04** en Cloud Run: https://earnings-radar-3qwezbjyfq-ew.a.run.app (proyecto `arctic-robot-474306-g3`, `europe-west1`, servicio `earnings-radar`, bucket `arctic-robot-474306-g3-earnings-radar`, secreto `earnings-radar-perplexity-api-key`). Comprobado en producción: páginas, búsqueda, análisis de AMD en 3 s por $0.0016 y segunda petición servida desde el bucket | Dominio `earningsradar.app` asignado (8 registros DNS en Cloudflare, solo DNS). `www` sin configurar |
| | Las lecturas bajo demanda se quedan en el bucket; no entran en `radar/` ni en las tendencias |
| | El análisis del estudio cubre 99 empresas; ampliar ese universo exige pagar su histórico |
| Tarjeta "Earnings Radar" en `personal-website` (`src/data/profile.ts`, campo nuevo `liveUrl`), publicada en alejandrorodriguez.dev/projects/ con enlace al sitio | No se ha añadido a `featuredProjectNames` (la selección de la portada) |
| | Ampliar al S&P 500 (estimación previa: $8–12, por encima de lo que queda del tope) |

## 1. Qué se pidió (resumen del encargo)

- **Pregunta:** ¿predicen las señales que un modelo de decisión extrae de texto financiero
  los retornos posteriores de las acciones? Es un experimento de investigación. Un resultado
  nulo ("es ruido") es válido y hay que darlo sin adornos.
- **Ajuste posterior del usuario:** el modelo debe predecir **teniendo en cuenta la reacción inicial
  del precio**, es decir, si lo que viene será mejor o peor que esa reacción. Por eso la señal
  principal es "¿la noticia es mejor o peor de lo que implica la reacción del día 0?".
- **Fin último:** que la investigación respalde después un producto usable y publicable en
  internet.
- **Cambio de modelo y de nombre (2026-10-04):** el encargo original era evaluar Jev (TypeSafe
  System One), pero el pago de créditos en TypeSafe no funcionó. El estudio pasa a **Perplexity
  Decider v1 27B** (`pplx-decider-v1-27b`), un modelo de decisión con el mismo formato de
  preguntas y respuestas. Por decisión del usuario el proveedor **no es configurable** y el
  proyecto deja de llamarse "jev": repo `decision-signal-lab`, paquete y comando `decisionsignal`
  (antes `jev-signal-lab` y `jevsignal`).

### Reglas no negociables

1. **No es un sistema de trading.** No se escribe código que envíe órdenes ni que se conecte a
   un broker. Hay un conector de IBKR en algunas sesiones: **no se usa jamás**.
2. **Cero look-ahead.** Solo se usa información disponible al publicarse el texto, y el primer
   precio operable es posterior a la publicación. El modelo pudo ver estos eventos al entrenarse; ver
   las defensas en METHODOLOGY.
3. **Preguntar antes de gastar.** Antes de llamadas masivas a la API o de descargas grandes hay
   que pedir permiso al usuario con una estimación de coste.
4. **Muestra pequeña primero.** Se valida el pipeline de extremo a extremo antes de escalar.
5. **Claves fuera del repo.** Solo en `.env` (ignorado por git) o en variables de entorno.

El usuario escribe en español. Los documentos están en español y el código y sus comentarios en
inglés.

## 2. Dónde estamos

> 2026-10-06: `scripts/deploy-cloudrun.sh` ya solo escribe un permiso cuando falta (`grant`): antes cada
> despliegue reescribía la política IAM del proyecto y dos a la vez chocaban ("concurrent policy
> changes"). Ahora los despliegues de los tres servicios pueden lanzarse en paralelo. Comprobado
> contra el proyecto sin escribir nada; aún no se ha hecho un despliegue en paralelo de verdad.

> 2026-10-06: `site/src/components/HubNav.astro` lleva dos enlaces más de My Hub, `Analysis` y
> `Community` (páginas nuevas del portal), igual que `App.astro` de `market-hub-landing`. Desplegado el mismo día.

| Hecho | Pendiente |
|---|---|
| Pipeline completo (`src/decisionsignal/`), CLI `decisionsignal` | Validar el parser de EDGAR con filings **reales** |
| 41 tests en verde: cronología y look-ahead, texto, anonimización, cliente de Perplexity simulado, estadística y e2e sintético | Primera llamada real a Perplexity: confirmar el formato de respuesta y el `usage` (los tests usan el ejemplo de su documentación) |
| Descarga de precios (yfinance) probada con datos reales | Piloto con datos reales (~30 eventos de 2024 S2) |
| Pre-registro **en borrador** (`docs/PREREGISTRATION.md`) | Ajustar preguntas en el split de diseño, cerrar el pre-registro y `decisionsignal lock` |
| Repo en GitHub: `alejandrorodriguezalvarez884-dot/decision-signal-lab` | Escala completa: requiere **aprobación de coste** del usuario |
| Cliente adaptado a Perplexity Decider (único proveedor, fijado en `config.py`) | |
| Piloto sin modelo ejecutado dos veces el 2026-10-04 (14 empresas, 30 filings, 29 eventos de 2024 S2): horas de EDGAR, sesiones y retornos revisados y correctos. Estimación del piloto con modelo: $0.0205 | |
| Limpieza de texto corregida tras el primer piloto (`text.py`): la narrativa se corta en el primer estado financiero y se quitan secciones legales con títulos largos, mobiliario de página, contactos y notas de tablas. Texto mediano de 15.4k a 8.1k caracteres; total al 66 % | Anonimización: rompe nombres de producto ("the Company Watch") y deja frases como "the Company CEO". Sin arreglar |
| Piloto con Perplexity hecho el 2026-10-04: 175 peticiones, 0 errores, formato de respuesta y `usage` confirmados, $0.108 reales frente a $0.0205 estimados. Causa: la API cobra el texto una vez por pregunta. Estimador corregido | |
| Recortes por coste decididos por el usuario (tope total de $10, `DECIDER_TOTAL_MAX_USD`): universo S&P 100 de diciembre de 2020 (99 empresas con datos), 8 + 3 preguntas, variantes sin anonimizar solo en el 15 % de los eventos | |
| **Fase de diseño hecha el 2026-10-04:** 6.121 peticiones, 0 errores, $2.50 reales ($3.11 estimados). Gasto acumulado: $2.61 de $10. `DECIDER_MAX_USD` quedó en 4.00. Informe en `results/report.md` (1.529 comunicados de resultados, 80 semanas) | Decidir con el usuario: revisar la pregunta principal en el split de diseño o cerrar el pre-registro tal cual, `lock` y holdout ($1.19 estimados) |
| Resultado del diseño (exploratorio): la señal principal `react_anon__nvr` no predice `fwd_abn_20` (IC semanal −0.053, t −1.60, p 0.11; signo contrario al esperado). Correlaciona −0.70 con la reacción del día 0 y, quitada la reacción, su correlación con el retorno posterior es −0.006. La continuación de la reacción sí sale (IC +0.061, p 0.02) | La sonda de memoria da IC +0.055 (p 0.023): según el pre-registro eso activa la regla de contaminación (solo cuentan las variantes `*_anon`). Ojo: la sonda ve la reacción, así que puede estar recogiendo la continuación y no memoria |
| Pregunta principal revisada el 2026-10-04: tres candidatas (`CANDIDATE_QUESTIONS`, variante `cand_anon`) puntuadas sobre el diseño por $0.53. Gasto acumulado: $3.14 de $10. Ninguna predice en el sentido esperado: `facts_vs_reaction` IC −0.078 (t −2.12), `next_month` IC −0.095 (t −2.51), `lasting_news` × signo de la reacción IC +0.016 (t 0.48). Dependen menos de la reacción (ρ −0.46 y −0.49 frente a −0.71), pero quitada la reacción quedan en −0.044 y −0.047, no significativos | Decidir con el usuario qué pregunta queda como principal, quitar las candidatas descartadas de `questions.py` (cada pregunta cuesta ≈ $0.08 en el holdout), actualizar `features.py`/`report.py`, cerrar el pre-registro, `lock` y holdout |
| | La comparación raw frente a anon usa solo 233 eventos y 15 semanas: IC −0.263 frente a −0.254, sin ventaja del texto sin anonimizar, pero con mucho ruido |
| Descarga completa del S&P 100 hecha el 2026-10-04: 2.371 filings, 2.350 textos, 2.291 eventos (1.585 diseño, 706 holdout). Estimación del holdout: $1.19 | Las respuestas del piloto (preguntas antiguas) están apartadas en `data/interim/answers_pilot.parquet` |
| | Limpieza de texto a escala: 246 de 2.291 textos (11 %) llegan al tope de 24k caracteres y 95 conservan algún "(Unaudited)". Peor que en el piloto; sin arreglar |
| | Diseño de la pregunta principal: en el piloto el modelo nunca elige "worse" (P máxima 0.35) y `react_anon__nvr` correlaciona −0.72 con la reacción del día 0. Puede ser solo una apuesta de reversión; revisar en el split de diseño antes del lock |
| | Los 2 comunicados de ABNB (PDF con líneas partidas) siguen llegando al tope de 24k caracteres; uno conserva el inicio de la sección legal |

### Lo que falta que aporte el usuario

- `PERPLEXITY_API_KEY`, la clave de la API de Perplexity (https://console.perplexity.ai/project/keys).
  Requiere saldo de API en Perplexity.
- `DECIDER_RELEASE_DATE` en `.env`. Para `pplx-decider-v1-27b` es 2026-10-01 (fecha de publicación de
  su ficha en Hugging Face); falta que el usuario la confirme y la anote.
- `SEC_USER_AGENT` ya está en el `.env` del Mac personal, con el gmail del usuario. En otro
  equipo hay que volver a ponerlo.
- ¿Email de los commits? Los dos primeros commits llevan el email de Solera (configuración
  global del portátil de trabajo). En el Mac personal el repo usa la dirección `noreply` de la
  cuenta de GitHub (configuración local del repo). Falta que el usuario confirme si lo prefiere así.

## 3. Puesta en marcha en un ordenador nuevo

```bash
git clone git@github.com:alejandrorodriguezalvarez884-dot/decision-signal-lab.git
cd decision-signal-lab
uv sync                 # instala Python 3.12 y las dependencias desde uv.lock
cp .env.example .env    # rellenar PERPLEXITY_API_KEY, SEC_USER_AGENT (y DECIDER_MAX_USD)
uv run pytest           # debe salir todo en verde
```

- **SSH:** en el portátil original el remoto usa el alias
  `git@github.com-alejandrorodriguezalvarez884:...`, definido en su `~/.ssh/config`. En otro
  equipo vale `git@github.com:...` o HTTPS, según cómo esté configurado.
- **`gh`:** no estaba autenticado en el equipo original. No hace falta para nada de lo que hay.
- **`data/` no está en git.** Se regenera con el pipeline: cachés HTTP de EDGAR, parquets
  intermedios y la caché de respuestas del modelo.
  - **Ojo con `data/cache/decision_cache.sqlite` cuando haya llamadas reales:** contiene respuestas
    pagadas y es el registro auditable de lo que se preguntó.
  - Al cambiar de máquina, cópiala a mano (no lleva secretos).
  - Si no se copia, se vuelve a pagar y las respuestas pueden variar un poco.

## 4. Próximos pasos, en orden

1. **Piloto sin modelo** (gratis; solo necesita `SEC_USER_AGENT`):
   ```bash
   uv run decisionsignal pilot --skip-model
   ```
   Hay que revisar a mano:
   - **Filings:** en `data/interim/filings.parquet`, que `accepted_et` coincide con la hora
     "Accepted" que muestra EDGAR en 3–4 filings y que `exhibit_url` apunta al comunicado de
     prensa.
   - **Textos:** en `data/interim/texts.parquet`, que el texto es narrativa limpia y la tabla
     de resultados ha desaparecido, y que la anonimización no rompe frases.
   - **Eventos:** en `data/interim/events.parquet`, que `r0_abn` y `fwd_abn_*` cuadran con
     algún caso conocido. Por ejemplo, AAPL publicó el 31-10-2024 tras el cierre, así que el
     día 0 es el 1-11 y la entrada el 4-11.
2. **Piloto con el modelo** (hecho el 2026-10-04; costó $0.108, dentro del tope por defecto `DECIDER_MAX_USD=1.00`):
   ```bash
   uv run decisionsignal pilot
   ```
   Hay que revisar en `data/interim/answers.parquet` que no hay filas con `error` (Perplexity
   rechaza una petición mal formada con 400) y que las probabilidades tienen sentido. Con unos 30 eventos la estadística **no significa nada**: solo
   valida el pipeline.
3. Anotar en `.env` la fecha de lanzamiento del modelo como `DECIDER_RELEASE_DATE`. Sale de la
   ficha del modelo en Hugging Face; no hay comando para consultarla porque
   Perplexity no tiene endpoint de modelos.
4. **Escala completa del split de diseño (2021–2024):**
   1. `universe`, `filings`, `texts`, `prices`, `events`.
   2. `uv run decisionsignal estimate --split design --n-cf 300`.
   3. **Enseñar la estimación al usuario y esperar su aprobación.**
   4. Subir `DECIDER_MAX_USD` a lo aprobado y lanzar `score --split design --n-cf 300`.
   5. `report`.
   - Coste esperado de todo el estudio: unos $35–40 de API (el texto se cobra una vez por
     pregunta) y 1–2 GB de EDGAR. La descarga de
     EDGAR también requiere el visto bueno del usuario.
5. Iterar las preguntas **solo** con datos del split de diseño. Después:
   1. Cerrar `docs/PREREGISTRATION.md` (quitar "BORRADOR").
   2. Commit.
   3. `uv run decisionsignal lock` y commit de `PREREGISTRATION.lock.json`.
6. Holdout: `score --split holdout` y luego `report --holdout`, **una sola vez**. Contar el
   resultado con honestidad, aplicando las reglas del pre-registro.
7. Producto/publicación: solo si hay señal en el holdout. Si no la hay, se publica el resultado
   nulo como tal.

## 5. Decisiones clave (y por qué)

Detalle completo en [METHODOLOGY.md](METHODOLOGY.md).

- **Texto:** comunicados de resultados (8-K Item 2.02, EX-99.1) de EDGAR. Son gratuitos y
  públicos, y tienen hora de aceptación exacta.
- **Momento:** la hora "Accepted" de la página índice de EDGAR, en hora del Este. El campo del
  JSON de submissions tiene una "Z" poco fiable y solo sirve de contraste.
- **Cronología:**
  - La reacción R0 va del cierre previo a la publicación al cierre del día 0 (primera sesión
    que *abre* después de la publicación).
  - La entrada es la apertura de la sesión siguiente al día 0.
  - Todo lo que ve el modelo termina en el cierre del día 0.
- **Universo:** S&P 100 a 21-12-2020 (lista fija en `config.py`), con la pertenencia histórica
  al S&P 500 (fja05680/sp500, licencia MIT). Decisión del usuario para abaratar el estudio. Riesgo de supervivencia:
  medido, no eliminado.
- **Modelo:** fijado en `pplx-decider-v1-27b` (Perplexity), sin alternativa configurable.
- **Señal principal:** `react_anon__nvr` = P(better) − P(worse), con texto anonimizado más la
  reacción, frente a `fwd_abn_20`.
- **Enfoque A frente a B:**
  - A: el modelo ve la reacción.
  - B: el modelo solo lee el texto y el código lo compara con la reacción.
  - Si A no supera a B, que el modelo "vea" la reacción no aporta nada.
- **Contaminación:** anonimización, sonda de memoria sin texto, holdout 2025+ y submuestra
  posterior al lanzamiento del modelo.
- **Estadística:** la unidad de independencia es la semana de entrada (temporada de resultados):
  Fama-MacBeth semanal con Newey-West y distribución t, bootstrap por semanas, placebo con
  permutación dentro de cada semana y regresión con errores agrupados por semana.
  - Se cambió de la normal a la t porque, con pocas semanas, la normal daba falsos positivos
    sobre ruido puro.
- **Potencia:** solo se detectan IC de ≈ 0.06 o más. Un nulo no descarta efectos pequeños.

## 6. Mapa del código

`README.md` tiene la estructura completa. Los dos archivos que definen el diseño, y que hay que
revisar antes de cualquier cambio, son:
- `src/decisionsignal/config.py`: fechas, horizontes, precios de la API y límites.
- `src/decisionsignal/questions.py`: todas las preguntas al modelo.

Cualquier cambio en estos dos, en `features.py` o en el pre-registro después del `lock` bloquea
el holdout hasta registrar la desviación y volver a bloquear (es intencionado).
