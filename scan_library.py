import os
import sys
import sqlite3
import argparse
from analyzer import analyze_song, save_to_db, init_db

SUPPORTED_EXTENSIONS = ('.flac', '.mp3', '.wav', '.ogg', '.m4a')

# Carpetas que nunca deben indexarse: papeleras y directorios ocultos. Sin este
# filtro se registraban canciones ya borradas (p. ej. .Trash-1000) que luego
# aparecían en la biblioteca y fallaban al reproducirse.
DIRS_EXCLUIDOS = ('.trash', '.trash-1000', '.recycle.bin', '$recycle.bin')


def _dir_indexable(nombre):
    n = nombre.lower()
    return not (n.startswith('.') or n in DIRS_EXCLUIDOS)


def purgar_fantasmas(cursor):
    """
    Borra de la BD las canciones cuyo archivo ya no existe, PERO sólo cuando su
    carpeta contenedora sí existe. Así se limpian los archivos realmente
    borrados sin destruir el registro de un disco externo desconectado (en ese
    caso la carpeta tampoco existe y la fila se conserva).

    Devuelve la lista de rutas eliminadas.
    """
    cursor.execute("SELECT filepath FROM songs")
    fantasmas = []
    for (ruta,) in cursor.fetchall():
        if os.path.exists(ruta):
            continue
        if os.path.isdir(os.path.dirname(ruta)):
            fantasmas.append(ruta)

    if fantasmas:
        cursor.executemany("DELETE FROM songs WHERE filepath = ?",
                           [(p,) for p in fantasmas])
    return fantasmas


def scan_directory(directory_path, limit=1000, reanalyze_all=False):
    if not os.path.isdir(directory_path):
        print(f"✘ Error: Directory not found: {directory_path}", file=sys.stderr)
        return

    print(f"📁 Scanning directory: {directory_path} (limit: {limit} songs)")
    init_db()

    audio_files = []
    for root, dirs, files in os.walk(directory_path):
        dirs[:] = [d for d in dirs if _dir_indexable(d)]
        for file in files:
            if file.lower().endswith(SUPPORTED_EXTENSIONS):
                audio_files.append(os.path.join(root, file))

    total_found = len(audio_files)
    print(f"🎵 Found {total_found} audio files.")

    scanned_paths = {os.path.abspath(f) for f in audio_files}

    conn = sqlite3.connect("music_library.db")
    cursor = conn.cursor()
    cursor.execute("SELECT filepath FROM songs")
    already_analyzed = {row[0] for row in cursor.fetchall()}

    # Eliminar de la BD las canciones que pertenecen a este directorio pero ya no
    # existen en disco. Solo lo hacemos cuando el directorio ES accesible (lo
    # confirmamos porque os.walk() devolvió resultados).
    dir_abs = os.path.abspath(directory_path)
    stale = [p for p in already_analyzed
             if p.startswith(dir_abs) and p not in scanned_paths]
    if stale:
        print(f"🗑 Eliminando {len(stale)} canción(es) borrada(s) del disco:")
        for p in stale:
            print(f"   - {os.path.basename(p)}")
        cursor.executemany("DELETE FROM songs WHERE filepath = ?", [(p,) for p in stale])
        conn.commit()

    # Purga global: limpia también canciones muertas de OTRAS carpetas ya
    # registradas. El filtro `stale` de arriba sólo mira el directorio escaneado,
    # así que sin esto las filas de otras rutas quedaban huérfanas para siempre y
    # colgaban el reproductor al intentar reproducirlas.
    otros_fantasmas = [p for p in purgar_fantasmas(cursor) if p not in set(stale)]
    if otros_fantasmas:
        print(f"🗑 Purga global: {len(otros_fantasmas)} canción(es) muerta(s) de otras carpetas:")
        for p in otros_fantasmas[:10]:
            print(f"   - {p}")
        if len(otros_fantasmas) > 10:
            print(f"   ... y {len(otros_fantasmas) - 10} más")
        conn.commit()
        already_analyzed -= set(otros_fantasmas)

    conn.close()

    print(f"📊 {len(already_analyzed)} songs already in the database.")
    if reanalyze_all:
        print("🔄 --reanalyze-all activo: se re-analizarán todas las canciones existentes.")

    processed_count = 0
    success_count = 0
    fallidas = []

    for filepath in audio_files:
        if processed_count >= limit:
            break

        abs_path = os.path.abspath(filepath)
        if abs_path in already_analyzed and not reanalyze_all:
            print(f"⏭ Skipping already analyzed song: {os.path.basename(filepath)}")
            continue

        processed_count += 1
        label = "Re-analizando" if (abs_path in already_analyzed and reanalyze_all) else "Analizando"
        print(f"\n[Song {processed_count}/{limit}] {label}: {os.path.basename(filepath)}")

        try:
            analysis = analyze_song(abs_path)
            if analysis:
                save_to_db(abs_path, analysis)
                print(f"✔ Guardado: {os.path.basename(filepath)}")
                success_count += 1
            else:
                print(f"✘ Falló el análisis: {os.path.basename(filepath)}")
                fallidas.append(os.path.basename(filepath))
        except Exception as e:
            print(f"✘ Error procesando {filepath}: {e}", file=sys.stderr)
            fallidas.append(os.path.basename(filepath))

    print(f"\n✨ Listo. Procesadas: {processed_count}, exitosas: {success_count}, "
          f"fallidas: {len(fallidas)}.")
    if fallidas:
        print("⚠ Canciones que fallaron y NO están en la biblioteca:")
        for nombre in fallidas:
            print(f"   - {nombre}")

    return {"procesadas": processed_count, "exitosas": success_count, "fallidas": fallidas}


