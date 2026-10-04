# Estado del proyecto y cómo continuar

Última actualización: 2026-10-04. Este documento basta para retomar el trabajo en otro
ordenador o en otra sesión de agente, sin el historial de la conversación.

## 1. Qué se pidió (resumen del encargo)

- **Pregunta:** ¿predicen las señales que Jev (TypeSafe, "System One") extrae de texto financiero
  los retornos posteriores de las acciones? Es un experimento de investigación. Un resultado
  nulo ("es ruido") es válido y hay que darlo sin adornos.
- **Ajuste posterior del usuario:** Jev debe predecir **teniendo en cuenta la reacción inicial
  del precio**, es decir, si lo que viene será mejor o peor que esa reacción. Por eso la señal
  principal es "¿la noticia es mejor o peor de lo que implica la reacción del día 0?".
- **Fin último:** que la investigación respalde después un producto usable y publicable en
  internet.
- **Cambio de modelo (2026-10-04):** el pago de créditos en TypeSafe no funcionó, así que el
  estudio pasa a **Perplexity Decider v1 27B** (`pplx-decider-v1-27b`), un modelo de decisión
  con el mismo formato de preguntas y respuestas. En este documento "Jev" designa a Perplexity
  Decider. Por decisión del usuario el proveedor **no es configurable**: el código solo llama a
  Perplexity y ya no puede llamar a TypeSafe.

### Reglas no negociables

1. **No es un sistema de trading.** No se escribe código que envíe órdenes ni que se conecte a
   un broker. Hay un conector de IBKR en algunas sesiones: **no se usa jamás**.
2. **Cero look-ahead.** Solo se usa información disponible al publicarse el texto, y el primer
   precio operable es posterior a la publicación. Jev pudo ver estos eventos al entrenarse; ver
   las defensas en METHODOLOGY.
3. **Preguntar antes de gastar.** Antes de llamadas masivas a la API o de descargas grandes hay
   que pedir permiso al usuario con una estimación de coste.
4. **Muestra pequeña primero.** Se valida el pipeline de extremo a extremo antes de escalar.
5. **Claves fuera del repo.** Solo en `.env` (ignorado por git) o en variables de entorno.

El usuario escribe en español. Los documentos están en español y el código y sus comentarios en
inglés.

## 2. Dónde estamos

| Hecho | Pendiente |
|---|---|
| Pipeline completo (`src/jevsignal/`), CLI `jevsignal` | Validar el parser de EDGAR con filings **reales** |
| 33 tests en verde: cronología y look-ahead, texto, anonimización, cliente de Perplexity simulado, estadística y e2e sintético | Primera llamada real a Perplexity: confirmar el formato de respuesta y el `usage` (los tests usan el ejemplo de su documentación) |
| Descarga de precios (yfinance) probada con datos reales | Piloto con datos reales (~30 eventos de 2024 S2) |
| Pre-registro **en borrador** (`docs/PREREGISTRATION.md`) | Ajustar preguntas en el split de diseño, cerrar el pre-registro y `jevsignal lock` |
| Repo en GitHub: `alejandrorodriguezalvarez884-dot/jev-signal-lab` | Escala completa: requiere **aprobación de coste** del usuario |
| Cliente adaptado a Perplexity Decider (único proveedor, fijado en `config.py`) | |

### Lo que falta que aporte el usuario

