# JevSignalDecisor

Proyecto de investigación. Pregunta: **cuando sale un comunicado de resultados y el precio ya ha
reaccionado, ¿sabe Jev (TypeSafe System One) si la noticia es mejor o peor de lo que esa reacción
descuenta?** Si lo sabe, su juicio debería predecir el retorno anormal de las semanas siguientes.

Si el resultado es "no hay señal", se dirá así.

> No es un sistema de trading. No hay código que envíe órdenes ni que se conecte a un broker.
> Las carteras long-short del informe son de papel.

## Cómo funciona

1. **Texto:** comunicados de resultados de empresas del S&P 500 (8-K Item 2.02, EX-99.1) desde
   2021, sacados de EDGAR con su hora exacta de aceptación.
2. **Reacción:** retorno anormal del día 0 (primera sesión completa tras la publicación) frente
   a SPY, escalado por la volatilidad normal de la acción.
3. **Jev:** lee el comunicado (anonimizado) y una frase con la reacción, y responde preguntas
   tipadas. La principal es *¿la noticia es mejor, igual o peor de lo que la reacción implica?*
   Todas las preguntas están en [`src/jevsignal/questions.py`](src/jevsignal/questions.py).
4. **Retorno a predecir:** desde la apertura del día siguiente al día 0 hasta 1, 5, 20 o 60
   sesiones, menos SPY.
5. **Evaluación:** IC semanal, placebo, quintiles y regresión incremental frente a baselines
   (deriva post-resultados, reversión, diccionario Loughran-McDonald), con un holdout 2025–2026
   sellado por pre-registro.

Diseño completo y limitaciones: [docs/METHODOLOGY.md](docs/METHODOLOGY.md). Hipótesis y reglas
de decisión fijadas de antemano: [docs/PREREGISTRATION.md](docs/PREREGISTRATION.md).

## Puesta en marcha

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # y rellena TYPESAFE_API_KEY y SEC_USER_AGENT
uv run pytest
```

Las claves solo viven en `.env`, que git ignora, o en variables de entorno. Nunca en el repo.

## Uso

```bash
uv run jevsignal pilot --skip-jev       # piloto con datos reales sin llamar a Jev (~30 eventos de 2024 S2)
uv run jevsignal pilot                  # piloto completo (< $0.10 de Jev)
```

Escala completa, paso a paso (cada paso escribe en `data/interim/` y se puede repetir):

```bash
uv run jevsignal universe
uv run jevsignal filings                # ~1-2 GB de EDGAR en caché, a <= 8 peticiones/s
uv run jevsignal texts
uv run jevsignal prices
uv run jevsignal events
uv run jevsignal estimate --split design --n-cf 300   # coste ANTES de gastar
uv run jevsignal score    --split design --n-cf 300   # respeta el tope JEV_MAX_USD
uv run jevsignal report                                # solo diseño (exploratorio)
# afinar preguntas en el split de diseño -> cerrar docs/PREREGISTRATION.md -> commit
uv run jevsignal lock
uv run jevsignal score  --split holdout
uv run jevsignal report --holdout                      # resultado confirmatorio, una sola vez
```

Los resultados van a `results/`: `report.md`, `results.json`, figuras e informes de cobertura.

## Estructura

```
src/jevsignal/
  config.py      constantes del estudio (fechas, horizontes, precios, límites)
  universe.py    S&P 500 en cada fecha + CIK
  edgar.py       8-K Item 2.02, hora de aceptación, EX-99
  text.py        HTML -> narrativa (sin tablas ni texto legal)
  anonymize.py   oculta empresa, ticker y fechas
  prices.py      precios diarios ajustados
  events.py      cronología del evento, reacción y retornos (cero look-ahead)
  questions.py   TODAS las preguntas a Jev + traducción de números a palabras
  jev.py         cliente HTTP con caché permanente y tope de gasto
  score.py       variantes de petición por evento
  features.py    respuestas -> señales
  baselines.py   señales sin Jev
  analysis.py    estadística
  prereg.py      sello del holdout
  report.py      informe
tests/           look-ahead, limpieza de texto, cliente, estadística, e2e sintético
```
