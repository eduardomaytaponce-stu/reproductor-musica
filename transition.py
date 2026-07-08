"""
Motor de decisión de transiciones (estilo DJ) para el reproductor inteligente.

Consume los vectores de características que ya extrae `analyzer.py` y guarda la
base SQLite (ver `analyzer.analyze_segment`):

    segmento = {
        "rms":               [float, ...],          # curva de energía  (1 valor / 0.5 s)
        "chroma":            [[12 floats], ...],     # perfil armónico   (T, 12)
        "spectral_centroid": [float, ...],           # brillo tímbrico   (1 valor / 0.5 s)
        "beats":             [float, ...],           # timestamps de beats (s, en la canción completa)
    }

La pieza central es `calcular_transicion_optima`, que decide el tipo de
transición y devuelve los parámetros listos para alimentar al reproductor.
"""

import json
import sqlite3

import numpy as np

DB_NAME = "music_library.db"

# Resolución temporal con la que `analyzer.py` extrae los frames (hop de 0.5 s).
HOP_SEGUNDOS = 0.5

# Umbrales de decisión.
UMBRAL_BPM_RELATIVO = 0.08   # 8 % de diferencia de tempo se considera "alineable"
UMBRAL_ARMONICO = 0.75       # similitud coseno de chroma para considerar acordes compatibles
UMBRAL_ARMONICO_MEDIO = 0.50  # por debajo de esto el choque de acordes es severo


# --------------------------------------------------------------------------- #
# Helpers numéricos
# --------------------------------------------------------------------------- #
def _perfil_chroma(segmento):
    """
    Colapsa la secuencia (T, 12) de chroma en un único perfil tonal de 12 dims.

    Promediar el chroma sobre el segmento da el "centro de gravedad armónico"
    (qué clases de tono dominan: el acorde / tonalidad de la zona de empalme).
    Se normaliza a norma unitaria para que la comparación sea de *forma* y no
    de energía absoluta.
    """
    chroma = np.asarray(segmento.get("chroma", []), dtype=float)
    if chroma.ndim != 2 or chroma.shape[0] == 0:
        return np.zeros(12, dtype=float)

    perfil = chroma.mean(axis=0)
    norma = np.linalg.norm(perfil)
    if norma == 0:
        return np.zeros(12, dtype=float)
    return perfil / norma


def _similitud_coseno(a, b):
    """Similitud coseno entre dos vectores; 0.0 si alguno es nulo."""
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))


def _compatibilidad_tonal_chroma(perfil_a, perfil_b):
    """
    Compara perfiles de chroma evaluando relaciones armónicas en el Círculo de Quintas.
    Retorna la mejor similitud encontrada y la relación armónica detectada.
    """
    if np.linalg.norm(perfil_a) == 0 or np.linalg.norm(perfil_b) == 0:
        return 0.0, "Disonante"
        
    # Rotaciones correspondientes a quintas (7 semitonos) y cuartas (5 semitonos)
    rotaciones_compatibles = {
        0: (1.0, "Tonalidad Idéntica"),
        7: (0.9, "Quinta Justa (Dominante)"),
        5: (0.9, "Cuarta Justa (Subdominante)"),
    }
    
    mejor_score = 0.0
    mejor_relacion = "Disonante"
    mejor_similitud = 0.0
    
    for rot, (peso, nombre) in rotaciones_compatibles.items():
        perfil_b_rotado = np.roll(perfil_b, rot)
        sim = _similitud_coseno(perfil_a, perfil_b_rotado)
        score = sim * peso
        if score > mejor_score:
            mejor_score = score
            mejor_similitud = sim
            mejor_relacion = nombre if sim > UMBRAL_ARMONICO else "Disonante"
            
    return mejor_similitud, mejor_relacion


