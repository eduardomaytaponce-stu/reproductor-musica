"""
Re-estima el BPM de TODA la biblioteca con el método robusto (feature.tempo + fold
de octava) y actualiza la DB. Corrige los errores de octava de `beat_track`
(p.ej. No One Noticed 199->99, We Are One 99->~128).

Uso: python fix_bpm.py
"""

import os
import sqlite3
import sys

import librosa

from analyzer import estimar_bpm

DB_NAME = "music_library.db"


def main():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, filepath, bpm, duration FROM songs ORDER BY id").fetchall()
    total = len(rows)
    print(f"🔄 Re-estimando BPM de {total} canciones (feature.tempo + fold)...")

    cambios = 0
    for i, r in enumerate(rows, 1):
        fp = r["filepath"]
        if not os.path.exists(fp):
            print(f"  [{i}/{total}] ⏭ {os.path.basename(fp)[:40]} (no existe)")
            continue
        try:
            dur = r["duration"] or 0
            bdur = min(30.0, dur) if dur else 30.0
            boff = max(0.0, (dur - bdur) / 2.0)
            y, sr = librosa.load(fp, sr=22050, offset=boff, duration=bdur, mono=True)
            nuevo = estimar_bpm(y, sr)
            viejo = r["bpm"] or 0
            conn.execute("UPDATE songs SET bpm = ? WHERE id = ?", (nuevo, r["id"]))
            flag = ""
            if abs(nuevo - viejo) >= 8:
                flag = f"  ⚠ {viejo:.0f} -> {nuevo:.0f}"
                cambios += 1
            print(f"  [{i}/{total}] {os.path.basename(fp)[:42]:42} {nuevo:6.1f} BPM{flag}")
        except Exception as e:
            print(f"  [{i}/{total}] ✘ {os.path.basename(fp)[:40]}: {e}")

    conn.commit()
    conn.close()
    print(f"\n✨ Listo. {cambios} canciones con corrección significativa (≥8 BPM).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
