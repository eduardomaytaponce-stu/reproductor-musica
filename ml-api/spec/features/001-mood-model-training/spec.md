# 001 — Entrenamiento del clasificador de mood

## Qué hace

Script offline (`train.py`, fuera del proceso de la API) que:

1. Lee `export/library.json` (160 canciones, campo `mood` con valores
   `relax` / `enfoque` / `energia` / `accion`).
2. Construye un dataset tabular por canción con features derivadas de lo que
   ya se calcula hoy (sin volver a tocar audio):
   - `bpm`
   - `duration`
   - `arousal_mean` — promedio de `arousal` en `macro_sections`
   - `energia_mean` — promedio de `energia` en `cue_points`
   - `energia_max` — máximo de `energia` en `cue_points`
3. Entrena `Pipeline(StandardScaler, GradientBoostingClassifier)` (baseline:
   `LogisticRegression`) con split train/test estratificado por `mood`.
4. Serializa el pipeline entrenado a
   `ml-api/app/models/mood_classifier.joblib`.
5. Imprime/guarda métricas (accuracy, F1 macro) comparadas contra un baseline
   de clase mayoritaria.

## Por qué estas features y no el audio crudo

El endpoint de análisis (002) ya extrae estos valores vía DSP en cada
request. Entrenar sobre ellos (en vez de sobre el audio crudo o embeddings)
mantiene el modelo barato de servir y coherente con lo que la app y el PC ya
consumen — el clasificador predice sobre lo que el sistema ya sabe calcular,
no introduce una fuente de verdad paralela.

## Criterios de aceptación

- [ ] El dataset se construye únicamente desde `export/library.json`, sin
      leer archivos de audio.
- [ ] Split train/test estratificado por `mood` (no aleatorio simple — hay
      sólo 160 filas y 4 clases, un split naive puede dejar una clase fuera
      del test).
- [ ] El accuracy/F1 del modelo entrenado se reporta junto al baseline de
      clase mayoritaria en la salida del script (no hace falta superar un
      umbral fijo — el objetivo de esta feature es tener el artefacto y la
      medición, no una garantía de calidad).
- [ ] El artefacto queda en `ml-api/app/models/mood_classifier.joblib` y es
      cargable con `joblib.load(...)` sin dependencias además de scikit-learn.
- [ ] Reentrenable con un solo comando (`python train.py`), determinístico
      (semilla fija).

## Fuera de alcance

- Tuning de hiperparámetros más allá de defaults razonables.
- Aumentar el dataset (data augmentation, más canciones) — se usa lo que ya
  existe en `library.json`.
