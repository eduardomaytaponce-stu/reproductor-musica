# Tasks — 003

- [x] Añadir `AnalysisResponsePC`/`AnalysisResponseApp`/`Platform` a
      `schemas.py`.
- [x] Modificar `/analyze` para aceptar `platform` y ramificar la
      serialización (no la extracción).
- [x] Test: misma canción, `platform=pc` y `platform=app` → mismo `bpm` y
      `mood` en ambas respuestas (70.75 / "energia" en ambas, confirmado).
- [x] Test: `platform=app` → confirmado que `cue_points`/`intro_beats`/
      `outro_beats` no están presentes en el JSON de respuesta.
- [x] Test: `platform` inválido o ausente → `422`.
- [x] Documentar ejemplo real:

## Ejemplo real (Arctic Monkeys — 505.flac, 2026-07-06)

`platform=pc` (extracto, sin `vector_track` por brevedad):
```json
{"bpm":70.75,"duration":253.59,"cue_points":[...8 puntos...],
 "macro_sections":[{"t_start":0.0,"t_end":147.0,"bpm":143.6,"arousal":0.174},
                    {"t_start":147.0,"t_end":252.0,"bpm":139.8,"arousal":0.518}],
 "intro_beats":[...],"outro_beats":[...],
 "mood_prediction":{"mood":"energia","probabilidades":{"accion":0.005,"energia":0.914,"enfoque":0.0754,"relax":0.0056}}}
```

`platform=app`:
```json
{"bpm":70.75,"mood":"energia",
 "macroSections":[{"t_start":0.0,"t_end":147.0,"bpm":143.6,"arousal":0.174},
                   {"t_start":147.0,"t_end":252.0,"bpm":139.8,"arousal":0.518}]}
```
