# Siguiente paso — Reproductor FLAC Hi-Fi

> Nota de continuidad para retomar el trabajo. Última sesión: 2026-06-04.

## 📱 FASE MÓVIL — definida (app standalone)

Decisión: app **Android NATIVA (Kotlin/Compose) vía Google AI Studio Build**,
**autónoma y offline** (NO control remoto de la PC; cuando el usuario sale la PC
está apagada). Tamaño 2-5 GB OK, celular min 8 GB RAM.

Arquitectura: la PC **analiza y exporta** un "paquete musical"; el celular solo
**consume metadatos precomputados** (batería mínima, no analiza).
- HECHO: **`export_library.py`** → `export/library.json` (143 canciones: bpm, mood,
  artista/título, cue_points energéticos). `--copy` empaqueta los FLAC en `export/music/`.
- Detección de actividad: **híbrido** = acelerómetro (deporte) + mood manual/voz
  (Warhammer sedentario). Modo combate = subir zona de BPM objetivo.
- Voz offline en el celular = `SpeechRecognizer` on-device (NO el openwakeword/
  Faster-Whisper del plan, que es para la PC).
- El **prompt completo para la IA de Google** (Kotlin nativo) está en el historial de
  esta sesión; consume `library.json`, hace transiciones con cue_points, modo
  Nativo/Pro, modo actividad por acelerómetro + voz, batería como prioridad.
- Bit-perfect NO aplica en el celular (imposible); ese sigue siendo el modo de la PC.

## ⭐⭐⭐ FIXES recientes (feedback usuario)

- **Hueco de silencio en transiciones de distinto sample-rate** (CORREGIDO):
  `_open_aplay` ahora hace **reapertura rápida** si PipeWire ya está suspendido
  (`_pw_suspended`), y `_do_crossfade` mezcla al rate del DAC YA abierto (no reabre
  durante el fundido). Same-rate = sin hueco; cross-rate = hueco mínimo tras el fundido.
  Validado: 44.1k→96k llega a bit-perfect.
- **Modo de transición Nativo/Pro** (NUEVO): pill `#transition-mode-toggle` en el
  panel de transición. **Nativo** = mínimo `MIN_PLAY_NATIVO=20s` por canción + la
  entrada enérgica no cae tan al final (evita puentes de <3s). **Pro** = transiciones
  puente sin mínimo (conserva el comportamiento que al usuario le gustó).
- **Distorsión modo DJ** (CORREGIDO): se desactivó el beatmatch por `playbackRate`
  (con preservesPitch=false distorsionaba tono y quedaba remodulado). Ahora tempo nativo.
- **Cuelgue DJ**: `release_device` síncrono devuelve el DAC a PipeWire + audioCtx.resume.
- **Nombre canción / sobre-volumen crossfade**: corregidos.

PENDIENTE inmediato:
- ~~Gestión MANUAL de playlists~~ HECHO: botón "➕ Nueva playlist vacía" + botón "+"
  por canción (aparece al hover) con menú "Nueva playlist…" / añadir a existente
  (✓ si ya está) + toast. Endpoint `PUT /api/playlists/{id}` añadido. Validado.
- Limitación conocida: el crossfade del motor aplay **bloquea el worker ~6s** (status
  rezagado y pause/seek no responden DURANTE el fundido). Mejora: escribir el fundido
  por bloques.

## ⭐⭐ BLOQUE 1 (transiciones inteligentes) — EN PROGRESO

HECHO:
- `cue_points.py`: detección de puntos clasificados por **energía** (valles + picos),
  no solo valles. `enrich_cues.py` actualizó las **143 canciones** (columna
  `transition_points` con `{timestamp_seg, tipo, energia, clase}`). Backup en
  `music_library.db.bak`.
- **Entrada enérgica**: el motor (`AplayHiFiEngine.load`/`_do_crossfade`) acepta
  `entry_offset`; el endpoint `/api/hifi/play` y el frontend (`chooseEntryOffset`)
  hacen que, si el contexto es enérgico (BPM≥115), la entrante empiece en su
  sección fuerte. VALIDADO: Free Bird entra en el solo (~303s), no en 0:00.
- **Disparo temprano**: `exitTriggerTime` dispara el fundido en el primer punto
  enérgico del tramo final (>60%), sin esperar a perder el ritmo.

HECHO (Bloque 3 — gestión de biblioteca):
- **Buscador** de canciones en vivo (filtra por canción/artista) en la pestaña
  Biblioteca, con contador resultados/total.
