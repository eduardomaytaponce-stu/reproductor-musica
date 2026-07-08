# ml-api — Análisis musical + clasificador de mood (FastAPI)

API REST que despliega un modelo de Machine Learning como un endpoint HTTP.
Combina dos cosas:

1. **Un modelo de ML entrenado** (scikit-learn: `StandardScaler` +
   `GradientBoostingClassifier`) que predice el *mood* de una canción
   (`relax` / `enfoque` / `energia` / `accion`).
2. **Un pipeline de DSP** (análisis de señal con librosa) que extrae BPM,
   puntos de energía, secciones y una vectorización de la canción.

Ambos se exponen detrás de un **router multiplataforma**: el mismo endpoint
devuelve una respuesta completa para PC o una ligera para la app móvil.

---

## ¿Qué es "la API" y cómo funciona? (para entender antes de correrla)

Una **API REST** es un programa que se queda escuchando pedidos por HTTP.
Tú (o `curl`, o el script `probar_api.py`, o el navegador) le mandas un
**request** y te devuelve un **response** en formato JSON.

```
   TÚ (curl / navegador / script)                    LA API (este proyecto)
   ─────────────────────────────                     ──────────────────────
   POST /analyze?platform=pc      ───── HTTP ─────▶   1. recibe el audio
   (con un archivo .flac)                             2. corre DSP + modelo ML
                                  ◀──── JSON ─────    3. devuelve el resultado
```

El "modelo en memoria" se carga **una sola vez** cuando la API arranca (no en
cada pedido), y a partir de ahí responde rápido.

---

## Instalación

Necesitas Python 3.11+ (probado en 3.14). Desde la carpeta `ml-api/`:

```bash
# 1. Crear e instalar el entorno
python -m venv .venv
source .venv/bin/activate          # en Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Entrenar el modelo de mood (genera app/models/mood_classifier.joblib)
#    Sólo hace falta la primera vez. Lee ../export/library.json.
python train.py
```

> El repositorio ya incluye un `app/models/mood_classifier.joblib` entrenado,
> así que el paso 2 es opcional si sólo quieres probar la API.

---

## Correr la API localmente (prender y apagar)

```bash
# desde la carpeta ml-api/, con el entorno activado:
uvicorn app.main:app --port 8123
```

Verás algo como `Uvicorn running on http://127.0.0.1:8123`. Déjala corriendo
en esa terminal.

**Para apagarla:** en esa misma terminal pulsa `Ctrl + C`.

### ¿Cómo funciona en la RAM? (importante)

La API es un **proceso servidor**: mientras esté corriendo ocupa RAM de forma
continua (el modelo se carga **una sola vez** al arrancar, gracias al
`lifespan`, y se queda en memoria para responder a todos los pedidos, sean 1 o
1000). **No se libera solo.** Sólo deja de ocupar RAM cuando **tú apagas el
servidor** con `Ctrl + C`.

Un cliente (como `probar_api.py` o `curl`) sólo le manda pedidos: cuando el
cliente termina, el **servidor sigue encendido** y sigue en RAM. Es distinto
de "llamar una función que se activa y se apaga sola". Es igual que una API
externa (la del clima): siempre está encendida en algún servidor — sólo que
aquí el servidor lo enciendes y apagas tú, en tu PC.

### Swagger — la forma más fácil de probar (recomendada para aprender)

Abre en tu navegador:

```
http://127.0.0.1:8123/docs
```

Es una interfaz interactiva (generada sola por FastAPI) donde ves todos los
endpoints, puedes subir un archivo y darle "Execute" sin escribir código.

---

## Ejemplos de request

### Con curl

```bash
# 1) ¿Está viva la API y cargó sus modelos?
curl http://127.0.0.1:8123/health

# 2) Analizar una canción — respuesta COMPLETA (PC):
curl -X POST "http://127.0.0.1:8123/analyze?platform=pc" \
     -F "file=@/ruta/a/tu/cancion.flac"

# 3) La misma canción — respuesta LIGERA (app móvil):
curl -X POST "http://127.0.0.1:8123/analyze?platform=app" \
     -F "file=@/ruta/a/tu/cancion.flac"

# 4) El modelo ML puro, sin audio (le pasas las features a mano):
curl -X POST "http://127.0.0.1:8123/predict" \
     -H "Content-Type: application/json" \
     -d '{"duration":210,"arousal_mean":0.65,"energia_mean":0.55,"energia_max":0.9}'

# 5) Mejores puntos para un clip corto (estilo TikTok):
curl -X POST "http://127.0.0.1:8123/hook-points?top_k=3" \
     -F "file=@/ruta/a/tu/cancion.flac"

# 6) Plan de transición entre DOS canciones:
curl -X POST "http://127.0.0.1:8123/mixup-plan" \
     -F "file_a=@/ruta/cancion_A.flac" \
     -F "file_b=@/ruta/cancion_B.flac"
```

