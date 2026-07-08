"""
Motor de análisis de audio — v2

Novedades vs v1:
- Una sola pasada rápida (soundfile nativo) para curvas completas a 1 valor/seg:
  RMS, spectral_flux (proxy de onset) y spectral_centroid.
- Segmentación estructural por change-point detection sobre esas tres curvas.
- BPM estimado por sección y ponderado por onset_strength → más robusto en
  canciones con secciones heterogéneas (ej. The Chain, huaynos, baladas).
- Perfil emocional simplificado por sección (arousal / valence proxies) basado
  en los principios de Dynamic MER (Circumplex de Russell).
- Sistema de alertas integrado: detecta BPM sospechoso en tiempo real.
- Los puntos de transición se derivan de los límites de sección + valles de
  energía, no de espaciado uniforme.
"""

import os
import sys
import argparse
import sqlite3
import json
from datetime import datetime

import librosa
import soundfile as sf
import numpy as np

DB_NAME = "music_library.db"
SR_ANALYSIS = 22050          # sr para segmentos de BPM y transition vectors
BPM_MIN = 70.0
BPM_MAX = 160.0
MIN_SECTION_DUR = 25         # segundos mínimos para estimar BPM de una sección
BPM_SAMPLE_DUR = 45.0        # segundos a cargar por sección para BPM
LOW_ONSET_ALERT = 5.0        # umbral de onset_mean para alertas (informativo)
CONFIDENCE_ALERT = 0.35      # umbral de bpm_confidence para alertas
# Umbral estricto para la auto-corrección de octava (halving).
# 5.0 era demasiado alto: música pop comprimida (Animals, Iron) tiene onset < 5 aunque
# sea energética → se dividía 104 BPM → 52 BPM incorrectamente.
# Con 1.5 sólo canciones verdaderamente suaves/ambient activan la corrección.
HALF_ONSET_THRESHOLD = 1.5
HALF_BPM_MIN = 130.0         # sólo corregir si el BPM ponderado está en zona sospechosa


# ---------------------------------------------------------------------------
# Helpers de tempo
# ---------------------------------------------------------------------------

def _fold_octava(bpm):
    """Pliega el BPM al rango perceptual [70, 160] corrigiendo errores de octava."""
    if not bpm or bpm <= 0:
        return 0.0
    while bpm > BPM_MAX:
        bpm /= 2.0
    while bpm < BPM_MIN:
        bpm *= 2.0
    return bpm


def estimar_bpm(y, sr):
    """
    Devuelve (bpm, onset_strength_mean) para un segmento de audio.
    Usa onset_envelope explícita para alimentar feature.tempo, lo que da
    una estimación más precisa que pasar y directamente.
    """
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_mean = float(np.mean(onset_env))
        t = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
        bpm = float(np.atleast_1d(t)[0]) if t is not None else 0.0
    except Exception:
        try:
            t, _ = librosa.beat.beat_track(y=y, sr=sr)
            bpm = float(np.atleast_1d(t)[0])
            onset_mean = 0.0
        except Exception:
            bpm, onset_mean = 0.0, 0.0
    return round(_fold_octava(bpm), 2), onset_mean


# ---------------------------------------------------------------------------
# Paso 1: Curvas completas a 1 valor/segundo (soundfile, una sola pasada)
# ---------------------------------------------------------------------------

def extraer_curvas_completas(filepath):
    """
    Extrae RMS, spectral_flux y spectral_centroid a resolución de 1 seg.
    Usa sf.read (sin remuestrear) para máxima velocidad.

    Retorna (rms_full, onset_full, sc_full, sr_native) — listas de floats.
    """
    data, sr_native = sf.read(filepath)
    y = data.mean(axis=1).astype(np.float32) if data.ndim > 1 else data.astype(np.float32)

    block = int(sr_native)                              # muestras por segundo
    freqs = np.fft.rfftfreq(block, d=1.0 / sr_native)
    n_blocks = (len(y) - block) // block

    rms_full, onset_full, sc_full = [], [], []
    mag_prev = None

    for i in range(n_blocks):
        seg = y[i * block: (i + 1) * block]

        rms_full.append(float(np.sqrt(np.mean(seg ** 2))))

        mag = np.abs(np.fft.rfft(seg))
        mag_sum = mag.sum()
        sc_full.append(float(np.dot(freqs, mag) / mag_sum) if mag_sum > 1e-10 else 0.0)

        # Spectral flux HWR: cambios positivos en el espectro = detección de onset
        onset_full.append(
            float(np.sum(np.maximum(0.0, mag - mag_prev))) if mag_prev is not None else 0.0
        )
        mag_prev = mag

    return rms_full, onset_full, sc_full, int(sr_native)