- **Generador de playlists**: pestañas Biblioteca/Playlists; `/api/playlists`
  (tabla `playlists`) CRUD + `/api/playlists/suggest` (auto-agrupa por BPM en
  Acción/Energía/Enfoque/Relax). UI: auto-generar, guardar con nombre, reproducir
  (cola que respeta `selectSmartNextSong`), borrar. Validado por TestClient + HTTP.
- Nombre de canción: título arriba / autor abajo (lista + banner).
- Disparo intermedio: `exitTriggerTime` ahora usa el ÚLTIMO punto enérgico cerca
  del final (parcial; el usuario quiere afinarlo más — sigue en pendientes).

PENDIENTE de Bloque 1:
- **Clustering por vector/mood** para el auto-siguiente (hoy `smart_next` es solo
  por BPM; falta usar chroma/mood para elegir canciones cercanas en vector). ← lo
  que el usuario marcó como "omitido".
- Energía **absoluta/normalizada por loudness** para emparejar energía ENTRE
  canciones (hoy es relativa dentro de cada canción).
- Afinar el punto de salida con momentum BPM y excepciones de drops.
- **[Feedback usuario] Punto de disparo intermedio**: `exitTriggerTime` ahora
  sobre-corrige hacia los máximos enérgicos y dispara demasiado temprano. Buscar
  el punto INTERMEDIO entre "esperar a que muera el ritmo" (antiguo) y "saltar al
  primer máximo del tramo final" (actual). Probablemente: último punto con energía
  ≥ media DENTRO de una ventana razonable cerca del final, o un compromiso por %.

## ⭐ ACTUALIZACIÓN — motor de crossfade implementado

Se construyó el **motor propio `AplayHiFiEngine`** en `player_engine.py`
(soundfile + numpy + `aplay -D hw:`), que es el motor Hi-Fi por defecto en
`main.py` (`get_hifi_engine`). Hace:
- Reproducción **bit-perfect** (PCM crudo S32_LE al rate nativo de cada archivo).
- **Crossfade equal-power al rate nativo de la entrante** → vuelve a bit-perfect
  sin costura (resuelve el límite tipo MPD/mpv). Param `crossfade` en
  `/api/hifi/play`; el frontend lo usa en next/auto-outro/chat (6 s) y corte en
  selección directa.
- **Coordinación con PipeWire**: suspende el sink del DAC antes de abrir exclusivo
  (`pactl suspend-sink … 1`, con reintentos) y lo devuelve al parar (`… 0`).

**Validado:** la PRIMERA prueba funcional completa pasó — play, crossfade
44.1k→96k **bit-perfect**, pause/resume/seek/stop. Luego, por `kill -9` agresivos
de prueba, el DAC USB se re-enumeró (de card3 a card1) y quedó en estado ocupado;
se recuperó solo (el device string `hw:CARD=Mini` por NOMBRE sigue válido).

### Limitaciones conocidas (a endurecer)
1. **Responsividad durante el crossfade**: `_do_crossfade` escribe el fundido
   completo de una vez → el worker NO atiende pause/seek/stop durante ~6 s y el
   status muestra valores viejos. Arreglo: escribir el fundido en bloques dentro
   del bucle, revisando flags y actualizando `_pos`.
2. **Contención con PipeWire**: el `suspend-sink` + reintentos a veces necesita
   más espera para que PipeWire suelte el hw. Si aparece "DAC ocupado": cerrar la
   app que use el DAC, o reproducir de nuevo en unos segundos. Si el DAC se quedó
   raro tras un corte forzado, **reconectar el USB** lo resetea.
3. Falta batería de tests larga (canción completa sin underruns) y validación
   interactiva real en el navegador.

## Dónde estamos

El proyecto es un reproductor de música FLAC con análisis de transiciones óptimas
(descomposición del audio en `rms`/`chroma`/`spectral_centroid`/`beats`, motor DSP
en `transition.py`). Esta semana el foco viró a **calidad de audio**: que iguale o
supere a VLC.

### Lo que YA funciona (validado en hardware)
- **Modo Hi-Fi bit-perfect**: backend `mpv → ALSA exclusivo` en el DAC
  `hw:CARD=Mini,DEV=0` (Kiwi Ears Allegro, hasta 384k/32-bit). Controlado por socket
  IPC JSON (sin `libmpv`/`python-mpv`). Probado bit-perfect a 44.1k/16 y 96k/24, y en
  cortes entre frecuencias distintas. Motor: `player_engine.py`. Endpoints
  `/api/hifi/{play,pause,resume,seek,stop,status}` en `main.py`.
- **Modo DJ**: el motor Web Audio original en el navegador (crossfade, barrido, eco,
  vinilo, beatmatch). Funciona pero **solo a 48 kHz** (el navegador remuestrea vía
  PipeWire) → NO bit-perfect.