> En `-F "file=@..."` la `@` es lo que le dice a curl "sube el contenido de
> este archivo", no el texto de la ruta.

### Con el script de prueba (Python)

Más legible que curl y muestra los resultados explicados:

```bash
# En OTRA terminal (la API debe estar corriendo):
python probar_api.py "/ruta/a/tu/cancion.flac"

# Con dos canciones, además prueba el mixup:
python probar_api.py "/ruta/cancion_A.flac" "/ruta/cancion_B.flac"
```

---

## Endpoints

| Método | Ruta | Qué hace |
|--------|------|----------|
| `GET`  | `/health` | Estado de la API, confirma que el modelo está cargado y su versión. |
| `POST` | `/predict` | Predice el mood a partir de 4 features numéricas (sin audio). |
| `POST` | `/analyze?platform=pc\|app` | Analiza un audio: BPM, mood, cue points, secciones, (pc) vectorización. |
| `POST` | `/hook-points?top_k=N` | Mejores momentos para iniciar un clip corto. |
| `POST` | `/mixup-plan` | Plan de transición entre dos canciones. |

Documentación interactiva completa: `http://127.0.0.1:8123/docs`

### Respuesta estructurada de `/predict`

```json
{
  "mood": "enfoque",
  "confianza": 0.8061,
  "probabilidades": {"accion": 0.0074, "energia": 0.1851, "enfoque": 0.8061, "relax": 0.0014},
  "tiempo_inferencia_ms": 2.05,
  "modelo_version": "1.0.0"
}
```

Incluye la predicción (`mood`), el **tiempo de inferencia en ms** y metadatos
(`confianza`, `modelo_version`).

### ¿Y si tengo una playlist en vez de 2 canciones?

`/mixup-plan` es estrictamente **entre 2 canciones**: en cada llamada la API
carga **sólo esas 2**, encuentra el punto de nexo y responde. Para una playlist
se procesan **pares consecutivos** (canción 1 → 2, luego 2 → 3, etc.) llamando
al endpoint varias veces desde el cliente — la API en sí nunca carga más de 2
a la vez (así no llena la RAM). Eso es justo lo que hace `probar_api.py` si le
pasas 3 o más archivos:

```bash
python probar_api.py "/ruta/1.flac" "/ruta/2.flac" "/ruta/3.flac"
```

---

## Estructura del código

```
ml-api/
├── app/
│   ├── main.py          ← punto de entrada FastAPI + lifespan (carga modelos 1 vez)
│   ├── router.py        ← definición de los endpoints
│   ├── schemas.py       ← validación de entrada/salida (Pydantic)
│   ├── model.py         ← carga del modelo ML (.joblib) en memoria
│   ├── features.py      ← features compartidas entre entrenamiento y servido
│   ├── dsp.py           ← envuelve el análisis de señal (analyzer.py)
│   ├── vectorize.py     ← vectorización continua de la canción
│   ├── hook_scorer.py   ← heurística de "puntos de enganche"
│   ├── mixup_planner.py ← plan de transición entre 2 canciones
│   └── models/
│       └── mood_classifier.joblib   ← modelo entrenado (lo genera train.py)
├── train.py             ← entrena el modelo de mood (offline)
├── requirements.txt
├── Dockerfile           ← (opcional) para correr en contenedor
├── probar_api.py        ← cliente de prueba
└── spec/                ← especificaciones SDD (Spec-Driven Development)
```

---

## Nota honesta sobre el modelo de mood

El `mood` con el que se entrenó viene de una regla sobre el BPM en el proyecto
original, así que el BPM se **excluye a propósito** de las features del modelo
(si no, tendría ~100% de accuracy "haciendo trampa", re-derivando la fórmula
del label). El modelo aprende de la envolvente de energía. Su F1 macro real
es **0.30 vs 0.136** del baseline (clase mayoritaria): modesto pero genuino,
limitado por tener sólo 160 canciones. El resto de endpoints (BPM, hook-points,
mixup) son DSP + heurísticas, no dependen de este modelo.
