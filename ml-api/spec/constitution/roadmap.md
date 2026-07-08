# Roadmap

Orden de implementación. Cada feature depende de la anterior.

1. **[001-mood-model-training](../features/001-mood-model-training/spec.md)**
   Entrenar y serializar el clasificador de mood a partir de
   `export/library.json` (dataset ya existente, 160 canciones etiquetadas).
   Sin esto no hay "coeficientes" que servir — es la base de todo lo demás.

2. **[002-fastapi-analysis-endpoint](../features/002-fastapi-analysis-endpoint/spec.md)**
   Endpoint FastAPI base: carga el `.joblib` de 001 + envuelve `analyzer.py`
   como función pura, expone `/health` y una respuesta combinada
   (DSP + predicción de mood) sin todavía diferenciar PC/app.

3. **[003-platform-router-pc-app](../features/003-platform-router-pc-app/spec.md)**
   Añade el parámetro `platform` y los dos schemas de salida (completo para
   PC, compacto para app), reutilizando la misma extracción de 002.

4. **[004-continuous-song-vectors](../features/004-continuous-song-vectors/spec.md)**
   Extiende la extracción de curvas de `analyzer.py` (`rms_full`/`onset_full`/
   `sc_full`, hoy sólo 3 valores/seg sin chroma) a una serie continua de
   vectores multi-dimensionales (rms, onset, spectral_centroid, chroma) cada
   3s para toda la canción, persistida y expuesta por la API — sin esto no
   hay con qué evaluar un timestamp arbitrario en 005/006.

5. **[005-hook-point-scorer](../features/005-hook-point-scorer/spec.md)**
   Heurística (no ML entrenado) que puntúa cualquier timestamp de la serie
   continua de 004 según el criterio "sube a un pico cercano, no corta en el
   pico, baja a un nivel similar (no igual) al de inicio" — generaliza a
   cualquier canción nueva porque opera sobre la curva, no sobre un catálogo
   conocido.

6. **[006-cross-song-mixup-planner](../features/006-cross-song-mixup-planner/spec.md)**
   Dadas dos canciones (nuevas o de la librería), usa 004 para vectorizarlas,
   005 para rankear puntos de salida en A y de entrada en B, agrupa por
   BPM/sentimiento (reutilizando `ordenar_cola_por_tempo` y las ideas de 001),
   y alimenta los mejores pares a `calcular_transicion_optima`
   (`transition.py`, ya existente) para producir un plan de edición ordenado
   — soundtrack de dos canciones para un video/historia.

No se planifica todavía integrar el endpoint dentro de `scan_library.py` ni de
la app Android — eso es trabajo de consumo posterior, fuera de este roadmap.