- **Interruptor Hi-Fi/DJ** en la UI (`index.html`): solo un motor posee el DAC a la
  vez. En Hi-Fi la web es un MANDO + visualizador (audio 100% local en el backend);
  en DJ la web es el motor de audio.
- DB limpia (143 canciones; eliminados los huérfanos dummy.flac/test_song.wav).

### Lo que FALLÓ y por qué
- El **híbrido por conmutación de dispositivo** (mismo mpv alternando exclusivo↔
  PipeWire↔exclusivo para mezclar durante la transición y volver a bit-perfect)
  **no es viable**: PipeWire no suelta el DAC a tiempo para reabrir exclusivo.
  Probados 3 métodos (conmutación directa, reintentos con recarga de AO,
  `pactl suspend-sink`) — los tres fallaron. Era el enfoque equivocado.

### Concepto clave (no olvidar)
- Bit-perfect y crossfade son **mutuamente excluyentes EN EL INSTANTE del fundido**,
  por definición (mezclar = crear muestras nuevas ≠ bits originales). Cierto en
  TODOS los reproductores. Pero antes y después del fundido sí puede ser bit-perfect.
- Programar transiciones FLAC SÍ se puede; lo que no existe es un crossfade
  "bit-perfect". El objetivo realista: **bit-perfect normal + crossfade a resolución
  NATIVA (no 48k) durante el fundido, todo en el backend.**

## Objetivo de la próxima sesión

Lograr **crossfades de alta resolución sin salir del backend**, con un **único motor
dueño del DAC que mezcla internamente** (passthrough bit-perfect en reproducción
normal; mezcla en float a resolución nativa solo durante el fundido). Esto evita el
problema de PipeWire (nunca se suelta el dispositivo) y es mejor que el modo DJ actual.

### Tareas
1. **Buscar en GitHub** soluciones reales y compararlas. En particular evaluar:
   - **MPD (Music Player Daemon)**: crossfade integrado + salida ALSA bit-perfect +
     control por protocolo (clientes web: myMPD, ympd).
   - **Motor propio en Python**: `sounddevice`/PortAudio + `soundfile`, passthrough
     bit-perfect + mezcla numpy durante el fade.
   - Otros: GStreamer (audiomixer), squeezelite/LMS, Snapcast.
2. Pros/contras, esfuerzo y riesgos de cada uno para el setup: PipeWire, DAC Kiwi
   Ears Allegro (hasta 384k/32-bit), FastAPI.
3. Recomendar uno. Si se aprueba el plan, implementarlo y probarlo en el DAC.
   **No modificar nada sin aprobar el plan primero.**

### Prompt para pegar al iniciar
```
Continúo el reproductor FLAC Hi-Fi. Lee SIGUIENTE_PASO.md, player_engine.py, main.py
y la memoria del proyecto antes de empezar. Objetivo: crossfades de alta resolución
en el backend con un único motor que es dueño del DAC y mezcla internamente
(bit-perfect normal; mezcla en float a resolución nativa solo durante el fundido).
Busca en GitHub soluciones reales y compáralas — evalúa MPD (crossfade + ALSA
bit-perfect, control web) vs. motor propio en Python (sounddevice/PortAudio +
soundfile). Dame pros/contras, esfuerzo y riesgos para mi setup (PipeWire, DAC Kiwi
Ears Allegro hasta 384k/32-bit, FastAPI), recomienda uno y NO modifiques nada sin
que apruebe el plan primero.
```

## Cómo ejecutar / configurar (estado actual)
- Ejecutar: `python main.py` → http://127.0.0.1:8000
- Para Hi-Fi: cerrar otras apps que usen el DAC (necesita modo exclusivo).
- Cambiar de DAC: editar `DEFAULT_ALSA_DEVICE` en `player_engine.py`
  (buscar el ID con `aplay -l` o `mpv --audio-device=help`).
- Volumen: en el DAC/sistema (en Hi-Fi va fijo al 100% para no alterar bits).

## Archivos relevantes
- `player_engine.py` — motor bit-perfect (mpv IPC). GOTCHA: usar
  `--gapless-audio=weak` (no `yes`, que rompe bit-perfect al cambiar de rate).
- `main.py` — endpoints `/api/hifi/*` + `/api/transition` (motor DSP).
- `transition.py` — motor de decisión de transiciones (tipo + duración + beatmatch).
- `index.html` — UI doble modo (controlador `HiFi` + `setMode()`).
- `analyzer.py` / `scan_library.py` — extracción de features a SQLite.
