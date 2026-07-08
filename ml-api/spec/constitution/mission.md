# Misión

## Qué construimos

Un servicio HTTP (`ml-api/`) que expone como endpoint el análisis de audio que hoy
sólo existe como script batch de PC (`analyzer.py`), y le añade una capa de
Machine Learning real (con coeficientes entrenados) que hoy no existe en el
proyecto.

Hoy `analyzer.py` es un pipeline **DSP/heurístico** (librosa: onset strength,
tempo, spectral centroid + umbrales fijos como `BPM_MIN`, `HALF_ONSET_THRESHOLD`).
No tiene nada "aprendido de datos" — es determinístico. Este servicio:

1. Reutiliza ese DSP tal cual (extracción de `bpm`, `cue_points`, `macro_sections`,
   `intro_beats`/`outro_beats`) — es el "modelo en memoria" en sentido amplio.
2. Añade un **clasificador de mood entrenado** (scikit-learn, con coeficientes
   reales) sobre las ~160 canciones ya etiquetadas en `export/library.json`
   (campo `mood`: relax/enfoque/energia/accion). Esto es lo que cumple
   literalmente el patrón "modelo de ML con coeficientes" pedido en clase.
3. Expone ambos resultados combinados detrás de un **router multimodelo** que
   decide qué forma de respuesta devolver según quién pregunta.

## Para quién

- **Cliente PC** (`scan_library.py` / `export_library.py`): hoy corren
  `analyzer.py` in-process. La meta es que puedan (opcionalmente) llamar a este
  endpoint y recibir el análisis **completo** — todos los campos que ya se
  guardan en `library.json` hoy, más la predicción de mood.
- **Cliente App Android** (`Song.kt` / Room): la app **no** corre librosa ni
  ningún análisis on-device hoy — sólo consume campos precalculados. La meta es
  que, cuando el usuario importe una canción nueva desde el teléfono, la app
  pueda pedir un análisis **ligero** (bpm + mood + macro_sections resumidas) ya
  con la forma exacta de los campos de `Song.kt`, sin la rejilla de beats
  completa (no la necesita, y pesa más).

## Por qué el router multimodelo

La app y el PC ya consumen formas distintas de los mismos datos (ver
`Song.kt` vs `library.json`). En vez de dos endpoints separados que dupliquen
la extracción de features, un solo endpoint hace la extracción una vez y el
router decide el *shape* de salida según `platform`. Esto evita divergencia
entre lo que ve el PC y lo que ve la app — el bug de fondo que se quiere evitar
es que ambos lean el mismo audio y obtengan valores distintos.

## Ampliación: vectorización continua + mixup entre canciones (2026-07-06)

Corrección importante sobre el estado real del proyecto (ver
[[ml-api-sdd-project]]): `analyzer.py` **ya** calcula vectores finos (`rms`,
`chroma` 12-dim, `spectral_centroid`, `beats`) en 8 puntos "óptimos" por
canción (`analyze_segment` + `transition_points`), y `transition.py` **ya**
tiene un motor de decisión DJ (`calcular_transicion_optima`) que, dado un par
de segmentos ya elegidos, decide tipo de transición/duración/beatmatching.
Todo esto vive sólo en `music_library.db` (PC) — `export_library.py` lo
descarta al exportar a `library.json`, dejando sólo los metadatos derivados
(`cue_points`), nunca los vectores.

Esta ampliación no reinventa nada de lo anterior; construye tres piezas que
faltan:

1. **Vectorización continua** (004): hoy los vectores sólo existen en 8
   puntos preseleccionados por estructura/valle de energía — no se puede
   evaluar un timestamp arbitrario. Se necesita una serie continua de
   vectores (mínimo cada 3s) para toda la canción, no sólo 8 muestras.
2. **Scoring de "buen punto de entrada/salida"** (005): ningún código actual
   implementa el criterio narrativo tipo TikTok/Instagram — subir hacia un
   pico, no cortar justo en el pico, bajar hasta un nivel parecido (no
   idéntico) al de inicio. `find_optimal_transition_timestamps` optimiza otra
   cosa (límites de sección + valles), no esta forma de arco.
3. **Emparejamiento entre dos canciones distintas** (006): `transition.py`
   evalúa un par de segmentos ya elegido; nada hoy busca, entre TODOS los
   puntos candidatos de la canción A y TODOS los de la canción B, el mejor
   par para armar una edición/historia con ambas como soundtrack (agrupando
   por BPM/sentimiento, igual que ya se agrupa por BPM en
   `ordenar_cola_por_tempo`).

**Por qué esto generaliza a canciones nuevas sin reentrenar nada**: 004/005
son DSP y heurísticas puras (no hay modelo ajustado a canciones específicas),
así que corren igual sobre audio nunca antes visto — el input es la curva del
audio, no un identificador de canción conocida. El límite real no es
"canciones nuevas vs conocidas", es que 005 arranca como heurística (no hay
dataset etiquetado de "esto es un buen hook") — coherente con la expectativa
del usuario de "no es perfecto, funciona para el 80% de las canciones más
populares". Si más adelante se quiere una versión aprendida, hace falta
primero recolectar labels (ver "Fuera de alcance" en 005).
