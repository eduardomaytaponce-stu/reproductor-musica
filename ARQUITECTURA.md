# Arquitectura y pipeline — Reproductor FLAC Hi-Fi

## 1. Los frameworks y qué hace cada uno

| Framework / herramienta | Rol en el proyecto | ¿Óptimo? |
|---|---|---|
| **FastAPI + uvicorn** | Servidor web/API: sirve `index.html`, los endpoints REST y el streaming. | ✅ óptimo |
| **SQLite** (`music_library.db`) | Base de datos: 1 fila por canción (bpm, duración, vectores, `transition_points`) + tabla `playlists`. | ✅ óptimo (1 usuario, local) |
| **librosa** | Análisis offline: BPM (`feature.tempo`), chroma, beats, RMS. **Pesado**, solo en escaneo. | ✅ para análisis |
| **soundfile (libsndfile)** | Decodifica FLAC a muestras (int32 bit-perfect / float para mezcla). | ✅ óptimo |
| **numpy** | Mezcla del crossfade, conversión a int32, cálculos de energía. | ✅ óptimo |
| **soxr** | Resampler con estado (streaming) para transiciones cross-rate sin clics. | ✅ óptimo |
| **aplay** (alsa-utils) | Salida al DAC: `hw:` directo = ALSA exclusivo bit-perfect. | ✅ óptimo |
| **Web Audio API** (navegador) | Modo **DJ**: reproduce y mezcla en el navegador (no bit-perfect). | ⚠️ pesado, solo modo DJ |
| **sentence-transformers + torch** | Chat por mood: embeddings de una **plantilla de texto** (no audio real). ~2-3 GB. | ❌ desproporcionado |
| **mpv** (`BitPerfectPlayer`) | Motor viejo, **reemplazado** por el motor `aplay`. | ❌ código muerto |

## 2. El pipeline paso a paso

```
[1 ESCANEO]                [2 SERVIR]                 [3 REPRODUCIR]
scan_library.py            main.py (FastAPI)          player_engine.py
   |                          |                          (AplayHiFiEngine)
   v                          v                          |
analyzer.analyze_song   GET /api/songs --------> frontend (index.html)
 - feature.tempo (BPM)  GET /api/stream/{id}        |  modo Hi-Fi: POST /api/hifi/play
 - chroma, beats, RMS   POST /api/hifi/*            |     -> motor aplay -> DAC (bit-perfect)
 - cue_points (nivel_N) POST /api/transition        |  modo DJ: stream + Web Audio (navegador)
   |                    POST /api/search (chat)      |
   v                    GET/POST /api/playlists      v
music_library.db  <----------+               transiciones inteligentes
   |                                          (chooseEntryOffset / exitTriggerTime)
   v
[4 EXPORTAR] export_library.py -> export/library.json -> [5 APP MÓVIL Android]
```

### Etapa 1 — Análisis (offline, una vez por canción)
`scan_library.py` recorre la carpeta → por cada FLAC nuevo llama a
`analyzer.analyze_song`:
- **BPM**: `librosa.feature.tempo()` + fold de octava (`estimar_bpm`). Robusto.
- **Vectores de transición** (intro/outro 15s): chroma (armonía), RMS (energía),
  spectral_centroid (brillo), beats (timestamps).
- **Puntos de corte** (`cue_points.detectar_puntos_energia`): 8 puntos clasificados
  por energía RMS en `nivel_1..10` (valles y picos).
Todo se guarda como JSON en columnas de `music_library.db`. **El audio NO se vuelve
a analizar en reproducción** (clave para la app móvil: batería mínima).

### Etapa 2 — Servir (`main.py`, FastAPI)
- `GET /api/songs`: lee la DB y devuelve la lista con metadatos.
- `GET /api/stream/{id}`: streaming con HTTP Range (para el modo DJ del navegador).
- `POST /api/hifi/{play,pause,seek,stop,status}`: controla el motor bit-perfect.
- `POST /api/transition`, `/api/songs/smart_next`: usan `transition.py` para decidir
  tipo de fundido y la siguiente canción por vector (BPM+chroma+mood).
- `GET/POST/PUT/DELETE /api/playlists`: CRUD de playlists con `target_bpm`.

### Etapa 3 — Reproducir
**Modo Hi-Fi (`player_engine.AplayHiFiEngine`)** — el corazón:
- Un hilo worker lee la cola de peticiones. Decodifica con `soundfile`.
- **Mismo rate** → escribe muestras crudas int32 a `aplay -D hw:` → **bit-perfect**.
- **Distinto rate** (tras una transición) → resamplea al vuelo con `soxr` (con estado)
  **sin reabrir el DAC** → sin pausa. Con headroom −1 dB → sin clipping.
- **Crossfade**: lee colas de saliente+entrante, mezcla equal-power en numpy, escribe.
- Coordina con **PipeWire** (`pactl suspend-sink`) para tomar el DAC en exclusivo.

**Modo DJ (navegador, Web Audio)**: streamea el FLAC y mezcla en el navegador con
2 decks + ganancia. No bit-perfect (el navegador remuestrea a 48 kHz).

### Etapa 4 — Exportar (`export_library.py`)
Vuelca la DB a `export/library.json` (bpm, mood, cue_points, playlists) para la app.

### Etapa 5 — App móvil (Android nativo, vía Google AI)
Consume `library.json`, reimplementa la lógica de transición (mate simple),
modo actividad por acelerómetro + voz. Ver `APP_PLAN.md`.

## 3. Auditoría — qué sobra / qué mejorar

**Ya limpiado (seguro):** imports/variables muertos (`asyncio`, `Header`, `torch`,
`encoder`) con ruff.

**Recomendado quitar (código muerto):**
- `BitPerfectPlayer` + `_selftest` en `player_engine.py` (~280 líneas) — motor mpv
  viejo, reemplazado por `AplayHiFiEngine`. Solo lo usa su propio `__main__`.
- `plan arquitectura/analyzer.py` — es un documento markdown con extensión `.py`
  (confunde a las herramientas). Renombrar a `.md`.

**Mejorar (desproporcionado):**
- `sentence-transformers + torch` (~2-3 GB) para el chat: hoy genera embeddings de
  una plantilla de texto, no del audio. Ya hay un fallback por palabras clave.
  **Sugerencia**: quitar la dependencia y usar solo reglas → −2-3 GB y arranque
  instantáneo. (El mood real ya sale del BPM/energía, no del texto.)

**Deuda estructural (no urgente, riesgoso con poco tiempo):**
- `main.py` (640 líneas) mezcla streaming, NLP, playback, playlists, voz →
  partir en routers (`routers/hifi.py`, `routers/playlists.py`, ...).
- `@app.on_event` deprecado → migrar a `lifespan`.
- Scripts de un solo uso (`fix_bpm.py`, `enrich_cues.py`) → mover a `tools/`.

**Robusto y óptimo (no tocar):** el motor `aplay` (soundfile+numpy+soxr+aplay),
el análisis con librosa, FastAPI/SQLite.
