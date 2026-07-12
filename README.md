# Cloud-Fi — Reproductor FLAC inteligente 🎧🤖

Reproductor de música local-first de alta fidelidad (FLAC) con transiciones automáticas tipo DJ (basadas en vectorizacion) y modo actividad(segun los BPM). Dos apps que comparten una biblioteca precomputada:

- **PC "el estudio"** (Python/FastAPI) — análisis, reproducción **Hi-Fi bit-perfect** (ALSA exclusivo → DAC), mezclador DJ en el navegador (Web Audio) y **export** de metadatos.
- **Android "Cloud-Fi Go"** (Kotlin/Compose) — reproductor autónomo **100% offline**, activity-aware (acelerómetro + voz).

## Arranque rápido
```bash
uv run main.py        # http://127.0.0.1:8000
```

## Documentación
- 📖 **[MANUAL_USUARIO.md](MANUAL_USUARIO.md)** — cómo usar ambos reproductores.
- 🛠️ **[GUIA_DESARROLLADOR.md](GUIA_DESARROLLADOR.md)** — arquitectura, pipeline, formato `library.json`, build del app Android.

## Estructura
`analyzer.py` (ETL) · `scan_library.py` (escaneo) · `main.py` (API) · `player_engine.py` (motor bit-perfect) · `transition.py` (decisión de mezcla) · `export_library.py` (export al app) · `voice_assistant.py` (voz) · `index.html` (UI web) · `music_library.db` (SQLite).
