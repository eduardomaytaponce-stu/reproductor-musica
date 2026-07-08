# Tasks — 001

- [x] Escribir `load_dataset()` y validar manualmente 2-3 filas contra
      `export/library.json` a ojo.
- [x] Escribir `build_pipeline()`.
- [x] Escribir `train_and_evaluate()` con split estratificado + baseline.
- [x] Serializar a `ml-api/app/models/mood_classifier.joblib`.
- [x] ~~Guardar `feature_names.json`~~ — el orden de columnas quedó fijo como
      constante `FEATURE_NAMES` en `ml-api/app/features.py`, compartida por
      `train.py` y `router.py` (evita el riesgo de desalineación train/serve
      sin necesidad de un archivo aparte).
- [x] Correr el script y pegar el `classification_report` en este archivo
      como evidencia de que el pipeline corrió end-to-end.

## Evidencia real (ejecutado 2026-07-06)

```
Dataset: 160 canciones, features=['duration', 'arousal_mean', 'energia_mean', 'energia_max']
Distribución de mood: {'accion': 27, 'energia': 43, 'enfoque': 60, 'relax': 30}

=== Baseline (clase mayoritaria) ===
F1 macro: 0.136

=== GradientBoostingClassifier ===
              precision    recall  f1-score   support
      accion       0.00      0.00      0.00         5
     energia       0.57      0.44      0.50         9
     enfoque       0.47      0.58      0.52        12
       relax       0.20      0.17      0.18         6
    accuracy                           0.38        32
   macro avg       0.31      0.30      0.30        32
weighted avg       0.37      0.38      0.37        32

F1 macro: 0.300  (baseline: 0.136)
```

Nota importante encontrada al implementar: `mood` en `library.json` se genera
hoy con una regla determinística sobre el BPM (`mood_por_bpm` en
`export_library.py`: `>=125 accion, >=115 energia, >=95 enfoque, else relax`).
Por eso el BPM se excluyó a propósito de las features (ver `features.py`) —
incluirlo daría accuracy ~100% por estar re-derivando la misma fórmula del
label, no por haber aprendido nada. El F1 de 0.30 (vs 0.136 del baseline) es
la señal real de cuánto explica la envolvente de energía (sin mirar el BPM)
sobre un mood que en el fondo es una función del BPM — es modesto pero
genuino, y honesto de presentar como tal.
