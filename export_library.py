"""
Exportador del "paquete musical" para el app móvil autónomo.

El celular NO analiza nada (batería mínima): consume estos metadatos YA
calculados por el backend de la PC. Genera `export/library.json` con, por canción:
bpm, duración, artista/título, mood (por BPM) y los puntos de corte clasificados
por energía. Con `--copy` también copia los FLAC a `export/music/`.

Uso:
    python export_library.py            # solo library.json (rápido)
    python export_library.py --copy     # + copia los FLAC (pesado, 2-5 GB)
"""

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

DB_NAME = "music_library.db"
OUT_DIR = "export"


def mood_por_bpm(bpm):
    if bpm >= 125:
        return "accion"      # combate / pelea
    if bpm >= 115:
        return "energia"     # ejercicio
    if bpm >= 95:
        return "enfoque"     # trabajo / estudio
    return "relax"           # calma


def split_title(filename):
    n = os.path.splitext(filename)[0]
    if " - " in n:
        artist, title = n.split(" - ", 1)
        return title.strip(), artist.strip()
    return n.strip(), ""


def main(copy_audio=False):
    if not os.path.exists(DB_NAME):
        print("✘ No existe la base de datos.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, filepath, bpm, duration, transition_points FROM songs ORDER BY id"
    ).fetchall()
    conn.close()

    os.makedirs(OUT_DIR, exist_ok=True)
    music_dir = os.path.join(OUT_DIR, "music")
    if copy_audio:
        os.makedirs(music_dir, exist_ok=True)

    songs = []
    faltan = 0
    copiados = 0
    for r in rows:
        fp = r["filepath"]
        if not os.path.exists(fp):
            faltan += 1
            continue
        base = os.path.basename(fp)
        title, artist = split_title(base)
        bpm = float(r["bpm"] or 0)
        tp = json.loads(r["transition_points"]) if r["transition_points"] else []
        cues = [{
            "t": p.get("timestamp_seg"),
            "energia": p.get("energia"),
            "clase": p.get("clase"),
            "tipo": p.get("tipo"),
        } for p in tp]

        songs.append({
            "id": r["id"],
            "file": base,
            "title": title,
            "artist": artist,
            "bpm": round(bpm, 1),
            "duration": round(float(r["duration"] or 0), 1),
            "mood": mood_por_bpm(bpm),
            "cue_points": cues,
        })

        if copy_audio:
            dst = os.path.join(music_dir, base)
            if not os.path.exists(dst):
                shutil.copy2(fp, dst)
                copiados += 1

    paquete = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(songs),
        "moods": sorted({s["mood"] for s in songs}),
        "songs": songs,
    }

    out_json = os.path.join(OUT_DIR, "library.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(paquete, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(out_json) / 1024
    print(f"✔ {out_json}  ({len(songs)} canciones, {size_kb:.0f} KB)")
    if faltan:
        print(f"  ⚠ {faltan} canciones omitidas (archivo no encontrado en disco).")
    if copy_audio:
        print(f"  🎵 FLAC copiados a {music_dir}/  ({copiados} nuevos)")
    else:
        print("  ℹ Solo metadatos. Para empaquetar los FLAC: python export_library.py --copy")
    print("\n  Transfiere la carpeta 'export/' (library.json + music/) al celular.")
    return 0


if __name__ == "__main__":
    sys.exit(main(copy_audio="--copy" in sys.argv))
