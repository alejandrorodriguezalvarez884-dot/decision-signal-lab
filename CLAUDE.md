# Instrucciones para agentes

Lee primero [docs/HANDOFF.md](docs/HANDOFF.md): contiene el encargo, el estado, lo pendiente y
los siguientes pasos.

Reglas que no se negocian:
- **Nada de trading.** No se escribe código que envíe órdenes ni que se conecte a un broker, y
  no se usa ningún conector de broker (IBKR u otro), ni siquiera para descargar precios.
- **Cero look-ahead.** Cualquier cambio en `events.py` se acompaña de su test en
  `tests/test_events.py`.
- **Antes de gastar en la API de Perplexity o de descargar volúmenes grandes,**
  se pide permiso al usuario con una estimación (`uv run jevsignal estimate …`).
- **El holdout (eventos desde 2025-01-01) está sellado** hasta `jevsignal lock`. No se ajustan
  preguntas mirando el holdout.
- **Claves solo en `.env` o en el entorno.** Nunca en el repo, en logs ni en commits.
- **Los resultados nulos se reportan tal cual.**

Convenciones:
- Hablar con el usuario en español. Código y comentarios en inglés.
- Python 3.12 con `uv`. Los tests se lanzan con `uv run pytest`.
- Las preguntas a Jev viven solo en `src/jevsignal/questions.py` y las constantes del estudio en
  `src/jevsignal/config.py`.
- Al terminar una tarea relevante, actualizar el apartado "Dónde estamos" de `docs/HANDOFF.md`.
