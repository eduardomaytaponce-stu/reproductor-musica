import numpy as np

from app.vectorize import VECTOR_BIN_SEG

ARCO_MIN_SEG = 15.0
ARCO_MAX_SEG = 45.0
BANDA_RETORNO_ABS = (0.03, 0.28)
MIN_PROMINENCIA = 0.15

PESO_PROMINENCIA = 0.4
PESO_SUBIDA = 0.3
PESO_BAJADA = 0.2
PESO_DURACION = 0.1


def energia_normalizada(vector_track: list[dict]) -> np.ndarray:
    rms = np.array([b["rms"] for b in vector_track], dtype=float)
    onset = np.array([b["onset"] for b in vector_track], dtype=float)
    rms_n = rms / (rms.max() + 1e-9)
    onset_n = onset / (onset.max() + 1e-9)
    return 0.6 * rms_n + 0.4 * onset_n


def _monotonicidad(energia: np.ndarray, i0: int, i1: int, ascendente: bool) -> float:
    tramo = energia[i0:i1 + 1]
    if len(tramo) < 2:
        return 0.0
    diffs = np.diff(tramo)
    pasos_ok = (diffs >= 0) if ascendente else (diffs <= 0)
    return float(np.mean(pasos_ok))


def _score_candidato(energia: np.ndarray, i_start: int, bin_seg: float) -> dict | None:
    max_bins_arco = int(ARCO_MAX_SEG / bin_seg)
    n = len(energia)

    ventana_pico = energia[i_start:min(i_start + max_bins_arco, n)]
    if len(ventana_pico) < 2:
        return None
    i_peak = i_start + int(np.argmax(ventana_pico))
    if i_peak == i_start:
        return None

    prominencia = float(energia[i_peak] - energia[i_start])
    if prominencia < MIN_PROMINENCIA:
        return None

    nivel_inicio = float(energia[i_start])
    i_end = None
    limite = min(i_start + max_bins_arco, n)
    for i in range(i_peak + 1, limite):
        diff = abs(float(energia[i]) - nivel_inicio)
        if BANDA_RETORNO_ABS[0] <= diff <= BANDA_RETORNO_ABS[1]:
            i_end = i
            break
    if i_end is None:
        return None

    duracion = (i_end - i_start) * bin_seg
    if not (ARCO_MIN_SEG <= duracion <= ARCO_MAX_SEG):
        return None

    subida = _monotonicidad(energia, i_start, i_peak, ascendente=True)
    bajada = _monotonicidad(energia, i_peak, i_end, ascendente=False)
    mid = (ARCO_MIN_SEG + ARCO_MAX_SEG) / 2.0
    half_range = (ARCO_MAX_SEG - ARCO_MIN_SEG) / 2.0
    duracion_score = max(0.0, 1.0 - abs(duracion - mid) / half_range)

    score = (
        PESO_PROMINENCIA * min(prominencia, 1.0)
        + PESO_SUBIDA * subida
        + PESO_BAJADA * bajada
        + PESO_DURACION * duracion_score
    )

    return {
        "t_start": round(i_start * bin_seg, 2),
        "t_peak": round(i_peak * bin_seg, 2),
        "t_end": round(i_end * bin_seg, 2),
        "score": round(float(score), 4),
        "componentes": {
            "prominencia": round(prominencia, 4),
            "subida": round(subida, 4),
            "bajada": round(bajada, 4),
            "duracion_score": round(duracion_score, 4),
            "duracion_seg": round(duracion, 2),
        },
    }


def mejores_puntos_enganche(vector_track: list[dict], top_k: int = 5, bin_seg: float = VECTOR_BIN_SEG) -> list[dict]:
    if len(vector_track) < 3:
        return []
    energia = energia_normalizada(vector_track)
    candidatos = []
    for i in range(len(energia)):
        c = _score_candidato(energia, i, bin_seg)
        if c is not None:
            candidatos.append(c)
    candidatos.sort(key=lambda c: c["score"], reverse=True)
    return candidatos[:top_k]
