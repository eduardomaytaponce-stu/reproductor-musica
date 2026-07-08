# Plan — 001

1. `load_dataset(path="export/library.json") -> pd.DataFrame`
   - Parsear `songs[]`, calcular `arousal_mean`/`energia_mean`/`energia_max`
     por canción con pandas/numpy sobre las listas ya presentes
     (`macro_sections`, `cue_points`).
   - Columnas finales: `bpm, duration, arousal_mean, energia_mean,
     energia_max, mood`.

2. `build_pipeline() -> sklearn.pipeline.Pipeline`
   - `StandardScaler()` + `GradientBoostingClassifier(random_state=42)`.

3. `train_and_evaluate(df)`
   - `train_test_split(..., stratify=df["mood"], test_size=0.2,
     random_state=42)`.
   - `.fit()` sobre train, `.predict()` sobre test.
   - `classification_report` + comparación contra `DummyClassifier
     (strategy="most_frequent")` como baseline.

4. `joblib.dump(pipeline, "ml-api/app/models/mood_classifier.joblib")`.

5. Guardar también la lista de nombres de features usada (mismo orden que en
   `model.py` de la feature 002) para evitar desalineación silenciosa entre
   entrenamiento y servido.

## Riesgo conocido

160 filas / 4 clases es un dataset pequeño — el split de test puede quedar con
~8 ejemplos por clase. Es aceptable para esta feature (el objetivo es tener el
pipeline funcionando end-to-end, no un modelo de producción), pero el `spec.md`
deja explícito que no se exige un umbral de accuracy.
