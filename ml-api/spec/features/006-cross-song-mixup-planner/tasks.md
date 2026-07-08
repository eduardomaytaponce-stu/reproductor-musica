# Tasks — 006

- [x] Implementar `arousal_en`, `mixup_planner.generar_plan` (candidatos de
      salida/entrada vienen directo de `mejores_puntos_enganche` de 005).
- [x] Probar con dos canciones de BPM/mood distintos — Arctic Monkeys 505
      (bpm 70.75, mood predicho "energia") + Michael Jackson Beat It (bpm
      136.0, mood "accion"): `plan_encontrado: true`, `crossfade_suave`,
      compatibilidad de octava (Δ=4.0% entre 70.75×2=141.5 y 136.0), armonía
      "Tonalidad Idéntica" (cos=0.95), beatmatch recomendado. Score final 0.699.
- [ ] Probar caso `plan_encontrado: false` (BPM/mood muy incompatibles) — no
      se probó explícitamente por tiempo; el camino de "sin par compatible"
      está implementado (`UMBRAL_AROUSAL_DIFF`/`MIN_SCORE_COMPATIBILIDAD`)
      pero no se disparó en el par de prueba usado.
- [x] Probar con archivos fuera de `music_library.db` como A/B — ambas
      canciones de prueba se pasaron como rutas de archivo directas (no IDs
      de la librería), confirmando que no depende de tener la canción ya
      escaneada.
- [x] Exponer `POST /mixup-plan` — probado con curl subiendo dos `.flac`
      reales, `HTTP 200` en ~15s.
- [x] Ejemplo real documentado abajo.

## Ejemplo real (2026-07-06)

Arctic Monkeys - 505 (A, saliente) → Michael Jackson - Beat It (B, entrante):

```json
{
  "plan_encontrado": true,
  "tramo_A": [0.0, 54.0],
  "tramo_B": [93.0, 258.15],
  "score": 0.699,
  "transicion": {
    "tipo_transicion": "crossfade_suave",
    "razon": "BPM compatibles con octava (Δ=4.0%) y armonía compatible (Tonalidad Idéntica, cos=0.95): cruce óptimo de 6.0s.",
    "parametros": {"duracion_seg": 6.0, "curva_fundido": "equal_power",
                    "ganancia_inicio_B": 0.89, "alinear_beats": true}
  }
}
```

## Costo medido

~15-17s por par (2× `analyze_song` completo + 2× `extraer_vector_track`, no
cacheados — ver riesgo pendiente en 004). Aceptable para una demo puntual, no
para uso interactivo en tiempo real.
