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
4. Guarda la lectura, con la hora (`read_utc`). La siguiente petición de ese filing no gasta nada.

**El dataset del estudio no se consulta** (decisión del usuario, 2026-10-04): `radar/` alimenta
solo las tendencias. Una empresa del estudio se lee en vivo como cualquier otra la primera vez
que alguien la pide (unos $0.0015) y después sale del almacén de lecturas bajo demanda.

`Analyser.run()` es un generador que emite cada paso real mientras ocurre (`edgar`, `filings`,
`download`, `model`, `read`, `done`). La API lo sirve en `/api/analysis/{ticker}/stream`, una
línea JSON por paso, y la página de análisis lo dibuja como un panel "Running live". Entre la
llamada al modelo y el guardado no hay ningún `yield`: si el visitante se va, la lectura pagada
se guarda igualmente.

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

API: `GET /api/health`, `GET /api/companies?q=`, `GET /api/analysis/{ticker}` y
`GET /api/analysis/{ticker}/stream` (el mismo análisis, paso a paso; es el que usa la web).

## El sitio

`site/` es un sitio Astro estático que lee `radar/*.json`:

- **Portada (`/`)**: solo el buscador (`CompanySearch.astro`, con sugerencias de la API para
  cualquier empresa), ejemplos, los tres pasos y un avance de las tendencias. Todo resultado
  abre el análisis en vivo.
- **Análisis en vivo (`/analyze/?ticker=`)**: pide el análisis por streaming, muestra los pasos
  reales mientras corre y dibuja el resultado: frase resumen, cuatro lecturas con medidor, "What
  stands out" (seguridad del modelo, posición frente a las 99 empresas, respuestas raras o
  dudosas), "What changed", probabilidades de guidance, escalas con la lectura anterior y la
  mediana, y una tarjeta por tema. La lógica de textos está en `site/src/lib/reading.ts`
  (`headline`, `standouts`, `changesSince`).
- **Market trends (`/trends/`)**: el único sitio que usa el dataset del estudio. Cifras del
  último trimestre con su serie, "What stands out" (récords y mayores cambios interanuales,
  `highlights()` en `radar.ts`), guidance, gráficas grandes por grupo (`SERIES` en `radar.ts`),
  mapa de calor por sector, quién dijo qué en el trimestre y el listado de las 99 empresas.
- **Histórico de una empresa del estudio (`/company/<ticker>/`)**: sus comunicados desde 2021
  (gráficas y tabla) y un botón al análisis en vivo. Cuelga de Market trends.
- **Method (`/method/`)**: el recorrido del texto, el modelo (qué es, cómo está construido y
  por qué se usa, con datos de su ficha en Hugging Face) y las preguntas exactas. Por decisión
  del usuario no explica la validación ni se extiende en los puntos débiles; el estudio nulo
  queda en un párrafo.

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

En producción: **https://earningsradar.app** (la dirección propia de Cloud Run,
https://earnings-radar-3qwezbjyfq-ew.a.run.app, sigue funcionando).

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

El sitio se construye con `radar/` dentro, así que tras `make update` hay que volver a
desplegar para que las tendencias vean los datos nuevos (`make publish` lo hace todo). El
servicio de análisis ya no lee `radar/`.

**Dominio.** `earningsradar.app` está registrado en Cloudflare (cuenta
`alejandrorodriguezalvarez884@gmail.com`, renueva el 2027-10-04) y asignado al servicio con un
*domain mapping* de Cloud Run en `europe-west1`. En el DNS de Cloudflare hay 4 registros A y 4
AAAA en la raíz que apuntan a Google, todos en modo "DNS only" (sin proxy, para que Google pueda
emitir y renovar el certificado), más el TXT de verificación de Google, que no hay que borrar.
`www.earningsradar.app` no está configurado. La dirección pública del sitio para los enlaces
canónicos está en `site/SITE_URL`.

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
