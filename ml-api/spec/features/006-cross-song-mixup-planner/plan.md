# Plan — 006

## `ml-api/app/mixup_planner.py`

```python
UMBRAL_AROUSAL_DIFF = 0.2   # diferencia máxima de arousal entre salida_A y entrada_B
MIN_SCORE_COMPATIBILIDAD = 0.4

def candidatos_salida(vector_track_a):
    """mejores_puntos_enganche(vector_track_a) -> usar t_end de cada uno como punto de salida."""

def candidatos_entrada(vector_track_b):
    """mejores_puntos_enganche(vector_track_b) -> usar t_start de cada uno como punto de entrada."""

def arousal_en(vector_track, t):
    """energia_combinada del bin más cercano a t, normalizada 0-1 (reusa 005)."""

def generar_plan(cancion_a, cancion_b):
    vt_a = obtener_o_calcular_vector_track(cancion_a)   # 004, cachea si ya está en la libreria
    vt_b = obtener_o_calcular_vector_track(cancion_b)

    salidas = candidatos_salida(vt_a)
    entradas = candidatos_entrada(vt_b)

    pares = []
    for s in salidas:
        for e in entradas:
            if abs(arousal_en(vt_a, s["t_end"]) - arousal_en(vt_b, e["t_start"])) > UMBRAL_AROUSAL_DIFF:
                continue   # descarta antes de llamar la parte cara

            seg_saliente = analyze_segment(cancion_a.filepath, s["t_end"], 15.0)
            seg_entrante = analyze_segment(cancion_b.filepath, e["t_start"], 15.0)
            transicion = calcular_transicion_optima(
                seg_saliente, seg_entrante, cancion_a.bpm, cancion_b.bpm
            )   # transition.py, sin cambios

            score = (
                0.4 * s["score"] + 0.4 * e["score"]
                + 0.2 * (1.0 if transicion["parametros"]["alinear_beats"] else 0.5)
            )
            if score < MIN_SCORE_COMPATIBILIDAD:
                continue
            pares.append({"salida": s, "entrada": e, "transicion": transicion, "score": score})

    pares.sort(key=lambda p: p["score"], reverse=True)
    if not pares:
        return {"plan_encontrado": False, "razon": "ningún par supera el umbral de compatibilidad"}

    mejor = pares[0]
    return {
        "plan_encontrado": True,
        "tramo_A": [0.0, mejor["salida"]["t_end"]],
        "transicion": mejor["transicion"],
        "tramo_B": [mejor["entrada"]["t_start"], cancion_b.duration],
        "alternativas": pares[1:4],
    }
```

## Reutilización explícita (no reimplementar)

- `mejores_puntos_enganche` → 005, tal cual.
- `analyze_segment` → `analyzer.py`, tal cual (ya extrae rms/chroma/spectral_centroid/beats de una ventana).
- `calcular_transicion_optima` → `transition.py`, tal cual.
- `arousal_en` es la única función nueva de bajo nivel — un lookup sobre el `vector_track` de 004.

## `router.py`

- `POST /mixup-plan`: recibe dos referencias de canción (id de librería o
  archivo a subir), delega a `generar_plan`.

## Riesgo conocido

`calcular_transicion_optima` espera segmentos con `beats` locales — para
puntos que no coinciden con un `transition_point` ya guardado, hay que correr
`analyze_segment` on-demand en ese timestamp (más lento que leer de DB). Se
acepta el costo porque sólo se llama sobre los pares que ya pasaron el filtro
de arousal, no sobre todos los candidatos.
