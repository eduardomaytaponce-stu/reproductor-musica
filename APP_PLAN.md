# Plan final de la App móvil "Cloud-Fi Go" + Prompt para Google AI Studio

## Arquitectura (2 apps)

| App | Rol | Tecnología | Estado |
|---|---|---|---|
| **PC — "el estudio"** | Análisis, Hi-Fi bit-perfect, DJ, **exportación** | Python/FastAPI (ya hecho) | ✅ |
| **Android — "el de campo"** | Reproductor autónomo offline, activity-aware | Kotlin/Compose vía Google AI | ⏳ a generar |

**Puente:** `python export_library.py [--copy]` → `export/library.json` (+ `export/music/`).
El celular **no analiza nada** (batería mínima); consume metadatos precomputados.

## Formato de `library.json` (lo que consume el app)

```json
{
  "version": 1,
  "count": 144,
  "moods": ["accion","energia","enfoque","relax"],
  "songs": [{
    "id": 147, "file": "Pitbull - We Are One.flac",
    "title": "We Are One", "artist": "Pitbull feat. ...",
    "bpm": 123.0, "duration": 222.6, "mood": "energia",
    "cue_points": [
      {"t": 0.0,   "energia": 0.31, "clase": "nivel_4", "tipo": "intro"},
      {"t": 98.0,  "energia": 1.00, "clase": "nivel_10","tipo": "segmento_3"},
      {"t": 207.6, "energia": 0.82, "clase": "nivel_9", "tipo": "outro"}
    ]
  }],
  "playlists": [{"name":"Combate","song_ids":[3,147],"target_bpm":140}]
}
```
- `mood` por BPM: relax(<95) · enfoque(95-115) · energia(115-125) · accion(≥125).
- `cue_points[].clase` = `nivel_1..10` (intensidad por RMS). Enérgico = `nivel ≥ 6`.
- `bpm` ya corregido (feature.tempo + fold de octava).

## Lógica que el app reimplementa (mate simple, sin DSP)

- **Entrada enérgica**: si el contexto es enérgico (bpm previo ≥115), la entrante
  empieza en su cue point de mayor energía (`nivel≥6`) dentro de una ventana; si no,
  en 0. **Modo Nativo** = mínimo ~20s/canción + entrada no tan al final. **Modo Pro**
  = transiciones puente (cualquier duración).
- **Salida**: dispara el fundido en el último cue point enérgico del tramo final.
- **Crossfade**: 2 instancias ExoPlayer + ganancia equal-power (limitador a 0 dBFS).
- **Modo actividad (clave)**: acelerómetro (batched, bajo consumo) → intensidad →
  zona de BPM objetivo (caminar→enfoque, correr→energia, intenso→**combate** ≥125).
  Re-evalúa ~1×/min con histéresis. **Override manual** (chips Relax/Enfoque/Energía/
  Combate) y **voz offline** (`SpeechRecognizer` on-device) para casos sedentarios
  (Warhammer): "modo combate", "relájate", "sube el ritmo".
- **Playlists** con `target_bpm`: ordena/sirve por cercanía al BPM (ej. combate=140).

---

## PROMPT PULIDO para Google AI Studio Build (Android nativo)

> Build a **native Android app (Kotlin + Jetpack Compose, minSdk 26)** called **"Cloud-Fi Go"**: a **fully offline, standalone** music player for sports, travel and board-games. **No server, no internet.** It does **NOT** analyze audio — all metadata is precomputed and imported.
>
> **IMPORT:** On first run the user picks a local folder with `library.json` and a `music/` folder of FLAC files (exported from a PC). Persist with Room + DataStore.
>
> **`library.json` schema:** `{ version, songs:[{ id, file, title, artist, bpm, duration, mood, cue_points:[{t, energia(0-1), clase("nivel_1".."nivel_10"), tipo}] }], playlists:[{name, song_ids, target_bpm}] }`. `mood` ∈ {relax,enfoque,energia,accion}. A cue point is "energetic" when its `nivel` ≥ 6.
>
> **Playback (Media3/ExoPlayer, FLAC):** smart transitions with **two players crossfaded by equal-power volume** (clamp the sum to 0 dBFS to avoid clipping) at cue points — no DSP. When transitioning A→B: if A.bpm ≥ 115, start B at its highest-`nivel` energetic cue point inside an allowed window; else start at 0. Trigger the fade near a late energetic cue point of A. Two modes via a toggle: **"Nativo"** (each song plays ≥ ~20s and the entry is capped so ≥20s remains) and **"Pro"** (bridge transitions, any duration).
>
> **Activity mode (headline feature):** read the **accelerometer** (batched, low power) to estimate motion intensity → map to a **target BPM zone** (still→relax<95, walking→enfoque 95-115, running→energia 115-125, intense→**combate** ≥125). Auto-select upcoming songs whose bpm/mood match the zone, re-evaluating ~once/minute **with hysteresis**. Provide a **manual mood override** (chips Relax/Enfoque/Energía/Combate) and **offline voice control** via Android's on-device `SpeechRecognizer` ("modo combate", "relájate", "sube el ritmo") — needed for sedentary intensity (e.g., Warhammer) where the accelerometer won't detect excitement.
>
> **Battery is the top priority:** precomputed metadata = minimal CPU; **foreground media service** with MediaSession (background + lock-screen + screen-off), batched sensors, **no always-on microphone** (voice via press-to-talk only).
>
> **Screens:** **Library** (search box filtering title/artist; cards show **song title on top, artist below**; a "＋" to add to a playlist). **Playlists** (create empty named playlist with an optional **target BPM**; add songs manually; auto-generate buckets by mood; play ordered by closeness to target BPM; edit BPM; delete). **Now-Playing** (album disc, fluid-wave canvas visualizer, transport, progress, and a prominent **current BPM zone + activity/combat indicator**). **Mood/Voice** control panel.
>
> **Aesthetic "Ambient Ethereal / Cloud-Fi":** animated **aurora gradient** background (sunset→night), **frosted-glass** cards (cream/lavender), **serif** titles (Playfair Display), **monospace** for technical data (JetBrains Mono), organic floating controls, **fluid wave** visualizer (lavender + cream spectrum).
>
> **Export/share** the active playlist (order + entry/exit cue points) to a file for re-import. 100% offline; everything persists locally.