def reanalyze_all_in_db(limit=1000):
    """Re-analiza todas las canciones registradas en la BD (aunque no estén en un directorio)."""
    init_db()

    conn = sqlite3.connect("music_library.db")
    cursor = conn.cursor()
    cursor.execute("SELECT filepath FROM songs ORDER BY id")
    filepaths = [row[0] for row in cursor.fetchall()]
    conn.close()

    print(f"🔄 Re-analizando {len(filepaths)} canciones registradas en la BD...")
    processed_count = 0
    success_count = 0
    missing = 0

    for filepath in filepaths:
        if processed_count >= limit:
            break
        if not os.path.exists(filepath):
            print(f"⚠ Archivo no encontrado, saltando: {filepath}")
            missing += 1
            continue

        processed_count += 1
        print(f"\n[{processed_count}/{min(limit, len(filepaths))}] {os.path.basename(filepath)}")
        try:
            analysis = analyze_song(filepath)
            if analysis:
                save_to_db(filepath, analysis)
                print(f"✔ Guardado")
                success_count += 1
            else:
                print(f"✘ Falló el análisis")
        except Exception as e:
            print(f"✘ Error: {e}", file=sys.stderr)

    print(f"\n✨ Listo. Re-analizadas: {processed_count}, exitosas: {success_count}, "
          f"no encontradas: {missing}.")


def main():
    parser = argparse.ArgumentParser(
        description="Escanea un directorio de audio y extrae características a SQLite."
    )
    parser.add_argument(
        "directory", nargs="?",
        help="Directorio con archivos de audio. Opcional si se usa --reanalyze-db."
    )
    parser.add_argument(
        "--limit", type=int, default=1000,
        help="Máximo de archivos a procesar."
    )
    parser.add_argument(
        "--reanalyze-all", action="store_true",
        help="Re-analiza todas las canciones del directorio, incluyendo las ya registradas."
    )
    parser.add_argument(
        "--reanalyze-db", action="store_true",
        help="Re-analiza TODAS las canciones ya registradas en la BD (sin necesitar directorio)."
    )
    args = parser.parse_args()

    if args.reanalyze_db:
        reanalyze_all_in_db(limit=args.limit)
    elif args.directory:
        scan_directory(args.directory, limit=args.limit, reanalyze_all=args.reanalyze_all)
    else:
        parser.error("Debes indicar un directorio o usar --reanalyze-db.")


if __name__ == "__main__":
    main()
