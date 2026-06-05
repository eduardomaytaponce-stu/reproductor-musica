"""
Detección de puntos de transición clasificados por ENERGÍA.

A diferencia del detector antiguo (que solo buscaba valles de baja energía), este
identifica un abanico de puntos —valles (entradas suaves) y picos (entradas
enérgicas)— y etiqueta cada uno con su energía relativa dentro de la canción.

Esto permite, en una transición, elegir el punto de ENTRADA acorde al contexto:
tras una canción fuerte, entrar en una sección enérgica de la siguiente (p.ej. el
solo de Free Bird en el min ~5-7) en lugar de su intro suave.

Salida: lista de dicts compatible con la columna `transition_points`:
    {"timestamp_seg": float, "tipo": str, "energia": float(0-1), "clase": "energico"|"suave"}
Es ligera (sin vectores por punto): el frontend solo usa timestamp/tipo y el motor
DSP usa las columnas intro/outro dedicadas.
"""

import numpy as np
import soundfile as sf

ENERGIA_ALTA = "energico"
ENERGIA_BAJA = "suave"


def detectar_puntos_energia(filepath, duration, n=8):
    """Devuelve hasta `n` puntos de transición con energía relativa y clase."""
    try:
        data, sr = sf.read(filepath)
    except Exception:
        return [{"timestamp_seg": 0.0, "tipo": "intro", "energia": 0.0, "clase": ENERGIA_BAJA}]

    y = data.mean(axis=1) if data.ndim > 1 else data

    # RMS grueso: bloques de 2 s con paso de 1 s (rápido, nativo).
    bs = int(2.0 * sr)
    hop = int(1.0 * sr)
    if len(y) < bs or duration < 30:
        # Canción muy corta: puntos uniformes.
        ts = np.linspace(0.0, max(0.0, duration - 15.0), n)
        return [{"timestamp_seg": round(float(t), 1), "tipo": _tipo(i, n),
                 "energia": 0.5, "clase": ENERGIA_BAJA} for i, t in enumerate(ts)]

    rms = np.array([np.sqrt(np.mean(y[i:i + bs] ** 2))
                    for i in range(0, len(y) - bs, hop)])
    times = np.arange(len(rms)) + 1.0                     # centro de cada bloque (s)
    e = (rms - rms.min()) / (rms.max() - rms.min() + 1e-9)  # energía normalizada 0-1
    med = float(np.median(e))

    # Candidatos: máximos y mínimos locales en ventana de ±6 s.
    W = 6
    picos, valles = [], []
    for i in range(W, len(e) - W):
        win = e[i - W:i + W + 1]
        if e[i] == win.max():
            picos.append((float(times[i]), float(e[i])))
        elif e[i] == win.min():
            valles.append((float(times[i]), float(e[i])))
    picos.sort(key=lambda x: -x[1])      # más enérgicos primero
    valles.sort(key=lambda x: x[1])      # más suaves primero

    sel = [(0.0, float(e[0]))]           # intro siempre
    outro_t = max(0.0, duration - 15.0)

    # Intercalar pico/valle para cubrir todo el rango de energía, separados ≥30 s.
    pool = []
    for k in range(max(len(picos), len(valles))):
        if k < len(picos):
            pool.append(picos[k])
        if k < len(valles):
            pool.append(valles[k])
    for t, en in pool:
        if t < 5 or abs(t - outro_t) < 30:
            continue
        if all(abs(t - s[0]) > 30 for s in sel):
            sel.append((t, en))
        if len(sel) >= n - 1:
            break

    sel.append((outro_t, med))
    sel = sorted(set(sel))

    puntos = []
    for i, (t, en) in enumerate(sel):
        puntos.append({
            "timestamp_seg": round(t, 1),
            "tipo": _tipo(i, len(sel)),
            "energia": round(en, 2),
            "clase": ENERGIA_ALTA if en >= med else ENERGIA_BAJA,
        })
    return puntos


def _tipo(i, total):
    if i == 0:
        return "intro"
    if i == total - 1:
        return "outro"
    return f"segmento_{i + 1}"
