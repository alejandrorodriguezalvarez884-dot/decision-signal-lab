# Pre-registro

**Estado: BORRADOR.** Se congela con `uv run jevsignal lock` cuando las preguntas estén cerradas
sobre el split de diseño. A partir de ese momento, el hash de este archivo, de `questions.py`,
de `features.py` y de `config.py` queda guardado en `PREREGISTRATION.lock.json`. El pipeline se
niega a tocar el holdout si alguno cambia.

## Pregunta de investigación

Hablamos de comunicados de resultados trimestrales (8-K Item 2.02, EX-99) de empresas del
S&P 500 en el momento del evento. Una vez conocida la reacción del precio en la primera sesión
(día 0), ¿sabe Jev decir si la noticia es mejor o peor de lo que esa reacción descuenta?
Si lo sabe, su juicio debería predecir el retorno anormal posterior.

## Modelo

El modelo evaluado es **Perplexity Decider v1 27B** (`pplx-decider-v1-27b`, Decisions API de
Perplexity), fijado en `src/jevsignal/config.py`. En el resto de este documento "Jev" designa a
ese modelo: el borrador se escribió para Jev (TypeSafe System One, `jev-1.13.0`) y el 2026-10-04,
antes de cualquier llamada real y antes del sello, se cambió de modelo porque no fue posible
contratar la API de TypeSafe. Preguntas, señales y reglas no cambian. Todas las respuestas del
estudio, en diseño y en holdout, deben venir de este mismo modelo.

## Hipótesis principal (H1)

- **Señal:** `react_anon__nvr` = P(`better`) − P(`worse`) de la pregunta `news_vs_reaction`.
  Jev ve el texto **anonimizado** y una frase que describe la reacción del día 0.
- **Objetivo:** `fwd_abn_20` = retorno de la acción desde la apertura de la sesión siguiente al
  día 0 hasta el cierre de la sesión 20, menos el retorno de SPY en esa misma ventana.
- **Muestra confirmatoria:** eventos aceptados por EDGAR desde 2025-01-01 (holdout). Solo cuentan
  los que Jev clasifica como comunicado de resultados (`is_earnings_release` ≥ 0.5) y que tienen
  precios para la reacción y para la ventana de 20 sesiones.
- **Test:** IC de Spearman semanal (semana de entrada) entre señal y objetivo, solo en semanas
  con ≥ 5 eventos. Se toma la media de los IC semanales y su t de Newey-West con 4 lags y
  distribución t, contraste bilateral con α = 0.05.
- **Criterio de "hay señal":** se exigen las dos condiciones:
  1. IC medio > 0 con p < 0.05.
  2. En la regresión incremental (objetivo winsorizado al 1/99 %, errores agrupados por
     semana), el coeficiente de la señal es > 0 con p < 0.05. Los controles son `r0_z`,
     `momentum`, `log_dollar_vol`, `base__lm_tone` y `text_anon__composite`.

  Si falla cualquiera de las dos, la conclusión es **"sin evidencia de señal incremental"**.
- **Robustez** (se reporta, no decide): placebo por permutación dentro de cada semana,
  diferencial Q5−Q1 con intervalo bootstrap por bloques de semana (cortes de quintil del split
  de diseño), los demás horizontes (1, 5, 60) y el benchmark sectorial.

## Hipótesis secundarias (corrección de Holm)

`react_anon__reversal_signal`, `react_anon__underappreciated_longterm`, `text_anon__mismatch`
(enfoque B: el texto frente a la reacción, sin que Jev vea la reacción), `text_anon__naive_mismatch`
y `text_anon__composite`.

## Reglas de interpretación fijadas de antemano

- **Contaminación:**
  - Si la sonda de memoria (`probe__*`, sin texto) tiene IC > 0 con p < 0.05 en algún split,
    Jev recuerda resultados. Todo lo basado en texto sin anonimizar se descarta y solo cuentan
    las variantes `*_anon` en el holdout.
  - Si `react_raw` supera claramente a `react_anon` en el split de diseño pero no en el holdout,
    eso también es memorización.
- **¿Usa Jev la reacción?** Se mide con contrafactuales: el mismo texto con tres reacciones
  inventadas. Si el veredicto apenas cambia en más del 50 % de los casos, o se mueve en la
  dirección esperada en menos del 50 %, Jev no está integrando la reacción. En ese caso el
  enfoque A no aporta sobre el B.
- **Comparación con baselines:** el valor de Jev se juzga contra la continuación (PEAD), la
  reversión y el diccionario Loughran-McDonald. Un IC positivo no basta si una regla trivial
  hace lo mismo.

## Potencia (honestidad sobre lo detectable)

Con unos 3.000–3.500 eventos en el holdout para h = 20 y la correlación entre eventos de la misma
semana, el error estándar del IC ronda 0.02–0.03. Con una potencia del 80 %, solo se detectan IC
de ≈ 0.06–0.08 o más. Las señales de texto publicadas sobre la deriva post-resultados suelen estar
en IC ≈ 0.02–0.05, así que **un resultado nulo no descarta un efecto pequeño**. Se informará así.

## Desviaciones

Se registran aquí, con fecha, los cambios hechos después del lock y su motivo.

- (ninguna)