# ---------------------------------------------------------------------------
# Paso 2: Segmentación estructural por change-point detection
# ---------------------------------------------------------------------------

def detectar_secciones(rms_full, onset_full, sc_full, min_dur=MIN_SECTION_DUR):
    """
    Detecta límites de sección calculando la distancia euclidea entre frames
    consecutivos en el espacio [RMS_z, onset_z, SC_z] y buscando picos
    (puntos de mayor cambio) con separación mínima de min_dur segundos.

    Retorna lista de (t_start_seg, t_end_seg) con valores enteros (= segundos).
    """
    n = len(rms_full)
    if n < 2 * min_dur:
        return [(0, n)]

    def zscore(arr):
        a = np.array(arr, dtype=float)
        s = np.std(a)
        return (a - np.mean(a)) / s if s > 1e-6 else np.zeros_like(a)

    # Distancia euclidea entre frames consecutivos
    delta = np.sqrt(
        np.diff(zscore(rms_full)) ** 2
        + np.diff(zscore(onset_full)) ** 2
        + np.diff(zscore(sc_full)) ** 2
    )

    # Suavizado gaussiano ~10 s (ventana 21 muestras, σ=5)
    win = np.exp(-0.5 * (np.arange(21) - 10) ** 2 / 25.0)
    win /= win.sum()
    delta_s = np.convolve(delta, win, mode="same")

    half = max(1, min_dur // 2)
    threshold = float(np.mean(delta_s) + 0.5 * np.std(delta_s))
    peaks = librosa.util.peak_pick(
        delta_s.astype(float),
        pre_max=half,
        post_max=half,
        pre_avg=min_dur,
        post_avg=min_dur,
        delta=max(0.0, threshold - float(np.mean(delta_s))),
        wait=min_dur,
    )

    boundaries = sorted({0} | {int(p) + 1 for p in peaks} | {n})

    # Fusionar secciones más cortas que min_dur con la anterior
    sections = []
    for i in range(len(boundaries) - 1):
        t0, t1 = boundaries[i], boundaries[i + 1]
        if (t1 - t0) < min_dur and sections:
            sections[-1] = (sections[-1][0], t1)
        else:
            sections.append((t0, t1))

    return sections or [(0, n)]


# ---------------------------------------------------------------------------
# Paso 3: BPM por sección ponderado por onset_strength
# ---------------------------------------------------------------------------

def estimar_bpm_secciones(filepath, secciones_seg):
    """
    Para cada sección carga BPM_SAMPLE_DUR segundos del centro de la sección
    y estima BPM + onset_strength_mean.

    Retorna (bpm_global, bpm_confidence, all_section_data).
    bpm_global = promedio ponderado por onset_strength entre secciones válidas.
    all_section_data tiene la misma longitud que secciones_seg (ceros para
    secciones demasiado cortas o con error).
    """
    bpms_pond, onsets_pond = [], []
    all_data = []

    for t_start, t_end in secciones_seg:
        dur = float(t_end - t_start)
        if dur < MIN_SECTION_DUR:
            all_data.append({"bpm_local": 0.0, "onset_mean": 0.0})
            continue

        sample_dur = min(BPM_SAMPLE_DUR, dur)
        sample_offset = float(t_start) + (dur - sample_dur) / 2.0

        try:
            y, sr = librosa.load(
                filepath, sr=SR_ANALYSIS,
                offset=sample_offset, duration=sample_dur, mono=True
            )
            bpm, onset_mean = estimar_bpm(y, sr)
            all_data.append({
                "bpm_local": round(bpm, 2),
                "onset_mean": round(max(onset_mean, 0.0), 3),
            })
            if bpm > 0:
                bpms_pond.append(bpm)
                onsets_pond.append(max(onset_mean, 1e-6))
        except Exception as e:
            print(f"   ⚠ Error en sección [{t_start:.0f}s–{t_end:.0f}s]: {e}",
                  file=sys.stderr)
            all_data.append({"bpm_local": 0.0, "onset_mean": 0.0})

    if not bpms_pond:
        return 0.0, 0.0, all_data

    bpms_arr = np.array(bpms_pond, dtype=float)
    onsets_arr = np.array(onsets_pond, dtype=float)

    bpm_global = round(
        _fold_octava(float(np.dot(bpms_arr, onsets_arr) / onsets_arr.sum())), 2
    )

    # Auto-corrección de octava: librosa a veces detecta al doble del tempo real en
    # canciones lentas/ambient. Solo corregimos si:
    #   1) El BPM ponderado es ≥ 130 (zona de sospecha de doubling)
    #   2) La señal rítmica es verdaderamente débil (onset < 1.5, no sólo "comprimida")
    #   3) Las secciones concuerdan (cv < 15%) → no es tempo variable, es un error uniforme
    # NOTA: el umbral anterior (onset < 5.0, bpm > 100) era demasiado agresivo y
    # dividía por la mitad canciones como Animals/Iron (104 BPM → 52) porque su
    # producción comprimida tiene onset_strength < 5 aunque sean energéticas.
    cv = float(np.std(bpms_arr) / np.mean(bpms_arr)) if np.mean(bpms_arr) > 0 else 1.0
    if bpm_global >= HALF_BPM_MIN and onsets_arr.max() < HALF_ONSET_THRESHOLD and cv < 0.15:
        bpm_global = round(bpm_global / 2.0, 2)

    # Confianza: intensidad de onset (¿hay beat claro?) + consistencia entre secciones
    onset_conf = float(np.clip(onsets_arr.max() / 20.0, 0.0, 1.0))
    bpm_consist = float(np.clip(1.0 - np.std(bpms_arr) / 50.0, 0.0, 1.0))
    bpm_confidence = round((onset_conf + bpm_consist) / 2.0, 3)

    return bpm_global, bpm_confidence, all_data


# ---------------------------------------------------------------------------
# Paso 4: Alertas de consistencia (monitoreo)
# ---------------------------------------------------------------------------

def generar_alertas(bpm, bpm_confidence, section_data):
    """Detecta inconsistencias en la estimación de BPM y retorna lista de mensajes."""
    alertas = []
    if not section_data:
        return alertas

    onset_means = [s["onset_mean"] for s in section_data if s["onset_mean"] > 0]
    bpm_locals = [s["bpm_local"] for s in section_data if s["bpm_local"] > 0]

    if bpm > 100 and onset_means and max(onset_means) < LOW_ONSET_ALERT:
        alertas.append(
            "⚠️  BPM posiblemente sobreestimado: señal rítmica débil en todas las secciones"
        )
    if bpm_confidence < CONFIDENCE_ALERT:
        alertas.append(
            f"⚠️  BPM de baja confianza ({bpm_confidence:.2f}): considerar revisión manual"
        )
    if len(bpm_locals) > 1 and (max(bpm_locals) - min(bpm_locals)) > 25:
        alertas.append(
            f"ℹ️  Tempo variable: {min(bpm_locals):.0f}–{max(bpm_locals):.0f} BPM por sección"
        )
    return alertas


# ---------------------------------------------------------------------------
# Paso 5: Perfil emocional por sección (Dynamic MER simplificado)
# ---------------------------------------------------------------------------

def construir_perfil_secciones(secciones_seg, rms_full, onset_full, sc_full, section_data):
    """
    Combina los índices de sección con las curvas completas para calcular
    arousal (onset_strength normalizado) y valence (spectral_centroid normalizado)
    por sección — aproximación al Circumplex de Russell sin ML externo.
    """
    rms_arr = np.array(rms_full, dtype=float)
    onset_arr = np.array(onset_full, dtype=float)
    sc_arr = np.array(sc_full, dtype=float)

    onset_max = max(float(onset_arr.max()), 1e-6)
    sc_max = max(float(sc_arr.max()), 1e-6)

    profile = []
    for i, (t_start, t_end) in enumerate(secciones_seg):
        t0, t1 = int(t_start), min(int(t_end), len(rms_arr))
        seg_rms = rms_arr[t0:t1]
        seg_onset = onset_arr[t0:t1]
        seg_sc = sc_arr[t0:t1]

        rms_mean = float(np.mean(seg_rms)) if len(seg_rms) else 0.0
        onset_mean_sec = float(np.mean(seg_onset)) if len(seg_onset) else 0.0
        sc_mean = float(np.mean(seg_sc)) if len(seg_sc) else 0.0

        sd = section_data[i] if i < len(section_data) else {}
        profile.append({
            "t_start": round(float(t_start), 1),
            "t_end": round(float(t_end), 1),
            "duration": round(float(t_end - t_start), 1),
            "bpm_local": sd.get("bpm_local", 0.0),
            "rms_mean": round(rms_mean, 5),
            "onset_mean": round(onset_mean_sec, 3),
            "sc_mean": round(sc_mean, 1),
            # arousal proxy: qué tan energética es la sección relativa al pico de la canción
            "arousal": round(onset_mean_sec / onset_max, 3),
            # valence proxy: cuán brillante es el timbre (más SC = más "positivo" perceptualmente)
            "valence": round(sc_mean / sc_max, 3),
        })
    return profile


# ---------------------------------------------------------------------------
# Paso 6: Puntos de transición óptimos (sección-aware)
# ---------------------------------------------------------------------------

def find_optimal_transition_timestamps(duration, rms_full, sections_seg, num_points=8):
    """
    Selecciona num_points timestamps usando:
      - Límites de sección como puntos primarios (cambios estructurales reales).
      - Valle de energía interno de cada sección como punto secundario.
    Mejor que el espaciado uniforme anterior porque respeta la estructura musical.
    """
    rms_arr = np.array(rms_full, dtype=float)
    points = {0.0}

    if duration < 60:
        return [round(x, 2) for x in
                np.linspace(0.0, max(0.0, duration - 15.0), num_points).tolist()]

    # Límites de sección (excluir los primeros 15s y los últimos 30s)
    for t_start, _ in sections_seg:
        if 15 < t_start < (duration - 30):
            points.add(float(t_start))

    # Valle de energía dentro de cada sección (excluye extremos de la sección)
    for t_start, t_end in sections_seg:
        t0 = int(t_start)
        t1 = min(int(t_end), len(rms_arr))
        sec_len = t1 - t0
        if sec_len < 10:
            continue
        margin = max(5, sec_len // 6)
        inner = rms_arr[t0 + margin: t1 - margin]
        if len(inner) > 0:
            valley = float(t0 + margin + int(np.argmin(inner)))
            if 15 < valley < (duration - 30):
                points.add(valley)

    # Outro (15s antes del final)
    outro_t = max(0.0, duration - 15.0)
    points.add(outro_t)
    points = sorted(points)

    # Rellenar si hay menos de num_points bisectando el hueco más largo
    while len(points) < num_points:
        diffs = [points[i + 1] - points[i] for i in range(len(points) - 1)]
        idx = int(np.argmax(diffs))
        points.insert(idx + 1, points[idx] + diffs[idx] / 2.0)

    return [round(p, 2) for p in points[:num_points]]


# ---------------------------------------------------------------------------
# Extracción de vectores finos por punto de transición (sin cambios vs v1)
# ---------------------------------------------------------------------------

def analyze_segment(filepath, offset, duration, sr=22050):
    """
    Carga un segmento específico y extrae vectores de transición:
    RMS, Chroma, Spectral Centroid y Beat Grid.
    """
    try:
        y, _ = librosa.load(filepath, sr=sr, offset=offset, duration=duration, mono=True)
    except Exception as e:
        print(f"✘ Error cargando segmento en {offset}s: {e}", file=sys.stderr)
        return None

    if len(y) == 0:
        return None

    hop_length_target = int(0.5 * sr)
    frame_length_target = int(1.0 * sr)

    rms = librosa.feature.rms(
        y=y,
        frame_length=min(frame_length_target, len(y)),
        hop_length=min(hop_length_target, len(y))
    )
    rms_list = rms[0].tolist()

    n_fft = min(2048, len(y))
    hop_length_stft = min(512, len(y))

    if len(y) >= n_fft:
        S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_length_stft))
        chroma = librosa.feature.chroma_stft(S=S**2, sr=sr, n_fft=n_fft,
                                              hop_length=hop_length_stft)
        spec_centroid = librosa.feature.spectral_centroid(S=S, sr=sr, n_fft=n_fft,
                                                           hop_length=hop_length_stft)
        factor = int(round((0.5 * sr) / hop_length_stft))
        if factor > 1:
            def downsample(arr, f):
                m, n = arr.shape
                trunc = (n // f) * f
                if trunc == 0:
                    return arr.mean(axis=1, keepdims=True)
                return arr[:, :trunc].reshape(m, n // f, f).mean(axis=2)
            chroma_ds = downsample(chroma, factor)
            spec_centroid_ds = downsample(spec_centroid, factor)
        else:
            chroma_ds = chroma
            spec_centroid_ds = spec_centroid
        chroma_list = chroma_ds.T.tolist()
        spec_centroid_list = spec_centroid_ds[0].tolist()
    else:
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_fft=n_fft,
                                              hop_length=hop_length_stft)
        spec_centroid = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=n_fft,
                                                           hop_length=hop_length_stft)
        chroma_list = chroma.T.tolist()
        spec_centroid_list = spec_centroid[0].tolist()

    try:
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=min(512, len(y)))
        beat_times = (librosa.frames_to_time(beats, sr=sr, hop_length=min(512, len(y)))
                      + offset)
        beat_times_list = beat_times.tolist()
    except Exception:
        beat_times_list = []

    return {
        "rms": rms_list,
        "chroma": chroma_list,
        "spectral_centroid": spec_centroid_list,
        "beats": beat_times_list,
    }


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

