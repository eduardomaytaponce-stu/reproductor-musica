# Plan — 004

## `analyzer.py` (o `ml-api/app/dsp.py` si se prefiere no tocar el original)

```python
VECTOR_BIN_SEG = 3.0

def extraer_vector_track(filepath):
    """
    Una sola pasada: rms/onset/spectral_centroid a 1 val/seg (igual que
    extraer_curvas_completas) + chroma cada VECTOR_BIN_SEG agregando bloques.
    Devuelve list[dict]: [{t_start, t_end, rms, onset, spectral_centroid, chroma[12]}, ...]
    """
    rms_full, onset_full, sc_full, sr_native = extraer_curvas_completas(filepath)
    # chroma: cargar con librosa a SR_ANALYSIS (ya se hace en otros pasos),
    # STFT con hop ajustado a VECTOR_BIN_SEG, promediar por bin.
    ...
    bins = []
    for i in range(n_bins):
        t0, t1 = i * VECTOR_BIN_SEG, (i + 1) * VECTOR_BIN_SEG
        bins.append({
            "t_start": t0, "t_end": t1,
            "rms": mean(rms_full[t0:t1]),
            "onset": mean(onset_full[t0:t1]),
            "spectral_centroid": mean(sc_full[t0:t1]),
            "chroma": chroma_bin_i,  # 12 floats, normalizado
        })
    return bins
```

## `save_to_db` / schema

- Nueva columna `vector_track_json TEXT` en `songs` (mismo patrón de
  migración incremental que ya usan las columnas `intro_chroma`, etc. en
  `init_db()` — ver [analyzer.py:456-511](../../../analyzer.py#L456-L511)).
- `analyze_song()` llama a `extraer_vector_track` como paso adicional (paso 7)
  y lo agrega al dict que devuelve.

## `ml-api/app/schemas.py` (extiende 002/003)

```python
class VectorBin(BaseModel):
    t_start: float
    t_end: float
    rms: float
    onset: float
    spectral_centroid: float
    chroma: list[float]  # len 12

# AnalysisResponsePC gana un campo:
class AnalysisResponsePC(AnalysisResponse):
    vector_track: list[VectorBin]
```

## Riesgo conocido

Persistir esto para las 160 canciones ya analizadas requiere re-correr
`analyzer.py` sobre cada archivo (no se puede derivar `chroma` de lo que ya
está en `rms_full`/`onset_full`, que no llevan información armónica). Se
acepta como trabajo de re-escaneo, no de migración de datos.