def _diff_bpm_relativa_octava(bpm_a, bpm_b):
    """
    Diferencia de tempo relativa normalizando octavas (mitad / doble).
    Retorna (diferencia_relativa, factor_octava).
    """
    if bpm_a <= 0 or bpm_b <= 0:
        return float("inf"), 1.0
        
    opciones = [0.5, 1.0, 2.0]
    mejor_diff = float("inf")
    mejor_k = 1.0
    for k in opciones:
        bpm_b_mod = bpm_b * k
        diff = abs(bpm_a - bpm_b_mod) / ((bpm_a + bpm_b_mod) / 2.0)
        if diff < mejor_diff:
            mejor_diff = diff
            mejor_k = k
            
    return mejor_diff, mejor_k


def _duracion_disponible(segmento):
    """Segundos de audio realmente cubiertos por los frames del segmento."""
    n = len(segmento.get("rms", []))
    return n * HOP_SEGUNDOS


def _energia_media(segmento):
    rms = segmento.get("rms", [])
    return float(np.mean(rms)) if rms else 0.0


def _encontrar_cruce_optimo_rms(rms_a, rms_b, dur_max):
    """
    Busca la duración ideal de crossfade (entre 4s y dur_max) evaluando
    la variación de energía combinada para evitar caídas o picos bruscos de volumen.
    """
    n_a = len(rms_a)
    n_b = len(rms_b)
    if n_a < 8 or n_b < 8:
        return min(6.0, dur_max)
        
    # Normalizar energías para comparar formas relativas
    rms_a_norm = np.array(rms_a) / (np.max(rms_a) + 1e-6)
    rms_b_norm = np.array(rms_b) / (np.max(rms_b) + 1e-6)
    
    max_frames = int(dur_max / HOP_SEGUNDOS)
    min_frames = 8  # 4 segundos mínimo
    
    mejor_var = float('inf')
    mejor_dur = 6.0
    
    for frames_cruce in range(min_frames, min(max_frames + 1, n_a, n_b)):
        seg_a = rms_a_norm[-frames_cruce:]
        seg_b = rms_b_norm[:frames_cruce]
        
        # Rampa lineal de mezcla
        rampa_a = np.linspace(1.0, 0.0, frames_cruce)
        rampa_b = np.linspace(0.0, 1.0, frames_cruce)
        
        combinada = (seg_a * rampa_a) + (seg_b * rampa_b)
        std_dev = np.std(combinada)
        
        if std_dev < mejor_var:
            mejor_var = std_dev
            mejor_dur = frames_cruce * HOP_SEGUNDOS
            
    return mejor_dur


# --------------------------------------------------------------------------- #
# Alineación de beats
# --------------------------------------------------------------------------- #
def _alinear_beats(beats_saliente, beats_entrante, bpm_saliente, bpm_entrante, factor_octava=1.0):
    """
    Calcula los parámetros de beatmatching para encajar el track entrante (B)
    sobre el saliente (A).
    """
    bpm_entrante_efectivo = bpm_entrante * factor_octava
    factor_relativo = bpm_saliente / bpm_entrante_efectivo if bpm_entrante_efectivo > 0 else 1.0
    
    # Acotar a un rango seguro de variación de pitch (regla DJ clásica de ±8%)
    dentro_limite = (1.0 - UMBRAL_BPM_RELATIVO) <= factor_relativo <= (1.0 + UMBRAL_BPM_RELATIVO)
    
    # factor_velocidad_B es el factor final de velocidad que aplicaremos
    # al Deck B (no multiplicamos por factor_octava para evitar velocidades extremas como 2x o 0.5x)
    factor_final = factor_relativo if dentro_limite else 1.0
    periodo = 60.0 / bpm_saliente if bpm_saliente > 0 else 0.0

    primer_beat_b = float(beats_entrante[0]) if beats_entrante else 0.0
    preroll_b = primer_beat_b * factor_final

    desfase_residual = (preroll_b % periodo) if periodo > 0 else 0.0
    if periodo > 0 and desfase_residual > periodo / 2.0:
        desfase_residual -= periodo

    return {
        "factor_velocidad_B": round(factor_final, 4),
        "bpm_B_ajustado": round(bpm_entrante * factor_final, 2),
        "periodo_beat_seg": round(periodo, 4),
        "preroll_B_seg": round(preroll_b, 3),
        "desfase_residual_seg": round(desfase_residual, 4),
        "num_beats_saliente": len(beats_saliente),
        "num_beats_entrante": len(beats_entrante),
        "dentro_limite": dentro_limite,
    }


