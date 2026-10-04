# DecisionSignalLab

Proyecto de investigación. Pregunta: **cuando sale un comunicado de resultados y el precio ya ha
reaccionado, ¿sabe un modelo de decisión si la noticia es mejor o peor de lo que esa reacción
descuenta?** Si lo sabe, su juicio debería predecir el retorno anormal de las semanas siguientes.

> **Modelo:** el estudio se ejecuta sobre **Perplexity Decider v1 27B** (`pplx-decider-v1-27b`,
> Decisions API de Perplexity), un modelo de decisión: recibe un texto y preguntas tipadas y
> devuelve probabilidades en lugar de texto. En estos documentos, "el modelo" es ese.

Si el resultado es "no hay señal", se dirá así.

> No es un sistema de trading. No hay código que envíe órdenes ni que se conecte a un broker.
> Las carteras long-short del informe son de papel.

## Cómo funciona

1. **Texto:** comunicados de resultados de empresas del S&P 500 (8-K Item 2.02, EX-99.1) desde
   2021, sacados de EDGAR con su hora exacta de aceptación.
2. **Reacción:** retorno anormal del día 0 (primera sesión completa tras la publicación) frente
   a SPY, escalado por la volatilidad normal de la acción.
3. **Modelo de decisión:** lee el comunicado (anonimizado) y una frase con la reacción, y responde preguntas
   tipadas. La principal es *¿la noticia es mejor, igual o peor de lo que la reacción implica?*
   Todas las preguntas están en [`src/decisionsignal/questions.py`](src/decisionsignal/questions.py).
4. **Retorno a predecir:** desde la apertura del día siguiente al día 0 hasta 1, 5, 20 o 60
   sesiones, menos SPY.
5. **Evaluación:** IC semanal, placebo, quintiles y regresión incremental frente a baselines
   (deriva post-resultados, reversión, diccionario Loughran-McDonald), con un holdout 2025–2026
   sellado por pre-registro.

**Para retomar el trabajo (otra sesión u ordenador): [docs/HANDOFF.md](docs/HANDOFF.md).**

Diseño completo y limitaciones: [docs/METHODOLOGY.md](docs/METHODOLOGY.md). Hipótesis y reglas
de decisión fijadas de antemano: [docs/PREREGISTRATION.md](docs/PREREGISTRATION.md).

## Puesta en marcha

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # y rellena PERPLEXITY_API_KEY y SEC_USER_AGENT
uv run pytest
```

Las claves solo viven en `.env`, que git ignora, o en variables de entorno. Nunca en el repo.

## Uso

```bash
uv run decisionsignal pilot --skip-model   # piloto con datos reales sin llamar al modelo (~30 eventos de 2024 S2)
uv run decisionsignal pilot                # piloto completo (< $0.10 de API)
```

Escala completa, paso a paso (cada paso escribe en `data/interim/` y se puede repetir):

```bash
uv run decisionsignal universe
uv run decisionsignal filings              # ~1-2 GB de EDGAR en caché, a <= 8 peticiones/s
uv run decisionsignal texts
uv run decisionsignal prices
uv run decisionsignal events
uv run decisionsignal estimate --split design --n-cf 300   # coste ANTES de gastar
uv run decisionsignal score    --split design --n-cf 300   # respeta el tope DECIDER_MAX_USD
uv run decisionsignal report                                # solo diseño (exploratorio)
# afinar preguntas en el split de diseño -> cerrar docs/PREREGISTRATION.md -> commit
uv run decisionsignal lock
uv run decisionsignal score  --split holdout
uv run decisionsignal report --holdout                      # resultado confirmatorio, una sola vez
```

Los resultados van a `results/`: `report.md`, `results.json`, figuras e informes de cobertura.

## Estructura

```
src/decisionsignal/
  config.py      constantes del estudio (fechas, horizontes, precios, límites)
  universe.py    S&P 500 en cada fecha + CIK
  edgar.py       8-K Item 2.02, hora de aceptación, EX-99
  text.py        HTML -> narrativa (sin tablas ni texto legal)
  anonymize.py   oculta empresa, ticker y fechas
  prices.py      precios diarios ajustados
  events.py      cronología del evento, reacción y retornos (cero look-ahead)
  questions.py   TODAS las preguntas al modelo + traducción de números a palabras
  client.py      cliente HTTP de Perplexity Decider con caché permanente y tope de gasto
  score.py       variantes de petición por evento
  features.py    respuestas -> señales
  baselines.py   señales sin el modelo
  analysis.py    estadística
  prereg.py      sello del holdout
  report.py      informe
tests/           look-ahead, limpieza de texto, cliente, estadística, e2e sintético
```
