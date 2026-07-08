# 002 — Endpoint FastAPI base (DSP + ML combinado)

## Qué hace

Expone vía HTTP el análisis que hoy sólo corre como script de PC, combinado
con la predicción de mood de la feature 001. Todavía sin diferenciar
plataforma (eso es 003) — una sola forma de respuesta, la completa.

- `POST /analyze` — recibe un archivo de audio (o una ruta local, ver Plan),
  corre el DSP de `analyzer.py` (bpm, cue_points, macro_sections,
  intro_beats, outro_beats) y el clasificador de mood de 001 sobre las
  features derivadas de ese mismo análisis. Devuelve todo combinado.
- `POST /predict/mood` — endpoint puramente ML: recibe las features
  numéricas directamente (`bpm`, `duration`, `arousal_mean`, `energia_mean`,
  `energia_max`) sin tocar audio, devuelve `{mood, probabilidades}`. Este es
  el que calza 1:1 con el patrón "modelo en memoria + predict" visto en
  clase.
- `GET /health` — confirma que el `.joblib` de mood cargó y que las
  funciones DSP están importables.

## Por qué dos endpoints de predicción

`/analyze` hace todo el trabajo pesado (DSP sobre audio real). `/predict/mood`
existe aparte porque es la forma más directa de demostrar el patrón exacto de
la tarea (input validado → modelo en memoria → predicción estructurada) sin
la complejidad del audio — útil para testear el modelo de 001 de forma
aislada y para clientes que ya tienen las features (ej. el propio `/analyze`
podría llamarlo internamente).

## Criterios de aceptación

- [ ] Los modelos (DSP importado + `.joblib`) se cargan una sola vez en el
      `lifespan` de FastAPI — no en cada request (verificar con un log de
      "modelo cargado" que sólo aparece una vez al boot).
- [ ] `POST /analyze` con un archivo no soportado (ej. `.txt` renombrado a
      `.flac`) responde `422` con detalle del error, no `500`.
- [ ] `POST /predict/mood` con un campo faltante (ej. sin `bpm`) responde
      `422` con el nombre del campo faltante (validación Pydantic, no
      try/except manual).
- [ ] `GET /health` responde `200` con
      `{"dsp_loaded": bool, "mood_model_loaded": bool, "status": "ok"|"degraded"}`
      — `degraded` si algún componente falló al iniciar, no un `"ok"` fijo.
- [ ] La respuesta de `/analyze` es un modelo Pydantic (`AnalysisResponse`)
      con los mismos nombres de campo que ya usa `library.json`
      (`bpm`, `cue_points`, `macro_sections`, `intro_beats`, `outro_beats`)
      más `mood_prediction: MoodPrediction`.

## Fuera de alcance

- Diferenciar respuesta por plataforma (PC vs app) — eso es 003.
- Autenticación/rate limiting — no forma parte del patrón de clase.
- Persistencia de resultados (esto es una lectura, no escribe en
  `music_library.db` ni en `library.json`).
