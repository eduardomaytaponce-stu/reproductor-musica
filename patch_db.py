"""
patch_db.py — Parches puntuales a la base de datos.

Paso 1: Retrocompatibilidad — rellena 'energia'/'clase' en transition_points sin ese campo.
Paso 2: Corrige BPMs incorrectamente divididos por la auto-corrección antigua (< 70 BPM
        cuando las secciones individuales muestran valores > 80).
        Usa promedio ponderado por duración de sección, sin el umbral onset problemático.
"""
import sqlite3
import json
import numpy as np

BPM_MIN = 70.0
BPM_MAX = 160.0

DB_NAME = "music_library.db"
conn = sqlite3.connect(DB_NAME)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# ─────────────────────────────────────────────
# Paso 1: energia/clase en transition_points
# ─────────────────────────────────────────────
rows = cur.execute("SELECT id, rms_full, transition_points FROM songs").fetchall()
updated_tp = 0

for row in rows:
    tp_str = row["transition_points"]
    if not tp_str:
        continue
    tp = json.loads(tp_str)

    rms_full_str = row["rms_full"]
    rms_full = json.loads(rms_full_str) if rms_full_str else []
    max_rms = max(rms_full) if rms_full else 1e-6
    max_rms = max(float(max_rms), 1e-6)

    changed = False
    for p in tp:
        if "energia" not in p or p["energia"] is None:
            rms_arr = p.get("rms", [])
            rms_mean = float(np.mean(rms_arr)) if rms_arr else 0.0
            energia = round(float(np.clip(rms_mean / max_rms, 0.0, 1.0)), 3)
            nivel = max(1, min(10, int(np.ceil(energia * 10))))
            p["energia"] = energia
            p["clase"] = f"nivel_{nivel}"
            changed = True

    if changed:
        cur.execute("UPDATE songs SET transition_points = ? WHERE id = ?",
                    (json.dumps(tp), row["id"]))
        updated_tp += 1

# ─────────────────────────────────────────────
# Paso 2: corregir BPMs divididos por mitad
# ─────────────────────────────────────────────
def fold_octava(bpm):
    if not bpm or bpm <= 0:
        return 0.0
    while bpm > BPM_MAX:
        bpm /= 2.0
    while bpm < BPM_MIN:
        bpm *= 2.0
    return bpm


rows_bpm = cur.execute(
    "SELECT id, filepath, bpm, sections FROM songs WHERE sections IS NOT NULL"
).fetchall()
updated_bpm = 0

for row in rows_bpm:
    stored_bpm = float(row["bpm"] or 0)
    # Solo corregir BPMs que parecen haber sido divididos por la mitad
    # (debajo de BPM_MIN y con secciones que muestran valores > stored_bpm * 1.5)
    if stored_bpm >= BPM_MIN:
        continue  # BPM ya en rango normal, no tocar

    sections = json.loads(row["sections"])
    valid_bpms = [(s["bpm_local"], s["t_end"] - s["t_start"])
                  for s in sections
                  if s.get("bpm_local", 0) > 0 and s.get("t_end", 0) > s.get("t_start", 0)]
    if not valid_bpms:
        continue

    total_dur = sum(d for _, d in valid_bpms)
    if total_dur <= 0:
        continue

    # Promedio ponderado por duración (no por onset — evita el bug original)
    weighted_bpm = sum(b * d for b, d in valid_bpms) / total_dur
    corrected = round(fold_octava(weighted_bpm), 2)

    if abs(corrected - stored_bpm) > 5.0:
        cur.execute("UPDATE songs SET bpm = ? WHERE id = ?", (corrected, row["id"]))
        print(f"  BPM corregido: {row['filepath'][-55:]} | {stored_bpm:.1f} → {corrected:.1f}")
        updated_bpm += 1

conn.commit()
conn.close()
print(f"\n✓ Paso 1 (energía): {updated_tp} canciones actualizadas.")
print(f"✓ Paso 2 (BPM):     {updated_bpm} canciones corregidas.")
