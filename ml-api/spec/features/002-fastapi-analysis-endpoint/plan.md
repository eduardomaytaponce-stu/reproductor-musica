# Plan — 002

## `schemas.py`

```python
class MoodPrediction(BaseModel):
    mood: Literal["relax", "enfoque", "energia", "accion"]
    probabilidades: dict[str, float]

class CuePoint(BaseModel):
    t: float
    energia: float
    clase: str
    tipo: str

class MacroSection(BaseModel):
    t_start: float
    t_end: float
    bpm: float
    arousal: float

class AnalysisResponse(BaseModel):
    bpm: float
    duration: float
    cue_points: list[CuePoint]
    macro_sections: list[MacroSection]
    intro_beats: list[float]
    outro_beats: list[float]
    mood_prediction: MoodPrediction

class MoodFeatures(BaseModel):
    bpm: float
    duration: float
    arousal_mean: float
    energia_mean: float
    energia_max: float

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    dsp_loaded: bool
    mood_model_loaded: bool
```

## `model.py`

- `class MoodClassifier`: carga `mood_classifier.joblib` una vez en
  `__init__`, expone `.predict(features: MoodFeatures) -> MoodPrediction`
  (usa `predict_proba` para las probabilidades, no sólo la clase).
- `run_dsp_analysis(filepath: str) -> dict`: wrapper delgado sobre las
  funciones de `analyzer.py` (refactorizadas a funciones puras — sin
  `sqlite3`/`argparse` — importadas desde la raíz del repo o copiadas a
  `ml-api/app/dsp.py` si `analyzer.py` no se puede importar limpio por sus
  side-effects de CLI).
- Ambos instanciados como singletons a nivel de módulo, poblados en el
  `lifespan` de `main.py`.

## `router.py`

- `POST /analyze`: recibe `UploadFile`, guarda a un temporal, corre
  `run_dsp_analysis`, deriva `MoodFeatures` del resultado DSP (mismas
  fórmulas de `arousal_mean`/`energia_mean`/`energia_max` que en el
  `train.py` de 001 — **debe reutilizar la misma función**, no reimplementarla,
  para no divergir del entrenamiento), llama a `MoodClassifier.predict`,
  arma `AnalysisResponse`.
- `POST /predict/mood`: recibe `MoodFeatures` directo, llama
  `MoodClassifier.predict`, devuelve `MoodPrediction`.
- `GET /health`: lee flags de los singletons.

## `main.py`

- `FastAPI(lifespan=lifespan)` donde `lifespan` instancia `MoodClassifier` y
  valida el import de DSP, guardándolos en `app.state`.
- Incluye el router de `router.py`.

## Riesgo conocido

Si las fórmulas de `arousal_mean`/`energia_mean` se reimplementan distinto en
`train.py` (001) y en `router.py` (002), el modelo servido verá features con
otra distribución que las de entrenamiento. Mitigación: extraer esas fórmulas
a una función compartida (`features.py`) importada por ambos, no duplicarlas.