- `PERPLEXITY_API_KEY`, la clave de la API de Perplexity (https://console.perplexity.ai/project/keys).
  Requiere saldo de API en Perplexity.
- `JEV_RELEASE_DATE` en `.env`. Para `pplx-decider-v1-27b` es 2026-10-01 (fecha de publicación de
  su ficha en Hugging Face); falta que el usuario la confirme y la anote.
- `SEC_USER_AGENT` ya está en el `.env` del Mac personal, con el gmail del usuario. En otro
  equipo hay que volver a ponerlo.
- ¿Email de los commits? Los dos primeros commits llevan el email de Solera (configuración
  global del portátil de trabajo). En el Mac personal el repo usa la dirección `noreply` de la
  cuenta de GitHub (configuración local del repo). Falta que el usuario confirme si lo prefiere así.

## 3. Puesta en marcha en un ordenador nuevo

```bash
git clone git@github.com:alejandrorodriguezalvarez884-dot/jev-signal-lab.git
cd jev-signal-lab
uv sync                 # instala Python 3.12 y las dependencias desde uv.lock
cp .env.example .env    # rellenar PERPLEXITY_API_KEY, SEC_USER_AGENT (y JEV_MAX_USD)
uv run pytest           # debe salir todo en verde
```

- **SSH:** en el portátil original el remoto usa el alias
  `git@github.com-alejandrorodriguezalvarez884:...`, definido en su `~/.ssh/config`. En otro
  equipo vale `git@github.com:...` o HTTPS, según cómo esté configurado.
- **`gh`:** no estaba autenticado en el equipo original. No hace falta para nada de lo que hay.
- **`data/` no está en git.** Se regenera con el pipeline: cachés HTTP de EDGAR, parquets
  intermedios y la caché de Jev.
  - **Ojo con `data/cache/jev_cache.sqlite` cuando haya llamadas reales:** contiene respuestas
    pagadas y es el registro auditable de lo que se preguntó.
  - Al cambiar de máquina, cópiala a mano (no lleva secretos).
  - Si no se copia, se vuelve a pagar y las respuestas pueden variar un poco.

## 4. Próximos pasos, en orden

1. **Piloto sin Jev** (gratis; solo necesita `SEC_USER_AGENT`):
   ```bash
   uv run jevsignal pilot --skip-jev
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
2. **Piloto con Jev** (estimado en menos de $0.10, dentro del tope por defecto `JEV_MAX_USD=1.00`):
   ```bash
   uv run jevsignal pilot
   ```
   Hay que revisar en `data/interim/answers.parquet` que no hay filas con `error` (Perplexity
   rechaza una petición mal formada con 400) y que las probabilidades tienen sentido. Con unos 30 eventos la estadística **no significa nada**: solo
   valida el pipeline.
3. Anotar en `.env` la fecha de lanzamiento del modelo como `JEV_RELEASE_DATE`. Sale de la
   ficha del modelo en Hugging Face; el comando `jevsignal models` ya no existe porque
   Perplexity no tiene endpoint de modelos.
4. **Escala completa del split de diseño (2021–2024):**
   1. `universe`, `filings`, `texts`, `prices`, `events`.
   2. `uv run jevsignal estimate --split design --n-cf 300`.
   3. **Enseñar la estimación al usuario y esperar su aprobación.**
   4. Subir `JEV_MAX_USD` a lo aprobado y lanzar `score --split design --n-cf 300`.
   5. `report`.
   - Coste esperado de todo el estudio: unos $12–16 de API y 1–2 GB de EDGAR. La descarga de
     EDGAR también requiere el visto bueno del usuario.
5. Iterar las preguntas **solo** con datos del split de diseño. Después:
   1. Cerrar `docs/PREREGISTRATION.md` (quitar "BORRADOR").
   2. Commit.
   3. `uv run jevsignal lock` y commit de `PREREGISTRATION.lock.json`.
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
  - Todo lo que ve Jev termina en el cierre del día 0.
- **Universo:** S&P 500 histórico (fja05680/sp500, licencia MIT). Riesgo de supervivencia:
  medido, no eliminado.
- **Modelo:** fijado en `pplx-decider-v1-27b` (Perplexity), sin alternativa configurable.
- **Señal principal:** `react_anon__nvr` = P(better) − P(worse), con texto anonimizado más la
  reacción, frente a `fwd_abn_20`.
- **Enfoque A frente a B:**
  - A: Jev ve la reacción.
  - B: Jev solo lee el texto y el código lo compara con la reacción.
  - Si A no supera a B, que Jev "vea" la reacción no aporta nada.
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
- `src/jevsignal/config.py`: fechas, horizontes, precios de la API y límites.
- `src/jevsignal/questions.py`: todas las preguntas a Jev.

Cualquier cambio en estos dos, en `features.py` o en el pre-registro después del `lock` bloquea
el holdout hasta registrar la desviación y volver a bloquear (es intencionado).