def init_db():
    """Inicializa la BD con el schema completo (v2)."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath                TEXT UNIQUE NOT NULL,
            bpm                     REAL NOT NULL,
            bpm_confidence          REAL,
            duration                REAL NOT NULL DEFAULT 0.0,
            intro_rms               TEXT,
            intro_chroma            TEXT,
            intro_spectral_centroid TEXT,
            intro_beats             TEXT,
            outro_rms               TEXT,
            outro_chroma            TEXT,
            outro_spectral_centroid TEXT,
            outro_beats             TEXT,
            transition_points       TEXT,
            rms_full                TEXT,
            onset_full              TEXT,
            sections                TEXT,
            user_cues               TEXT DEFAULT '[]',
            analyzed_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("PRAGMA table_info(songs)")
    existing = {row[1] for row in cur.fetchall()}

    additions = {
        "duration":                 "REAL NOT NULL DEFAULT 0.0",
        "intro_rms":                "TEXT",
        "intro_chroma":             "TEXT",
        "intro_spectral_centroid":  "TEXT",
        "intro_beats":              "TEXT",
        "outro_rms":                "TEXT",
        "outro_chroma":             "TEXT",
        "outro_spectral_centroid":  "TEXT",
        "outro_beats":              "TEXT",
        "transition_points":        "TEXT",
        "rms_full":                 "TEXT",
        "onset_full":               "TEXT",
        "sections":                 "TEXT",
        "bpm_confidence":           "REAL",
        "user_cues":                "TEXT DEFAULT '[]'",
    }
    for col, col_type in additions.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE songs ADD COLUMN {col} {col_type}")

    conn.commit()
    conn.close()


def save_to_db(filepath, analysis):
    """Guarda o actualiza el análisis completo de una canción en la BD."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    intro = analysis.get("intro") or {}
    outro = analysis.get("outro") or {}

    # ON CONFLICT DO UPDATE preserva el id (AUTOINCREMENT) de la fila existente,
    # evitando que re-análisis rompan los song_ids almacenados en playlists.
    cur.execute("""
        INSERT INTO songs (
            filepath, bpm, bpm_confidence, duration,
            intro_rms, intro_chroma, intro_spectral_centroid, intro_beats,
            outro_rms, outro_chroma, outro_spectral_centroid, outro_beats,
            transition_points, rms_full, onset_full, sections, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(filepath) DO UPDATE SET
            bpm=excluded.bpm, bpm_confidence=excluded.bpm_confidence,
            duration=excluded.duration,
            intro_rms=excluded.intro_rms, intro_chroma=excluded.intro_chroma,
            intro_spectral_centroid=excluded.intro_spectral_centroid,
            intro_beats=excluded.intro_beats,
            outro_rms=excluded.outro_rms, outro_chroma=excluded.outro_chroma,
            outro_spectral_centroid=excluded.outro_spectral_centroid,
            outro_beats=excluded.outro_beats,
            transition_points=excluded.transition_points,
            rms_full=excluded.rms_full, onset_full=excluded.onset_full,
            sections=excluded.sections, analyzed_at=excluded.analyzed_at
    """, (
        os.path.abspath(filepath),
        float(analysis["bpm"]),
        float(analysis.get("bpm_confidence", 0.0)),
        float(analysis["duration"]),
        json.dumps(intro.get("rms", [])),
        json.dumps(intro.get("chroma", [])),
        json.dumps(intro.get("spectral_centroid", [])),
        json.dumps(intro.get("beats", [])),
        json.dumps(outro.get("rms", [])),
        json.dumps(outro.get("chroma", [])),
        json.dumps(outro.get("spectral_centroid", [])),
        json.dumps(outro.get("beats", [])),
        json.dumps(analysis.get("transition_points", [])),
        json.dumps(analysis.get("rms_full", [])),
        json.dumps(analysis.get("onset_full", [])),
        json.dumps(analysis.get("sections", [])),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def analyze_song(filepath):
    """
    Analiza una canción en 6 pasos:
      1. Curvas completas a 1 val/seg (soundfile, rápido)
      2. Segmentación estructural (change-point detection)
      3. BPM por sección ponderado por onset_strength
      4. Alertas de consistencia
      5. Puntos de transición óptimos (sección-aware)
      6. Vectores finos de 15 s por punto de transición
    """
    print(f"🔍 Analizando: {filepath}")

    try:
        info = sf.info(filepath)
        duration = info.duration
        print(f"   ℹ Duración: {duration:.2f}s | SR nativo: {info.samplerate} Hz")
    except Exception as e:
        print(f"✘ Error leyendo metadatos: {e}", file=sys.stderr)
        return None

    # --- 1. Curvas completas ---------------------------------------------
    print("   📈 Extrayendo curvas de energía completas (1 val/seg)...")
    try:
        rms_full, onset_full, sc_full, _ = extraer_curvas_completas(filepath)
    except Exception as e:
        print(f"✘ Error extrayendo curvas: {e}", file=sys.stderr)
        return None
    print(f"   ✓ {len(rms_full)} segundos procesados")

    # --- 2. Segmentación estructural ------------------------------------
    print("   🔬 Detectando secciones estructurales...")
    sections_idx = detectar_secciones(rms_full, onset_full, sc_full)
    sections_seg = [(float(s), float(e)) for s, e in sections_idx]
    print(f"   ✓ {len(sections_seg)} sección(es):")
    for i, (s, e) in enumerate(sections_seg):
        print(f"      [{i + 1}] {s:.0f}s – {e:.0f}s  ({e - s:.0f}s)")

    # --- 3. BPM por sección ponderado ----------------------------------
    print("   🎵 Estimando BPM por sección...")
    bpm, bpm_confidence, section_data = estimar_bpm_secciones(filepath, sections_seg)
    print(f"   🎯 BPM global: {bpm:.2f}  (confianza: {bpm_confidence:.2f})")
    for i, sd in enumerate(section_data):
        if sd["bpm_local"] > 0:
            print(f"      Sección {i + 1}: BPM={sd['bpm_local']:.1f}  onset={sd['onset_mean']:.2f}")

    # Fallback si todas las secciones fallaron
    if bpm <= 0:
        print("   ⚠ Fallback: estimando BPM desde el centro de la canción...")
        try:
            offset_fb = max(0.0, (duration - 30.0) / 2.0)
            y_fb, sr_fb = librosa.load(filepath, sr=SR_ANALYSIS, offset=offset_fb,
                                       duration=min(30.0, duration), mono=True)
            bpm, _ = estimar_bpm(y_fb, sr_fb)
        except Exception:
            bpm = 0.0

    # --- 4. Alertas -----------------------------------------------------
    alertas = generar_alertas(bpm, bpm_confidence, section_data)
    for alerta in alertas:
        print(f"   {alerta}")

    # --- 5. Puntos de transición sección-aware -------------------------
    print("   📊 Seleccionando puntos de transición...")
    timestamps = find_optimal_transition_timestamps(
        duration, rms_full, sections_seg, num_points=8
    )
    print(f"   📍 Timestamps: {timestamps}")

    # --- 6. Vectores finos ---------------------------------------------
    transition_points = []
    
    max_rms = max(rms_full) if rms_full else 1e-6
    max_rms = max(float(max_rms), 1e-6)
    
    for i, ts in enumerate(timestamps):
        tipo = ("intro" if i == 0
                else ("outro" if i == len(timestamps) - 1
                      else f"segmento_{i + 1}"))
        print(f"      👉 Vector en {ts:.2f}s ({tipo})...")
        seg_data = analyze_segment(filepath, offset=ts,
                                   duration=min(15.0, duration - ts))
        if seg_data:
            rms_arr = seg_data.get("rms", [])
            rms_mean = float(np.mean(rms_arr)) if rms_arr else 0.0
            energia = round(rms_mean / max_rms, 3)
            energia = float(np.clip(energia, 0.0, 1.0))
            
            # Map energia (0-1) to clase (nivel_1 - nivel_10)
            nivel = max(1, min(10, int(np.ceil(energia * 10))))
            clase = f"nivel_{nivel}"
            
            transition_points.append({
                "timestamp_seg": ts, 
                "tipo": tipo, 
                "energia": energia,
                "clase": clase,
                **seg_data
            })

    if not transition_points:
        return None

    # Perfil emocional por sección (Dynamic MER)
    sections_profile = construir_perfil_secciones(
        sections_seg, rms_full, onset_full, sc_full, section_data
    )

    intro_data = next(
        (pt for pt in transition_points if pt["tipo"] == "intro"),
        transition_points[0]
    )
    outro_data = next(
        (pt for pt in transition_points if pt["tipo"] == "outro"),
        transition_points[-1]
    )

    return {
        "duration": duration,
        "bpm": bpm,
        "bpm_confidence": bpm_confidence,
        "rms_full": rms_full,
        "onset_full": onset_full,
        "sections": sections_profile,
        "intro": intro_data,
        "outro": outro_data,
        "transition_points": transition_points,
        "alertas": alertas,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Analiza un archivo de audio y extrae BPM, secciones y vectores de transición."
    )
    parser.add_argument("file", help="Ruta al archivo de audio (FLAC, MP3, WAV…)")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"✘ Archivo no encontrado: '{args.file}'", file=sys.stderr)
        sys.exit(1)

    init_db()
    analysis = analyze_song(args.file)
    if analysis:
        save_to_db(args.file, analysis)
        print(f"\n💾 Guardado: {args.file}")
        print(f"   • BPM: {analysis['bpm']:.2f}  (confianza: {analysis['bpm_confidence']:.2f})")
        print(f"   • Duración: {analysis['duration']:.2f}s")
        print(f"   • Secciones detectadas: {len(analysis['sections'])}")
        if analysis.get("alertas"):
            print("   • Alertas:")
            for a in analysis["alertas"]:
                print(f"     {a}")
    else:
        print("✘ Análisis fallido.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