# --------------------------------------------------------------------------- #
# Ordenamiento de cola por tempo (evita saltos fuerte→alegre)
# --------------------------------------------------------------------------- #
def ordenar_cola_por_tempo(items, bpm_key="bpm", arrancar_desde_primero=True):
    """
    Reordena una lista de canciones encadenando BPMs cercanos (octava-aware),
    para que las transiciones sean consistentes y no salten de tempos fuertes
    a alegres de golpe. Greedy de vecino más cercano.

    `items`: lista de dicts; cada uno debe tener `bpm_key`.
    `arrancar_desde_primero`: si True conserva la 1ª canción como apertura;
    si False arranca desde la de menor BPM (rampa ascendente clásica de DJ).

    Devuelve una nueva lista ordenada (no muta la original).
    """
    restantes = [x for x in items if (x.get(bpm_key) or 0) > 0]
    sin_bpm = [x for x in items if (x.get(bpm_key) or 0) <= 0]
    if len(restantes) <= 2:
        return items

    if arrancar_desde_primero:
        orden = [restantes.pop(0)]
    else:
        restantes.sort(key=lambda x: x[bpm_key])
        orden = [restantes.pop(0)]

    while restantes:
        ultimo_bpm = orden[-1][bpm_key]
        mejor_i, mejor_diff = 0, float("inf")
        for i, c in enumerate(restantes):
            diff, _ = _diff_bpm_relativa_octava(ultimo_bpm, c[bpm_key])
            if diff < mejor_diff:
                mejor_diff, mejor_i = diff, i
        orden.append(restantes.pop(mejor_i))

    # Las que no tienen BPM van al final, sin romper la cadena.
    return orden + sin_bpm


