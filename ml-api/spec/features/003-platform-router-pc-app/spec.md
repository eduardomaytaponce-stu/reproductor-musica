# 003 — Router multimodelo: respuesta PC vs App

## Qué hace

Añade un parámetro `platform: Literal["pc", "app"]` a `POST /analyze` (query
param o header `X-Client-Platform`, a definir en plan). El endpoint sigue
extrayendo features **una sola vez**; lo único que cambia es qué schema de
Pydantic se usa para serializar la salida:

- **`platform=pc`** → `AnalysisResponsePC` (= `AnalysisResponse` de 002 sin
  cambios): todo — `bpm`, `cue_points` completos, `intro_beats`/`outro_beats`,
  `macro_sections`, `mood_prediction` con probabilidades. Pensado para que
  `scan_library.py`/`export_library.py` puedan eventualmente llamar a este
  endpoint en vez de invocar `analyzer.py` in-process, sin perder ningún
  campo de los que hoy escriben a `library.json`.

- **`platform=app`** → `AnalysisResponseApp` (compacto): `bpm`, `mood`
  (sin probabilidades — la app no las usa), `macro_sections` (sí, la app
  las lee para el display de "Suave/Moderado/Energético" en `MacroSection.kt`),
  **sin** `cue_points` completos ni `intro_beats`/`outro_beats` (la app no
  hace beatmatching en vivo desde un análisis remoto, y son los campos que
  más pesan). Los nombres de campo son literalmente los de `Song.kt`
  (`bpm`, `mood`, `macroSections`) para poder mapear la respuesta directo a
  una fila de Room sin traducir nombres en Kotlin.

## Por qué un solo endpoint y no dos

Si `/analyze/pc` y `/analyze/app` fueran rutas separadas con su propia
llamada a DSP, un cambio en `analyzer.py` (ej. el ajuste de
`HALF_ONSET_THRESHOLD` que ya pasó una vez en este proyecto) se podría
aplicar a una ruta y olvidar en la otra, y el PC y el teléfono verían BPM
distinto para la misma canción — exactamente el tipo de bug de fondo que la
misión de este proyecto busca evitar. Un solo endpoint con un router de
salida hace estructuralmente imposible esa divergencia.

## Criterios de aceptación

- [ ] `platform` ausente o con valor fuera de `{"pc","app"}` responde `422`
      listando los valores aceptados (validación Pydantic/FastAPI, no un
      `if/else` con `raise HTTPException` manual).
- [ ] Para la misma canción de entrada, `bpm` y `mood` son **idénticos**
      entre la respuesta `pc` y la respuesta `app` (misma extracción
      subyacente — sólo cambia qué se serializa).
- [ ] La respuesta `app` no incluye las claves `cue_points`,
      `intro_beats`, `outro_beats` en absoluto (no vacías — ausentes del
      JSON), para no pagar payload de más en el teléfono.
- [ ] La respuesta `app` usa exactamente los nombres de campo de `Song.kt`
      (`bpm`, `mood`, `macroSections`), documentado con un ejemplo lado a
      lado con la respuesta `pc` en este spec tras implementarlo.

## Fuera de alcance

- Cambiar `Song.kt` o el import real de la app — este spec sólo define el
  contrato HTTP; el consumo desde Kotlin es trabajo futuro, no listado en el
  roadmap actual.
- Negociación de contenido vía `Accept` header — se usa un parámetro
  explícito (`platform`) por simplicidad y porque es lo que pide la clase
  (input validado explícito, no inferencia de headers).
