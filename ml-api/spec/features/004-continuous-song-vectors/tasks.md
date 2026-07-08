# Tasks — 004

- [x] Implementar `extraer_vector_track()` — quedó en `ml-api/app/vectorize.py`
      (no se tocó `analyzer.py` de la raíz; se reimplementó la misma lógica
      de `extraer_curvas_completas` en un módulo aparte para no modificar
      código ya en producción del reproductor).
- [ ] ~~Agregar columna `vector_track_json` a `init_db()`~~ — no implementado
      todavía: por ahora se calcula bajo demanda en cada request de
      `platform=pc`, no se persiste en `music_library.db`. Pendiente si se
      quiere evitar recalcularlo en cada análisis de una misma canción.
- [x] Integrar como paso adicional — se llama desde `router.py` sólo cuando
      `platform=pc` (no en `app`, tal como pide el spec).
- [x] Extender `schemas.py` con `VectorBin` y el campo `vector_track` en
      `AnalysisResponsePC` (no en `AnalysisResponseApp`) — confirmado con
      curl: `pc` devuelve `vector_track` con 84 bins, `app` no lo incluye.
- [x] Test de consistencia: bin en t=93-96s (rms=0.245) vs cue_point en
      t=93.5 (energia=0.755, nivel_8) — mismo orden relativo que el bin de
      intro (rms=0.073, cue_point energia=0.252) — consistente.
- [x] Medir tiempo: ~3.9s para una canción de 253s (84 bins de 3s, con chroma).

## Riesgo pendiente (documentado, no bloqueante)

Como no se persiste el vector_track, generar un mixup-plan (006) recalcula la
vectorización de ambas canciones en cada llamada (~4s cada una). Aceptable
para una demo; en un uso real conviene cachear en `music_library.db` como
decía el plan original.