# --------------------------------------------------------------------------- #
# Función principal
# --------------------------------------------------------------------------- #
def calcular_transicion_optima(intro_A, outro_B, bpm_A, bpm_B):
    """
    Recomienda la mejor transición entre dos canciones a partir de sus
    vectores de características.

    Nota sobre los argumentos
    -------------------------
    En una mezcla A -> B se empalma el OUTRO de A (lo que termina) con el
    INTRO de B (lo que entra). Conservo tu firma `calcular_transicion_optima`,
    pero internamente trato:
        * `intro_A`  -> segmento SALIENTE (outro de A, lo que se desvanece)
        * `outro_B`  -> segmento ENTRANTE (intro de B, lo que aparece)
    Pasa los segmentos en ese orden (primero el de A, luego el de B).

    Parámetros
    ----------
    intro_A, outro_B : dict
        Dicts con claves "rms", "chroma", "spectral_centroid", "beats"
        (mismo formato que devuelve `analyzer.analyze_segment`).
    bpm_A, bpm_B : float
        Tempo estimado de cada canción.

    Retorna
    -------
    dict  (serializable a JSON con json.dumps) con la recomendación.
    """
    seg_saliente, seg_entrante = intro_A, outro_B

    # --- 1. Compatibilidad de tempo con normalización de octava ----------- #
    diff_rel, factor_octava = _diff_bpm_relativa_octava(bpm_A, bpm_B)
    bpm_compatibles = diff_rel < UMBRAL_BPM_RELATIVO

    # --- 2. Similitud armónica evaluando relaciones del Círculo de Quintas - #
    perfil_a = _perfil_chroma(seg_saliente)
    perfil_b = _perfil_chroma(seg_entrante)
    similitud_armonica, relacion_armonica = _compatibilidad_tonal_chroma(perfil_a, perfil_b)
    acordes_compatibles = similitud_armonica > UMBRAL_ARMONICO

    # --- 3. Beatmatching con límite seguro DJ (±8%) y octavas ------------- #
    alineacion = _alinear_beats(
        seg_saliente.get("beats", []),
        seg_entrante.get("beats", []),
        bpm_A,
        bpm_B,
        factor_octava=factor_octava,
    )
    # Solo se recomienda beatmatch si los BPM son compatibles a nivel relativo
    # y la velocidad requerida no excede el límite seguro.
    beatmatch_viable = bpm_compatibles and alineacion["dentro_limite"]
    alineacion["recomendado"] = bool(beatmatch_viable)

    # Tope de duración disponible
    dur_max = max(1.0, min(_duracion_disponible(seg_saliente),
                           _duracion_disponible(seg_entrante)))

    # --- 4. Árbol de decisión mejorado con curvas de energía ------------- #
    if beatmatch_viable and acordes_compatibles:
        tipo = "crossfade_suave"
        # Duración dinámica basada en la suavidad de las curvas RMS
        duracion = _encontrar_cruce_optimo_rms(
            seg_saliente.get("rms", []),
            seg_entrante.get("rms", []),
            dur_max
        )
        razon = (
            f"BPM compatibles con octava (Δ={diff_rel*100:.1f}%) y armonía compatible "
            f"({relacion_armonica}, cos={similitud_armonica:.2f}): "
            f"cruce óptimo de {duracion}s basado en envolventes de energía."
        )
    elif beatmatch_viable and not acordes_compatibles:
        tipo = "barrido_filtro"
        # Duración acotada para el barrido
        duracion = float(np.clip(0.5 * dur_max, 2.0, 6.0))
        razon = (
            f"BPM compatibles (Δ={diff_rel*100:.1f}%) pero choque armónico "
            f"({relacion_armonica}, cos={similitud_armonica:.2f}): "
            f"barrido de filtro pasa-bajos de {duracion}s para ocultar disonancia."
        )
    elif not beatmatch_viable and similitud_armonica >= UMBRAL_ARMONICO_MEDIO:
        tipo = "eco_delay"
        # Eco para suavizar transición sin sincronía de beats
        duracion = float(np.clip(0.25 * dur_max, 1.5, 4.0))
        razon = (
            f"Tempo incompatible (Δ={diff_rel*100:.1f}%) con armonía aceptable "
            f"({relacion_armonica}, cos={similitud_armonica:.2f}): "
            f"eco de delay de {duracion}s como puente rítmico."
        )
    else:
        tipo = "freno_vinilo"
        # Desaceleración total por choque armónico y rítmico
        duracion = float(np.clip(0.15 * dur_max, 1.0, 2.5))
        razon = (
            f"Tempo incompatible (Δ={diff_rel*100:.1f}%) y disonancia total "
            f"({relacion_armonica}, cos={similitud_armonica:.2f}): "
            f"freno de vinilo rápido de {duracion}s antes del corte seco."
        )

    es_crossfade = tipo == "crossfade_suave"

    # Brillo tímbrico
    sc_a = seg_saliente.get("spectral_centroid", [])
    sc_b = seg_entrante.get("spectral_centroid", [])
    delta_brillo = round(abs(np.mean(sc_a) - np.mean(sc_b)), 1) if sc_a and sc_b else None

    # Normalización del volumen relativo (Loudness)
    rms_a_med = _energia_media(seg_saliente)
    rms_b_med = _energia_media(seg_entrante)
    # Ganancia inicial de B para igualar energía con A
    ganancia_b = round(rms_a_med / (rms_b_med + 1e-6), 2) if rms_a_med > 0 and rms_b_med > 0 else 1.0
    # Limitar ganancia a un rango razonable [0.5, 1.5] para evitar picos
    ganancia_b = float(np.clip(ganancia_b, 0.5, 1.5))

    return {
        "tipo_transicion": tipo,
        "razon": razon,
        "diagnostico": {
            "bpm_A": round(float(bpm_A), 2),
            "bpm_B": round(float(bpm_B), 2),
            "diferencia_bpm_relativa": round(diff_rel, 4) if np.isfinite(diff_rel) else None,
            "factor_octava": float(factor_octava),
            "bpm_compatibles": bool(bpm_compatibles),
            "similitud_armonica": round(similitud_armonica, 4),
            "relacion_armonica": relacion_armonica,
            "acordes_compatibles": bool(acordes_compatibles),
            "delta_brillo_hz": delta_brillo,
        },
        "parametros": {
            "duracion_seg": round(duracion, 2),
            "curva_fundido": "equal_power" if es_crossfade else "exponencial",
            "ganancia_inicio_B": round(ganancia_b, 2),
            "alinear_beats": bool(beatmatch_viable),
        },
        "alineacion_beats": alineacion,
    }


