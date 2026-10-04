# Metodología, decisiones y limitaciones

## Objetivo

Averiguar si un modelo de decisión extrae del texto de un comunicado de resultados
información que el precio **todavía no** ha incorporado tras la reacción inicial. Es investigación,
no un sistema de trading: aquí no hay código que envíe órdenes ni que se conecte a un broker, y
todas las carteras son de papel.

> **Modelo:** el estudio se ejecuta sobre **Perplexity Decider v1 27B** (`pplx-decider-v1-27b`,
> Decisions API de Perplexity), un modelo de decisión: recibe un texto y preguntas tipadas y
> devuelve probabilidades en lugar de texto. En estos documentos, "el modelo" es ese.

## Datos

| Qué | Fuente | Por qué |
|---|---|---|
| Texto | EDGAR: 8-K con Item 2.02, exhibit EX-99 (normalmente el 99.1) | Gratuito, de dominio público y con hora de aceptación exacta |
| Momento de publicación | Hora "Accepted" de la página índice del filing (hora del Este de EE. UU.) | Es conservador: el mismo comunicado suele salir antes por agencia, nunca después |
| Universo | Composición histórica del S&P 500 ([fja05680/sp500](https://github.com/fja05680/sp500), MIT) | Evita usar los miembros actuales para el pasado |
| Ticker → CIK | `company_tickers.json` de la SEC más una tabla de cambios de ticker | Solo conoce tickers actuales (ver limitaciones) |
| Precios | Yahoo Finance (yfinance), diarios y ajustados | Gratis. Se toman la acción, SPY y los ETF sectoriales SPDR |
| Baseline léxico | Diccionario Loughran-McDonald (`pysentiment2`) | Es el estándar en finanzas |

Periodo: de 2021-01-01 hasta hoy. El **split de diseño** cubre 2021–2024; ahí se pueden ajustar
las preguntas. El **holdout** empieza el 2025-01-01, está sellado hasta el pre-registro y solo se
evalúa una vez.

## Cronología de un evento (cero look-ahead)

```
cierre base ── publicación t ── [sesión día 0: reacción R0] ── noche: decisión ── apertura de entrada ── … cierre h
```

- **Sesión base:** la última cuyo cierre es igual o anterior a `t`.
- **Día 0:** la primera sesión cuya apertura es *posterior* a `t`.
- **R0:** del cierre base al cierre del día 0, menos lo que hizo SPY en la misma ventana.
  - Se escala por la volatilidad diaria anormal de la acción en las 60 sesiones previas (`r0_z`).
  - Si el comunicado sale en mitad de la sesión, esa sesión queda fuera de R0 y del retorno
    futuro. Se pierde un poco de información, pero no se mira el futuro.
- **Entrada:** la apertura de la sesión siguiente al día 0.
- **Retorno futuro:** de la apertura de entrada al cierre de la sesión `h` (h = 1, 5, 20 o 60),
  menos SPY. Como secundario, menos el ETF del sector.

Los tests (`tests/test_events.py`) cubren los casos límite: comunicados antes de la apertura,
durante la sesión, después del cierre y en fin de semana, y la media sesión de Acción de Gracias.

## Qué hace el modelo

Por cada evento se hacen cinco variantes, cada una en una sola llamada con todas sus preguntas
(definidas en `src/decisionsignal/questions.py`):

| Variante | Qué ve el modelo | Para qué |
|---|---|---|
| `text_raw` / `text_anon` | Solo el comunicado | Rasgos del texto: guidance, tono, demanda, márgenes, extraordinarios… |
| `react_raw` / `react_anon` | Comunicado + frase con la reacción | **Juicio principal:** ¿la noticia es mejor o peor de lo que refleja el precio? |
| `probe` | Empresa, fecha y reacción, **sin comunicado** | Sonda de memoria |
| `cf_*` (submuestra) | Comunicado anonimizado + reacciones inventadas | ¿Usa el modelo realmente la reacción? |

Al modelo se le pregunta por lenguaje, no por aritmética, así que el código traduce la reacción a
palabras ("cerró un 7.1 % por debajo del mercado: un movimiento negativo grande para lo habitual
en esta acción"). Toda la aritmética se queda en el código.

El texto se limpia antes de enviarlo:
- Se quitan las tablas financieras y el texto legal (forward-looking statements, non-GAAP,
  contactos, "About X", glosarios).
- La narrativa termina en el primer estado financiero ("Consolidated Statements of…") o en el
  `###` de fin de comunicado: lo que sigue son tablas, sus títulos y notas, y conciliaciones.
- Se quita el mobiliario de página (cabeceras repetidas, "Page N", "(Unaudited)", unidades).
- Se conservan las frases con cifras.
- Se recorta a unos 24k caracteres (≈7k tokens). El límite de Perplexity Decider es de 262k
  tokens por petición, muy por encima; el recorte se eligió para dar al modelo solo la narrativa.

## Enfoques comparados

- **A:** el modelo ve el texto y la reacción y emite el veredicto directamente (`react_anon__nvr`).
- **B:** el modelo solo lee el texto. El código calcula la parte del tono que la reacción no explica
  (`text_anon__mismatch`).
- **Sin modelo:** lo mismo con el diccionario LM (`base__lm_mismatch`), además de la continuación
  pura (PEAD), la reversión y el momentum.

## Estadística

Los eventos se amontonan en las mismas semanas (temporada de resultados), así que la unidad de
independencia es la **semana de entrada**. Se calculan:

- La media de los IC de Spearman semanales (Fama-MacBeth) con errores Newey-West y distribución t.
- El IC agregado con intervalo bootstrap por bloques de semana.
- Un placebo que permuta la señal dentro de cada semana.
- Quintiles con cortes fijados en el split de diseño.
- Una regresión incremental con errores agrupados por semana.
- La corrección de Holm para las hipótesis secundarias.

Todo está detallado en `docs/PREREGISTRATION.md`.

## Contaminación por entrenamiento

Perplexity Decider v1 27B es un ajuste fino de Qwen3.8-27B publicado el 2026-10-01 (ficha del
modelo en Hugging Face); la fecha de corte de sus datos no está publicada.
Como salió después de todo el periodo de holdout, pudo ver esos eventos al entrenarse. Hay tres
defensas:
1. El holdout más reciente posible. Los eventos posteriores a la fecha de lanzamiento del
   modelo (`DECIDER_RELEASE_DATE`) se reportan aparte.
2. La anonimización del nombre, el ticker, las fechas y los años. La variante principal es la
   anonimizada.
3. La sonda sin texto. Si predice retornos, el modelo recuerda.

## Coste y control de gasto

- **Precio:** $0.04 por millón de tokens de entrada; la salida no se cobra (docs de Perplexity,
  2026-10).
- **Escala completa:** ~11k eventos × 5 variantes × ~7k tokens ≈ 300–400M tokens ≈ **$12–16**,
  más una submuestra contrafactual.
- **Controles:**
  - `decisionsignal estimate` da el coste antes de gastar nada.
  - `DECIDER_MAX_USD` es un tope duro: el cliente rechaza el lote si la estimación lo supera y se
    detiene si el gasto real lo cruza.
  - Toda respuesta se guarda en `data/cache/decision_cache.sqlite` y nunca se paga dos veces.
- **Versión del modelo:** fijada en el código en `pplx-decider-v1-27b`, el único modelo que
  sirve la Decisions API (no hay alias móvil ni otro proveedor configurable), para que no cambie
  a mitad del estudio.

## Limitaciones conocidas

- **Supervivencia:** el mapeo ticker→CIK solo conoce tickers actuales y Yahoo pierde muchos
  deslistados. Las empresas adquiridas o quebradas tienden a faltar. Se mide en
  `results/coverage_*.json`.
- **Precios:** yfinance no es oficial y su histórico ajustado puede revisarse. Para un producto
  habría que pasar a una fuente con licencia.
- **Hora del 8-K, no del newswire:** la reacción puede empezar antes de la hora de EDGAR. Por
  diseño solo se opera después del día 0 completo, así que esto no introduce look-ahead.
- **Sin consenso de analistas:** no hay "sorpresa" frente a estimaciones (los datos son de pago).
  El modelo y los baselines solo ven el texto y la reacción.
- **Anonimización parcial:** no oculta productos ni nombres de directivos, y sustituye el
  nombre de la empresa también dentro de nombres de producto ("the Company Watch").
- **Comunicados convertidos desde PDF:** algunos (p. ej. las cartas a accionistas de Airbnb)
  llegan con las líneas partidas y sin títulos reconocibles. La limpieza por secciones no
  actúa y el texto se corta en el límite de 24k caracteres, que suele caer antes de la parte
  legal pero no siempre.
- **Sector por SIC:** es una aproximación gruesa a GICS.
- **Licencia LM:** el diccionario Loughran-McDonald es gratuito para investigación, pero su uso
  comercial requiere licencia.
- **Potencia:** solo se detectan IC de ≈ 0.06 o más (ver el pre-registro).
- **Variabilidad del modelo:** las respuestas del modelo pueden variar algo entre llamadas idénticas.
  La caché fija la respuesta usada, pero no mide esa variabilidad.
