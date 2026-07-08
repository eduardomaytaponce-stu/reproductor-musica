# 004 — Vectorización continua de la canción

## Qué hace

Extiende `extraer_curvas_completas` (hoy en [analyzer.py:84-116](../../../analyzer.py#L84-L116),
que sólo devuelve `rms_full`/`onset_full`/`sc_full` a 1 valor/seg, sin
información armónica) para producir una **serie continua de vectores
multi-dimensionales cada 3 segundos**, para toda la duración de la canción:

```
vector(t) = [rms(t), onset_strength(t), spectral_centroid(t), chroma(t) (12 dim)]
```

15 dimensiones por bin de 3s. Se elige 3s (no 1s) como resolución de
persistencia porque es suficiente para el criterio de forma de curva de 005
(subir/bajar en escalas de 5-30s) y porque a 1s con chroma de 12 dims una
canción de 4 min ya son ~240×15 valores — a 3s baja a ~80×15, más manejable
para servir por HTTP y comparar entre canciones.

Esto **no reemplaza** los `transition_points` de 8 puntos que ya existen
(`analyzer.py:637-679`) — esos siguen sirviendo para cue_points/mood. Esta es
una serie nueva, de más baja resolución pero cobertura completa, pensada para
que 005/006 puedan evaluar *cualquier* timestamp, no sólo los 8
preseleccionados.

## Por qué reutilizar la pasada existente y no una nueva

`extraer_curvas_completas` ya hace una sola pasada por el audio con
`soundfile` (sin remuestrear, rápido) para rms/onset/spectral_centroid. Añadir
chroma ahí implica un FFT adicional por bloque de 3s (no por segundo), así que
el costo extra es ~3x más barato que si se calculara a 1s. No se debe abrir
una segunda lectura completa del archivo de audio sólo para chroma.

## Criterios de aceptación

- [ ] La serie cubre el 100% de la duración de la canción (no sólo
      intro/outro/8 puntos).
- [ ] Resolución fija de 3s por bin, configurable por constante (no
      hardcodeada en múltiples lugares).
- [ ] Se persiste en `music_library.db` (columna nueva, ej.
      `vector_track_json`) — no sólo en memoria del proceso de análisis.
- [ ] El endpoint `/analyze` (002/003) con `platform=pc` incluye esta serie en
      la respuesta; `platform=app` **no** la incluye (payload demasiado
      grande para el teléfono y la app no la necesita).
- [ ] Corriendo esto sobre una canción ya en la librería, los valores de
      `rms`/`spectral_centroid` en los bins que coinciden con un
      `transition_point` existente son consistentes (mismo orden de magnitud)
      con los ya guardados — valida que no hay un bug de escala entre las dos
      formas de extracción.

## Fuera de alcance

- Downsampling adaptativo (bins más finos en zonas de cambio rápido) — bins
  de tamaño fijo alcanza para 005/006.
- Migrar canciones ya analizadas automáticamente — se recalculan bajo demanda
  o en el próximo `scan_library.py` completo.
