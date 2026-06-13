"""
Enriquecimiento ligero: recalcula los puntos de transición de TODAS las canciones
con energía/clase (ver cue_points.detectar_puntos_energia) y actualiza solo la
columna `transition_points`. No re-extrae los vectores pesados (intro/outro), así
que es rápido (~1-2 s por canción).

Uso:
    python enrich_cues.py            # procesa toda la biblioteca
"""

import json
import os
import sqlite3
import sys

from cue_points import detectar_puntos_energia

DB_NAME = "music_library.db"


def main():
    if not os.path.exists(DB_NAME):
        print("✘ No existe la base de datos.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, filepath, duration FROM songs").fetchall()
    total = len(rows)
    print(f"🔄 Enriqueciendo puntos de transición de {total} canciones...")

    ok = 0
    for i, r in enumerate(rows, 1):
        fp = r["filepath"]
        if not os.path.exists(fp):
            print(f"  [{i}/{total}] ⏭ no existe: {os.path.basename(fp)}")
            continue
        try:
            pts = detectar_puntos_energia(fp, r["duration"], n=8)
            conn.execute("UPDATE songs SET transition_points = ? WHERE id = ?",
                         (json.dumps(pts), r["id"]))
            
            def es_energico(clase):
                if clase == "energico":
                    return True
                if isinstance(clase, str) and clase.startswith("nivel_"):
                    try:
                        return int(clase.split("_")[1]) >= 6
                    except ValueError:
                        pass
                return False
                
            n_en = sum(1 for p in pts if es_energico(p["clase"]))
            print(f"  [{i}/{total}] ✔ {os.path.basename(fp)[:42]:42} "
                  f"{len(pts)} puntos ({n_en} enérgicos)")
            ok += 1
        except Exception as e:
            print(f"  [{i}/{total}] ✘ {os.path.basename(fp)[:42]}: {e}")

    conn.commit()
    conn.close()
    print(f"\n✨ Listo. Actualizadas {ok}/{total} canciones.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
