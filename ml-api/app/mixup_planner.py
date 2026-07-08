from app.dsp import _REPO_ROOT  # noqa: F401
import analyzer
from transition import calcular_transicion_optima

from app.hook_scorer import energia_normalizada, mejores_puntos_enganche
from app.vectorize import VECTOR_BIN_SEG, extraer_vector_track

UMBRAL_AROUSAL_DIFF = 0.2
MIN_SCORE_COMPATIBILIDAD = 0.35
DURACION_VECTOR_LOCAL = 15.0


def arousal_en(vector_track: list[dict], t: float, bin_seg: float = VECTOR_BIN_SEG) -> float:
    energia = energia_normalizada(vector_track)
    idx = min(int(t // bin_seg), len(energia) - 1)
    return float(energia[max(idx, 0)])


def _vector_local(filepath: str, t: float, hacia_adelante: bool) -> dict | None:
    if hacia_adelante:
        offset, duration = t, DURACION_VECTOR_LOCAL
    else:
        offset = max(0.0, t - DURACION_VECTOR_LOCAL)
        duration = t - offset
    if duration <= 0:
        return None
    return analyzer.analyze_segment(filepath, offset=offset, duration=duration)


def generar_plan(filepath_a: str, filepath_b: str, top_k_candidatos: int = 5) -> dict:
    analisis_a = analyzer.analyze_song(filepath_a)
    analisis_b = analyzer.analyze_song(filepath_b)
    if analisis_a is None or analisis_b is None:
        return {"plan_encontrado": False, "razon": "no se pudo analizar una de las dos canciones"}

    bpm_a, bpm_b = analisis_a["bpm"], analisis_b["bpm"]
    duration_b = analisis_b["duration"]

    vt_a = extraer_vector_track(filepath_a)
    vt_b = extraer_vector_track(filepath_b)

    salidas = mejores_puntos_enganche(vt_a, top_k=top_k_candidatos)
    entradas = mejores_puntos_enganche(vt_b, top_k=top_k_candidatos)

    if not salidas or not entradas:
        return {
            "plan_encontrado": False,
            "razon": "ninguna de las dos canciones tiene un arco de enganche claro",
        }

    pares = []
    for s in salidas:
        arousal_s = arousal_en(vt_a, s["t_end"])
        for e in entradas:
            arousal_e = arousal_en(vt_b, e["t_start"])
            if abs(arousal_s - arousal_e) > UMBRAL_AROUSAL_DIFF:
                continue

            seg_saliente = _vector_local(filepath_a, s["t_end"], hacia_adelante=False)
            seg_entrante = _vector_local(filepath_b, e["t_start"], hacia_adelante=True)
            if not seg_saliente or not seg_entrante:
                continue

            transicion = calcular_transicion_optima(seg_saliente, seg_entrante, bpm_a, bpm_b)
            compat_beats = 1.0 if transicion["parametros"]["alinear_beats"] else 0.5
            score = 0.4 * s["score"] + 0.4 * e["score"] + 0.2 * compat_beats

            if score < MIN_SCORE_COMPATIBILIDAD:
                continue

            pares.append({"salida": s, "entrada": e, "transicion": transicion, "score": round(score, 4)})

    if not pares:
        return {
            "plan_encontrado": False,
            "razon": "ningún par de puntos supera el umbral de compatibilidad de arousal/BPM",
        }

    pares.sort(key=lambda p: p["score"], reverse=True)
    mejor = pares[0]
    return {
        "plan_encontrado": True,
        "tramo_A": [0.0, mejor["salida"]["t_end"]],
        "transicion": mejor["transicion"],
        "tramo_B": [mejor["entrada"]["t_start"], duration_b],
        "score": mejor["score"],
        "alternativas": pares[1:4],
    }
