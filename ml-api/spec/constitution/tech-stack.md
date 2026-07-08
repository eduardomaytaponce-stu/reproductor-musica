# Tech stack y convenciones

## Stack

- **FastAPI** + **Pydantic v2** — validación de entrada/salida, nunca `dict` crudo
  en una respuesta pública.
- **uvicorn** — server ASGI.
- **scikit-learn** — `Pipeline(StandardScaler, GradientBoostingClassifier)` (o
  `LogisticRegression` como baseline) para el clasificador de mood.
- **joblib** — serialización del pipeline entrenado a
  `ml-api/app/models/mood_classifier.joblib`.
- **librosa / soundfile / numpy** — reutilizados de `analyzer.py` (raíz del
  repo), refactorizados a funciones puras (sin `sqlite3`, sin `argparse`, sin
  side effects de CLI) para poder importarlos desde `model.py`.

## Estructura de código (`ml-api/app/`)

```
app/
├── main.py      ← punto de entrada, FastAPI(), lifespan (carga modelos 1 vez)
├── schemas.py   ← Pydantic: AnalysisRequest, AnalysisResponsePC,
│                  AnalysisResponseApp, MoodPrediction, HealthResponse
├── model.py     ← singletons: DSPAnalyzer (wrapper de analyzer.py) y
│                  MoodClassifier (carga el .joblib)
├── router.py    ← POST /analyze, POST /predict/mood, GET /health
└── models/
    └── mood_classifier.joblib
```

## Convenciones no negociables

1. **Modelo en memoria, no por-request.** Tanto el DSP (import de las
   funciones de `analyzer.py`) como el `.joblib` del clasificador se cargan
   una única vez en el `lifespan` de FastAPI. Ningún endpoint vuelve a leer
   disco o reimportar en cada request.
2. **Un endpoint, extracción única, router decide el shape.** `POST /analyze`
   corre la extracción de features una sola vez; el parámetro `platform`
   (`"pc" | "app"`) sólo cambia qué campos se serializan en la respuesta, no
   vuelve a analizar el audio.
3. **Toda respuesta es un modelo Pydantic explícito**, con los mismos nombres
   de campo que ya usan `library.json` (PC) y `Song.kt` (app) — sin inventar
   nombres nuevos que obliguen a traducir en el cliente.
4. **`/health` no es un placeholder.** Debe confirmar que el `.joblib` cargó y
   que las funciones DSP están disponibles, devolviendo `false` por componente
   si algo falló al iniciar (no sólo `{"status": "ok"}` fijo).
5. **El clasificador se entrena offline**, fuera del proceso de la API
   (feature 001). La API sólo carga el artefacto ya entrenado — nunca entrena
   en el request path.
6. **No reimplementar lo que ya existe en la raíz del repo.** `analyzer.py`
   (curvas, segmentación, `transition_points`) y `transition.py`
   (`calcular_transicion_optima`, `ordenar_cola_por_tempo`) se importan tal
   cual desde `ml-api/`. Las features 004-006 son capas nuevas encima, no
   reescrituras — si una función ya existe en la raíz, se importa, no se
   copia.
7. **004-006 son DSP/heurísticas, no ML entrenado.** No requieren dataset
   etiquetado y por eso generalizan a audio nunca antes visto sin
   reentrenar. Sólo 001 (mood) es un modelo aprendido de datos; documentar
   esta distinción explícitamente en cualquier respuesta de la API que
   combine ambos, para no hacerle creer al consumidor que todo es "predicho"
   por un modelo entrenado.
