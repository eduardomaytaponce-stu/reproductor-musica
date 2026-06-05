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

def init_db():
    """Initializes the SQLite database with the full schema."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT UNIQUE NOT NULL,
            bpm REAL NOT NULL,
            duration REAL NOT NULL DEFAULT 0.0,
            intro_rms TEXT,
            intro_chroma TEXT,
            intro_spectral_centroid TEXT,
            intro_beats TEXT,
            outro_rms TEXT,
            outro_chroma TEXT,
            outro_spectral_centroid TEXT,
            outro_beats TEXT,
            transition_points TEXT,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Check if we need to add the new columns if the table already existed with the old schema
    cursor.execute("PRAGMA table_info(songs)")
    columns = [row[1] for row in cursor.fetchall()]
    
    new_cols = {
        "duration": "REAL NOT NULL DEFAULT 0.0",
        "intro_rms": "TEXT",
        "intro_chroma": "TEXT",
        "intro_spectral_centroid": "TEXT",
        "intro_beats": "TEXT",
        "outro_rms": "TEXT",
        "outro_chroma": "TEXT",
        "outro_spectral_centroid": "TEXT",
        "outro_beats": "TEXT",
        "transition_points": "TEXT"
    }
    
    for col, col_type in new_cols.items():
        if col not in columns:
            cursor.execute(f"ALTER TABLE songs ADD COLUMN {col} {col_type}")
            
    conn.commit()
    conn.close()

def save_to_db(filepath, analysis):
    """Saves or updates the BPM and transition vectors of a song in the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    intro = analysis.get("intro") or {}
    outro = analysis.get("outro") or {}
    
    cursor.execute("""
        INSERT OR REPLACE INTO songs (
            filepath, bpm, duration,
            intro_rms, intro_chroma, intro_spectral_centroid, intro_beats,
            outro_rms, outro_chroma, outro_spectral_centroid, outro_beats,
            transition_points, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        os.path.abspath(filepath),
        float(analysis["bpm"]),
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
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

def analyze_segment(filepath, offset, duration, sr=22050):
    """
    Loads a specific segment of the audio file in memory and extracts transition features:
    RMS energy, Chroma vectors, Spectral Centroid, and Beat Grid.
    """
    try:
        # Load audio segment directly in memory
        y, _ = librosa.load(filepath, sr=sr, offset=offset, duration=duration, mono=True)
    except Exception as e:
        print(f"✘ Error loading audio segment at offset {offset}s: {e}", file=sys.stderr)
        return None
        
    if len(y) == 0:
        return None
        
    # We want a target temporal resolution of 0.5s for database storage
    hop_length_target = int(0.5 * sr)
    frame_length_target = int(1.0 * sr)
    
    # 1. RMS Energy (volume curve)
    rms = librosa.feature.rms(y=y, frame_length=min(frame_length_target, len(y)), hop_length=min(hop_length_target, len(y)))
    rms_list = rms[0].tolist()
    
    # 2 & 3. Chroma & Spectral Centroid - computed with high resolution STFT then averaged
    # to avoid sub-sampling gaps (hop_length > n_fft).
    n_fft = min(2048, len(y))
    hop_length_stft = min(512, len(y))
    
    if len(y) >= n_fft:
        S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_length_stft))
        chroma = librosa.feature.chroma_stft(S=S**2, sr=sr, n_fft=n_fft, hop_length=hop_length_stft)
        spec_centroid = librosa.feature.spectral_centroid(S=S, sr=sr, n_fft=n_fft, hop_length=hop_length_stft)
        
        # Downsample by averaging frames to match the 0.5s resolution
        factor = int(round((0.5 * sr) / hop_length_stft))
        if factor > 1:
            def downsample(arr, f):
                m, n = arr.shape
                truncated_len = (n // f) * f
                if truncated_len == 0:
                    return arr.mean(axis=1, keepdims=True)
                reshaped = arr[:, :truncated_len].reshape(m, n // f, f)
                return reshaped.mean(axis=2)
                
            chroma_ds = downsample(chroma, factor)
            spec_centroid_ds = downsample(spec_centroid, factor)
        else:
            chroma_ds = chroma
            spec_centroid_ds = spec_centroid
            
        chroma_list = chroma_ds.T.tolist()
        spec_centroid_list = spec_centroid_ds[0].tolist()
    else:
        # Fallback for extremely short segments
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_fft=n_fft, hop_length=hop_length_stft)
        spec_centroid = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=n_fft, hop_length=hop_length_stft)
        chroma_list = chroma.T.tolist()
        spec_centroid_list = spec_centroid[0].tolist()
        
    # 4. Beat Grid (timestamps of beats relative to start of song)
    try:
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=min(512, len(y)))
        beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=min(512, len(y))) + offset
        beat_times_list = beat_times.tolist()
    except Exception:
        beat_times_list = []
        
    return {
        "rms": rms_list,
        "chroma": chroma_list,
        "spectral_centroid": spec_centroid_list,
        "beats": beat_times_list
    }

def find_optimal_transition_timestamps(filepath, duration, num_points=8):
    """
    Analiza la energía RMS gruesa de la canción para identificar num_points
    puntos óptimos de transición (valles de energía, intros, climas, etc.).
    Garantiza al menos num_points espaciados de forma coherente.
    Usa sf.read de forma nativa para evitar remuestreos costosos.
    """
    # Siempre incluimos el inicio (intro, 0.0) y el final (outro, dur - 15)
    points = [0.0]
    
    # Si la canción es extremadamente corta, devolvemos puntos interpolados linealmente
    if duration < 60:
        return [round(x, 2) for x in np.linspace(0.0, max(0.0, duration - 15.0), num_points).tolist()]
        
    try:
        # Carga ultra rápida nativa con soundfile (sin remuestrear en Python)
        data, sr_native = sf.read(filepath)
        if len(data.shape) > 1:
            y_coarse = data.mean(axis=1) # Convertir a mono
        else:
            y_coarse = data
            
        # Calcular RMS en bloques de 2 segundos con paso de 1 segundo
        block_size = int(2.0 * sr_native)
        hop_size = int(1.0 * sr_native)
        
        rms_coarse = []
        for start in range(0, len(y_coarse) - block_size, hop_size):
            block = y_coarse[start : start + block_size]
            rms_coarse.append(np.sqrt(np.mean(block**2)))
            
        rms_coarse = np.array(rms_coarse)
        
        # Encontrar valles (mínimos locales) de energía
        # Filtramos para no estar en los extremos (primeros 30s ni últimos 30s)
        min_border = 30
        max_border = len(rms_coarse) - 30
        
        valles = []
        if min_border < max_border:
            for i in range(min_border, max_border):
                vecindario = rms_coarse[max(0, i - 5) : min(len(rms_coarse), i + 6)]
                if rms_coarse[i] == np.min(vecindario):
                    valles.append((float(i), float(rms_coarse[i])))
                    
        # Ordenar valles por menor energía
        valles.sort(key=lambda x: x[1])
        
        # Seleccionar valles que estén separados al menos por 30 segundos
        valles_filtrados = []
        for t, val in valles:
            if all(abs(t - vf[0]) > 30 for vf in valles_filtrados):
                valles_filtrados.append((t, val))
                if len(valles_filtrados) >= (num_points - 2):
                    break
                    
        for vf in valles_filtrados:
            points.append(vf[0])
    except Exception as e:
        print(f"   ⚠️ Error analizando estructura gruesa rápida ({e}). Usando espaciado uniforme.")
        
    # Completar/rellenar hasta tener num_points usando espaciado uniforme
    while len(points) < num_points - 1:
        cand = len(points) * (duration / (num_points - 1))
        if all(abs(cand - p) > 20 for p in points):
            points.append(cand)
        else:
            points.append(points[-1] + 25.0)
            
    # Asegurar el Outro al final
    outro_t = max(0.0, duration - 15.0)
    if all(abs(outro_t - p) > 15 for p in points):
        points.append(outro_t)
    else:
        points.sort()
        points[-1] = outro_t
        
    points = sorted(list(set(points)))
    
    # Si por duplicados el set tiene menos de num_points, rellenar
    while len(points) < num_points:
        diffs = [points[i+1] - points[i] for i in range(len(points)-1)]
        max_idx = np.argmax(diffs)
        new_pt = points[max_idx] + diffs[max_idx] / 2.0
        points.insert(max_idx + 1, new_pt)
        
    return [round(p, 2) for p in points[:num_points]]

def analyze_song(filepath):
    """
    Analyzes the audio file by loading and analyzing specific chunks:
    - 30 seconds from the middle for BPM estimation
    - Detects at least 8 optimal structural transition points (using RMS valleys, intro, outro, breakdown).
    - Extracts full transition vectors for each point.
    """
    print(f"🔍 Analyzing: {filepath}")
    
    try:
        info = sf.info(filepath)
        duration = info.duration
        print(f"   ℹ Duration: {duration:.2f} seconds | Sample Rate: {info.samplerate} Hz")
    except Exception as e:
        print(f"✘ Error reading file metadata: {e}", file=sys.stderr)
        return None
        
    # Calculate BPM using the middle 30 seconds
    bpm_duration = min(30.0, duration)
    bpm_offset = max(0.0, (duration - bpm_duration) / 2.0)
    
    print(f"   ⚡ Estimating BPM from middle segment ({bpm_offset:.1f}s - {bpm_offset + bpm_duration:.1f}s)...")
    try:
        y_bpm, sr_bpm = librosa.load(filepath, sr=22050, offset=bpm_offset, duration=bpm_duration, mono=True)
        tempo, _ = librosa.beat.beat_track(y=y_bpm, sr=sr_bpm)
        if hasattr(tempo, "__len__"):
            bpm = float(tempo[0]) if len(tempo) > 0 else 0.0
        else:
            bpm = float(tempo)
        print(f"   🎯 BPM Estimated: {bpm:.2f}")
    except Exception as e:
        print(f"✘ Error estimating BPM: {e}", file=sys.stderr)
        bpm = 0.0
        
    # Detect 8 optimal transition timestamps
    print("   📊 Finding 8 optimal transition candidate points...")
    timestamps = find_optimal_transition_timestamps(filepath, duration, num_points=8)
    print(f"   📍 Transition timestamps selected: {timestamps}")
    
    transition_points = []
    for i, ts in enumerate(timestamps):
        tipo = "intro" if i == 0 else ("outro" if i == len(timestamps) - 1 else f"segmento_{i+1}")
        print(f"      👉 Analyzing transition point at {ts:.2f}s ({tipo})...")
        seg_data = analyze_segment(filepath, offset=ts, duration=min(15.0, duration - ts))
        if seg_data:
            transition_points.append({
                "timestamp_seg": ts,
                "tipo": tipo,
                **seg_data
            })
            
    if not transition_points:
        return None
        
    # For backward compatibility with schema columns:
    intro_data = next((pt for pt in transition_points if pt["tipo"] == "intro"), transition_points[0])
    outro_data = next((pt for pt in transition_points if pt["tipo"] == "outro"), transition_points[-1])
    
    return {
        "duration": duration,
        "bpm": bpm,
        "intro": intro_data,
        "outro": outro_data,
        "transition_points": transition_points
    }

def main():
    parser = argparse.ArgumentParser(description="Analyze audio files and extract BPM and transition curves.")
    parser.add_argument("file", help="Path to the audio file (FLAC, MP3, WAV, etc.) to analyze.")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"✘ Error: File not found at '{args.file}'", file=sys.stderr)
        sys.exit(1)

    init_db()
    
    analysis = analyze_song(args.file)
    if analysis:
        save_to_db(args.file, analysis)
        print(f"💾 Successfully saved to database: {args.file}")
        print(f"   • BPM: {analysis['bpm']:.2f}")
        print(f"   • Duration: {analysis['duration']:.2f}s")
        print(f"   • Intro RMS Frames: {len(analysis['intro']['rms']) if analysis['intro'] else 0}")
        print(f"   • Outro RMS Frames: {len(analysis['outro']['rms']) if analysis['outro'] else 0}")
    else:
        print("✘ Failed to analyze song.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
