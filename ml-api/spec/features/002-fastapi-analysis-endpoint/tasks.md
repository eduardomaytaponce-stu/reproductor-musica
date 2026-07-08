# Tasks — 002

- [x] Extraer `arousal_mean`/`energia_mean`/`energia_max` a
      `ml-api/app/features.py`, usada tanto por `train.py` (001) como por
      `router.py` (002) — evita divergencia train/serve.
- [x] Refactorizar (o envolver) `analyzer.py` para exponer una función pura
      `analizar(filepath) -> dict` sin `sqlite3`/`argparse`/prints de CLI.
      → `ml-api/app/dsp.py::run_dsp_analysis` (envuelve `analyzer.analyze_song`,
      que ya era puro — no hizo falta tocar `analyzer.py`).
- [x] Escribir `schemas.py` con los modelos del plan.
- [x] Escribir `model.py` (`MoodClassifier`, `run_dsp_analysis`).
- [x] Escribir `router.py` (`/analyze`, `/predict/mood`, `/health`).
- [x] Escribir `main.py` con `lifespan`.
- [x] Probar `/health` antes de que termine de cargar vs después — refleja
      `dsp_loaded`/`mood_model_loaded` reales, confirmado con `{"status":"ok",
      "dsp_loaded":true,"mood_model_loaded":true}`.
- [x] Probar `/analyze` con un `.flac` real (Arctic Monkeys - 505) — bpm=70.75,
      8 cue_points, macro_sections, mood_prediction=energia (91.4% confianza).
      Tiempo de análisis: ~5s.
- [x] Probar `/predict/mood` con un campo faltante → confirmado `422` con el
      detalle de los 3 campos faltantes.

## Evidencia real de errores (2026-07-06)

- Archivo de audio corrupto → `422 {"detail":"No se pudo analizar el audio: ..."}`
  (no 500).
- `platform` inválido/ausente → `422` listando `'pc' or 'app'`.
