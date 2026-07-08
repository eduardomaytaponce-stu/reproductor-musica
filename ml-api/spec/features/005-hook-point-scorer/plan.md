# Plan — 005

## `ml-api/app/hook_scorer.py`

```python
ARCO_MIN_SEG = 15.0
ARCO_MAX_SEG = 45.0
BANDA_RETORNO_REL = (0.05, 0.25)   # t_end debe volver a 5%-25% de diferencia
                                    # relativa vs energia(t_start) — ni loop
                                    # exacto ni bajada insuficiente
PESO_PROMINENCIA = 0.4
PESO_SUBIDA = 0.3
PESO_BAJADA = 0.2
PESO_DURACION = 0.1

def energia_combinada(bin_): return 0.6 * bin_["rms"] + 0.4 * bin_["onset"]  # proxy arousal

def buscar_pico(vector_track, i_start, ventana_bins):
    """Índice del máximo de energia_combinada en vector_track[i_start:i_start+ventana_bins]."""

def buscar_retorno(vector_track, i_peak, nivel_inicio, max_bins):
    """Primer índice después de i_peak cuya energia_combinada cae dentro de
    BANDA_RETORNO_REL respecto a nivel_inicio. None si no se encuentra."""

def score_candidato(vector_track, i_start):
    i_peak = buscar_pico(...)
    if i_peak == i_start:          # no hay subida real
        return None
    i_end = buscar_retorno(...)
    if i_end is None:
        return None
    duracion = (i_end - i_start) * VECTOR_BIN_SEG
    if not (ARCO_MIN_SEG <= duracion <= ARCO_MAX_SEG):
        return None
    prominencia = energia_combinada(vector_track[i_peak]) - energia_combinada(vector_track[i_start])
    subida = ...   # pendiente media t_start -> t_peak
    bajada = ...   # qué tan monótona es la caída t_peak -> t_end (penaliza rebotes)
    duracion_score = 1.0 - abs(duracion - (ARCO_MIN_SEG+ARCO_MAX_SEG)/2) / ((ARCO_MAX_SEG-ARCO_MIN_SEG)/2)
    score = (PESO_PROMINENCIA*prominencia + PESO_SUBIDA*subida
             + PESO_BAJADA*bajada + PESO_DURACION*duracion_score)
    return {"t_start": ..., "t_peak": ..., "t_end": ..., "score": score, ...}

def mejores_puntos_enganche(vector_track, top_k=5):
    candidatos = [score_candidato(vector_track, i) for i in range(len(vector_track))]
    candidatos = [c for c in candidatos if c is not None]
    candidatos.sort(key=lambda c: c["score"], reverse=True)
    return candidatos[:top_k]
```

## Integración con la API

- `POST /hook-points`: recibe un audio (o reutiliza `/analyze` con
  `platform=pc` para obtener `vector_track` de 004), devuelve
  `mejores_puntos_enganche`.

## Riesgo conocido

Evaluar cada bin como candidato (`range(len(vector_track))`) es O(n²) en el
peor caso por la búsqueda de pico/retorno con ventana. Para una canción de 4
min a bins de 3s son ~80 candidatos — trivial. No optimizar prematuramente.
