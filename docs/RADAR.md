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

## Análisis bajo demanda

Lo principal del producto: el visitante escribe cualquier empresa y el servicio ejecuta la
metodología en ese momento (`ondemand.py`, `api.py`).

1. Resuelve el ticker con la lista de la SEC (`company_tickers.json`).
2. Lista sus 8-K con Item 2.02 de los últimos 14 meses y los recorre del más nuevo al más
   antiguo, hasta 6, buscando el último comunicado de resultados y el anterior.
3. De cada filing que nadie ha leído aún descarga el comunicado, lo limpia, oculta nombres y
   fechas y le hace al modelo las mismas preguntas que al estudio (texto y temas).
4. Guarda la lectura. La siguiente petición de esa empresa no gasta nada.

Los filings que ya están en `radar/releases.json` (las 99 empresas del estudio) se sirven de
ahí, sin llamar al modelo.

Límites para que nadie gaste de más con tu clave:

| Límite | Valor | Dónde |
|---|---|---|
| Gasto máximo del servicio por día (UTC) | $0.25 | `RADAR_DAILY_MAX_USD`, se fija al desplegar |
| Gasto máximo del servicio en toda su vida | $4.00 | `RADAR_TOTAL_MAX_USD`, se fija al desplegar |
| Gasto máximo por petición | $0.03 | `ONDEMAND_REQUEST_MAX_USD` en `config.py` |
| Análisis por dirección IP y hora | 30 | `ONDEMAND_PER_IP_PER_HOUR` en `config.py` |
| Instancias simultáneas | 2 | `MAX_INSTANCES` al desplegar |

Un análisis nuevo cuesta unos $0.0015 (dos comunicados). Al llegar a un tope, las empresas ya
leídas siguen funcionando y las nuevas responden con un aviso. El tope total existe para que el
proyecto no pase de los $10 que fijó el usuario; para subirlo: `RADAR_TOTAL_MAX_USD=8 make deploy`.

API: `GET /api/health`, `GET /api/companies?q=`, `GET /api/analysis/{ticker}`.

## El sitio

`site/` es un sitio Astro estático que lee `radar/*.json`:

- **Portada (`/`)**: buscador. Las empresas del estudio se filtran al escribir; cualquier otra
  la sugiere la API y abre el análisis bajo demanda.
- **Análisis bajo demanda (`/analyze/?ticker=`)**: página vacía que pide el análisis a la API
  y lo dibuja en el navegador (`site/src/lib/reading.ts` tiene la lógica compartida).
- **Ficha de empresa del estudio (`/company/<ticker>/`)**: el mismo análisis más el histórico
  desde 2021 y la comparación con sus pares de sector.
- **Market trends (`/trends/`)**: los agregados por trimestre y sector de lo ya ejecutado.
- **Method (`/method/`)**: preguntas exactas, validación y el estudio que salió nulo.

## Comandos (`make`)

Nada se ejecuta solo ni en GitHub Actions. Todo se lanza a mano desde el `Makefile`:

| Comando | Qué hace | Gasta |
|---|---|---|
| `make` | Lista los comandos | No |
| `make api` + `make dev` | API en el puerto 8000 y sitio en el 4321, ambos con recarga | Solo si analizas una empresa nueva |
| `make serve` | Sitio y API juntos en http://localhost:8080, como en producción | Igual |
| `make deploy` | Construye y despliega el servicio en Cloud Run | No |
| `make check` | Mira si las empresas del estudio tienen comunicados nuevos y cuánto costaría puntuarlos | No |
| `make update` | Los descarga y puntúa, y reescribe `radar/` | Sí, hasta `MAX_USD` ($0.25) |
| `make save` | Hace commit de `radar/` y sube la rama | No |
| `make publish` | `update` + `save` + `deploy` | Sí |
| `make test` / `make install` | Tests y dependencias | No |

Los comandos de debajo siguen disponibles: `uv run decisionsignal radar estimate|build|check|update|summary`.

## Despliegue en Cloud Run

En producción: https://earnings-radar-3qwezbjyfq-ew.a.run.app

Mismo patrón que `lease-lens`: un solo contenedor con el sitio estático servido por la app
FastAPI, así que web y API comparten origen. `make deploy` ejecuta
`scripts/deploy-cloudrun.sh`, que:

1. Activa las APIs necesarias y da permisos a la cuenta de servicio por defecto.
2. Sube `PERPLEXITY_API_KEY` de `.env` a Secret Manager (`earnings-radar-perplexity-api-key`).
3. Crea el bucket `gs://<proyecto>-earnings-radar`, donde se guarda cada análisis y el gasto
   de cada día. Sin él cada arranque en frío volvería a pagar.
4. Construye la imagen con Cloud Build (no hace falta Docker en local) y despliega el
   servicio `earnings-radar` en `europe-west1`, con escalado a cero.

`.gcloudignore` deja fuera `.env` y `data/`. Variables opcionales: `GCP_PROJECT`, `GCP_REGION`,
`SERVICE_NAME`, `MAX_INSTANCES`, `RADAR_DAILY_MAX_USD`, `RADAR_TOTAL_MAX_USD`.

La imagen lleva dentro `radar/`, así que tras `make update` hay que volver a desplegar para
que el servicio y las tendencias vean los datos nuevos (`make publish` lo hace todo).

**Dominio propio.** Cuando esté comprado en Cloudflare: asignarlo al servicio de Cloud Run
(`gcloud beta run domain-mappings create --service earnings-radar --domain <dominio> --region europe-west1`),
crear en Cloudflare los registros DNS que indique ese comando, y escribir la dirección en
`site/SITE_URL` para los enlaces canónicos.

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
