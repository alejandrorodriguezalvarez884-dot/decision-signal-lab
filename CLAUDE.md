# Instrucciones para agentes

Lee primero [docs/HANDOFF.md](docs/HANDOFF.md): contiene el encargo, el estado, lo pendiente y
los siguientes pasos. El producto actual es el radar: [docs/RADAR.md](docs/RADAR.md).

Reglas que no se negocian:
- **Nada de trading.** No se escribe código que envíe órdenes ni que se conecte a un broker, y
  no se usa ningún conector de broker (IBKR u otro), ni siquiera para descargar precios.
- **Cero look-ahead.** Cualquier cambio en `events.py` se acompaña de su test en
  `tests/test_events.py`.
- **Antes de gastar en la API de Perplexity o de descargar volúmenes grandes,**
  se pide permiso al usuario con una estimación (`uv run decisionsignal estimate …`).
- **El estudio de predicción está cerrado como resultado nulo** (2026-10-04). El contraste con
  retornos sobre el holdout (eventos desde 2025-01-01) no se hizo y no se hace: `score` y
  `report --holdout` siguen bloqueados sin `lock`.
- **El radar solo lee texto.** `radar.py` no usa precios, retornos ni la reacción del mercado, y
  la web no publica nada que sea una predicción o una recomendación.
- **Todo en local, nada programado.** No hay GitHub Actions ni tareas periódicas, y no se
  añaden. Los datos y el sitio cambian solo cuando el usuario lanza un comando del `Makefile`
  (`make check`, `make update`, `make deploy`, `make publish`).
- **Claves solo en `.env` o en el entorno.** Nunca en el repo, en logs ni en commits.
- **Los resultados nulos se reportan tal cual.**

Convenciones:
- Hablar con el usuario en español. Código y comentarios en inglés.
- Python 3.12 con `uv`. Los tests se lanzan con `make test` (o `uv run pytest`).
- Las preguntas al modelo viven solo en `src/decisionsignal/questions.py` y las constantes del estudio en
  `src/decisionsignal/config.py`.
- `radar/` (el dataset publicado) y `validation/` están en git. `data/` no.
- Al terminar una tarea relevante, actualizar el apartado "Dónde estamos" de `docs/HANDOFF.md`.
