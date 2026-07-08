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


def compute_macro_sections(sections_profile):
    """
    Colapsa las micro-secciones detectadas en 2-3 macro-secciones para mostrar en la UI.
    Criterio: divide donde hay el mayor salto de arousal entre secciones adyacentes.
    Retorna lista de {t_start, t_end, bpm, arousal}.
    """
    if not sections_profile:
        return []
    valid = [s for s in sections_profile if s.get("bpm_local", 0) > 0 or s.get("arousal", 0) > 0]
    if not valid:
        valid = sections_profile
    if len(valid) <= 2:
        return [{"t_start": s["t_start"], "t_end": s["t_end"],
                 "bpm": s.get("bpm_local", 0), "arousal": round(s.get("arousal", 0), 3)}
                for s in valid]

    arousals = [s.get("arousal", 0) for s in valid]

    def group_summary(group):
        bpms = [s.get("bpm_local", 0) for s in group if s.get("bpm_local", 0) > 0]
        avg_bpm = round(sum(bpms) / len(bpms), 1) if bpms else 0.0
        avg_ar = round(sum(s.get("arousal", 0) for s in group) / len(group), 3)
        return {"t_start": round(group[0]["t_start"], 1), "t_end": round(group[-1]["t_end"], 1),
                "bpm": avg_bpm, "arousal": avg_ar}

    # Primer corte: mayor salto de energía entre secciones adyacentes
    jumps = [abs(arousals[i + 1] - arousals[i]) for i in range(len(arousals) - 1)]
    max_jump = max(jumps)
    if max_jump < 0.08:
        # Todas las secciones tienen energía similar → una sola macro-sección
        return [group_summary(valid)]

    cut1 = jumps.index(max_jump)
    group_a = valid[:cut1 + 1]
    group_b = valid[cut1 + 1:]

    # Segundo corte opcional: si hay un salto >0.12 dentro del grupo más largo
    result = [group_summary(group_a), group_summary(group_b)]
    longest = group_a if len(group_a) >= len(group_b) else group_b
    if len(longest) >= 3:
        sub_arousals = [s.get("arousal", 0) for s in longest]
        sub_jumps = [abs(sub_arousals[i + 1] - sub_arousals[i]) for i in range(len(sub_arousals) - 1)]
        second_jump = max(sub_jumps)
        if second_jump > 0.12:
            cut2 = sub_jumps.index(second_jump)
            sub_a = longest[:cut2 + 1]
            sub_b = longest[cut2 + 1:]
            if longest is group_a:
                result = [group_summary(sub_a), group_summary(sub_b), group_summary(group_b)]
            else:
                result = [group_summary(group_a), group_summary(sub_a), group_summary(sub_b)]

    return sorted(result, key=lambda x: x["t_start"])


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
        "SELECT id, filepath, bpm, duration, transition_points, "
        "intro_beats, outro_beats, sections, user_cues FROM songs ORDER BY id"
    ).fetchall()
    conn.close()

    os.makedirs(OUT_DIR, exist_ok=True)
    music_dir = os.path.join(OUT_DIR, "music")
    if copy_audio:
        os.makedirs(music_dir, exist_ok=True)

    # --- Deduplicar por nombre de archivo (la DB tiene filas repetidas) ---
    # Se conserva, para cada archivo, la fila CON puntos de transición (si existe);
    # las demás ids se remapean a la conservada para no romper las playlists.
    mejor_por_base = {}
    for r in rows:
        base = os.path.basename(r["filepath"])
        actual = mejor_por_base.get(base)
        tiene_tp = bool(r["transition_points"])
        if actual is None:
            mejor_por_base[base] = r
        elif tiene_tp and not bool(actual["transition_points"]):
            mejor_por_base[base] = r  # preferir la que trae transiciones
    id_canonico_por_base = {b: r["id"] for b, r in mejor_por_base.items()}
    id_to_canon = {r["id"]: id_canonico_por_base[os.path.basename(r["filepath"])] for r in rows}
    unique_rows = sorted(mejor_por_base.values(), key=lambda r: r["id"])
    duplicados = len(rows) - len(unique_rows)

    songs = []
    faltan = 0
    copiados = 0
    for r in unique_rows:
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

        # Rejillas de beats (timestamps en seg) para el beatmatch del "Modo Pro" del app.
        def _beats(col):
            try:
                return [round(float(x), 3) for x in (json.loads(col) if col else [])]
            except Exception:
                return []

        sections_profile = json.loads(r["sections"]) if r["sections"] else []
        macro_secs = compute_macro_sections(sections_profile)
        user_cues_raw = json.loads(r["user_cues"]) if r["user_cues"] else []
        songs.append({
            "id": r["id"],
            "file": base,
            "title": title,
            "artist": artist,
            "bpm": round(bpm, 1),
            "duration": round(float(r["duration"] or 0), 1),
            "mood": mood_por_bpm(bpm),
            "cue_points": cues,
            "intro_beats": _beats(r["intro_beats"]),
            "outro_beats": _beats(r["outro_beats"]),
            # Secciones globales para display en la app (2-3 macro-secciones)
            "macro_sections": macro_secs,
            # Cue points personalizados por el usuario (anclas con margen protegido)
            "user_cues": user_cues_raw,
        })

        if copy_audio:
            dst = os.path.join(music_dir, base)
            if not os.path.exists(dst):
                shutil.copy2(fp, dst)
                copiados += 1

    # Playlists (con BPM objetivo) para el modo actividad del app móvil.
    playlists = []
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        prows = conn.execute("SELECT name, song_ids, target_bpm FROM playlists ORDER BY id").fetchall()
        conn.close()
        from transition import ordenar_cola_por_tempo
        bpm_por_id = {s["id"]: s["bpm"] for s in songs}
        for p in prows:
            raw_ids = json.loads(p["song_ids"]) if p["song_ids"] else []
            # Remapear ids duplicadas a la conservada y quitar repetidos manteniendo orden.
            vistos, mapeadas = set(), []
            for sid in raw_ids:
                cid = id_to_canon.get(sid, sid)
                if cid not in vistos and cid in bpm_por_id:
                    vistos.add(cid)
                    mapeadas.append(cid)
            # Ordenar por tempo para transiciones consistentes (sin saltos fuerte→alegre).
            items = [{"id": cid, "bpm": bpm_por_id[cid]} for cid in mapeadas]
            ordenadas = [x["id"] for x in ordenar_cola_por_tempo(items)]
            playlists.append({
                "name": p["name"],
                "song_ids": ordenadas,
                "target_bpm": p["target_bpm"],
            })
    except Exception:
        pass

    paquete = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(songs),
        "moods": sorted({s["mood"] for s in songs}),
        "songs": songs,
        "playlists": playlists,
    }

    out_json = os.path.join(OUT_DIR, "library.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(paquete, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(out_json) / 1024
    print(f"✔ {out_json}  ({len(songs)} canciones únicas, {size_kb:.0f} KB)")
    if duplicados:
        print(f"  ✔ {duplicados} duplicados fusionados (playlists remapeadas).")
    if faltan:
        print(f"  ⚠ {faltan} canciones omitidas (archivo no encontrado en disco).")
    if copy_audio:
        print(f"  🎵 FLAC copiados a {music_dir}/  ({copiados} nuevos)")
        print("  ⚠ Esto DUPLICA espacio en disco. Si tu música ya está en el celular,")
        print("    NO uses --copy: basta copiar 'library.json' a la carpeta de tu música.")
    else:
        print("\n  Flujo recomendado (sin duplicar espacio):")
        print(f"    1) Copia SOLO '{out_json}' a la carpeta de música del celular")
        print("       (junto a tus FLAC; la app lo detecta por su nombre).")
        print("    2) En la app: 📁 Carpeta → selecciona esa carpeta.")
    return 0


if __name__ == "__main__":
    sys.exit(main(copy_audio="--copy" in sys.argv))