# --------------------------------------------------------------------------- #
# Utilidad: cargar segmentos directamente desde la base SQLite
# --------------------------------------------------------------------------- #
def cargar_segmento_db(song_id, parte, db_name=DB_NAME):
    """
    Devuelve (segmento_dict, bpm) para una canción de la base.
    `parte` debe ser "intro" u "outro".
    """
    if parte not in ("intro", "outro"):
        raise ValueError("parte debe ser 'intro' u 'outro'")

    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        f"""SELECT bpm,
                   {parte}_rms               AS rms,
                   {parte}_chroma            AS chroma,
                   {parte}_spectral_centroid AS spectral_centroid,
                   {parte}_beats             AS beats
            FROM songs WHERE id = ?""",
        (song_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"No existe la canción con id={song_id}")

    segmento = {
        "rms": json.loads(row["rms"]) if row["rms"] else [],
        "chroma": json.loads(row["chroma"]) if row["chroma"] else [],
        "spectral_centroid": json.loads(row["spectral_centroid"]) if row["spectral_centroid"] else [],
        "beats": json.loads(row["beats"]) if row["beats"] else [],
    }
    return segmento, float(row["bpm"])


def cargar_segmento_cercano_db(song_id, current_time, db_name=DB_NAME):
    """
    Busca los transition_points de la canción en la base y devuelve el segmento
    cuyo timestamp esté más cercano al current_time del reproductor.
    """
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT bpm, transition_points FROM songs WHERE id = ?",
        (song_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"No existe la canción con id={song_id}")
        
    bpm = float(row["bpm"])
    tps_json = row["transition_points"]
    if not tps_json:
        return cargar_segmento_db(song_id, "outro", db_name)
        
    tps = json.loads(tps_json)
    if not tps:
        return cargar_segmento_db(song_id, "outro", db_name)
        
    # Encontrar el punto más cercano
    closest_tp = min(tps, key=lambda tp: abs(tp.get("timestamp_seg", 0.0) - current_time))
    
    segmento = {
        "rms": closest_tp.get("rms", []),
        "chroma": closest_tp.get("chroma", []),
        "spectral_centroid": closest_tp.get("spectral_centroid", []),
        "beats": closest_tp.get("beats", []),
        "timestamp_seg": closest_tp.get("timestamp_seg", 0.0)
    }
    
    return segmento, bpm


# --------------------------------------------------------------------------- #
# Demo / CLI
# --------------------------------------------------------------------------- #
def _demo_desde_db(id_a, id_b):
    """Calcula la transición A->B usando el outro de A y el intro de B."""
    outro_a, bpm_a = cargar_segmento_db(id_a, "outro")
    intro_b, bpm_b = cargar_segmento_db(id_b, "intro")
    return calcular_transicion_optima(outro_a, intro_b, bpm_a, bpm_b)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Recomienda la transición óptima entre dos canciones de la base."
    )
    parser.add_argument("id_a", type=int, help="ID de la canción que termina (A).")
    parser.add_argument("id_b", type=int, help="ID de la canción que entra (B).")
    args = parser.parse_args()

    resultado = _demo_desde_db(args.id_a, args.id_b)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
