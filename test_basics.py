"""
Tests de las funciones puras (sin audio ni DAC). Ejecutar:
    python test_basics.py        (o:  uv run python test_basics.py)

Cubre lo crítico que no debe regresar: corrección de octava del BPM, clasificación
de mood, y el motor de decisión de transiciones.
"""

import sys


def _check(nombre, cond):
    estado = "✔" if cond else "✘ FALLA"
    print(f"  {estado}  {nombre}")
    return bool(cond)


def test_fold_octava():
    from analyzer import _fold_octava
    casos = [
        ("199 -> ~99 (×2)", abs(_fold_octava(199) - 99.5) < 0.6),
        ("258 -> ~129", abs(_fold_octava(258) - 129) < 1.0),
        ("161 -> ~80.5", abs(_fold_octava(161) - 80.5) < 0.6),
        ("57 -> 114 (½)", abs(_fold_octava(57) - 114) < 0.6),
        ("99 se mantiene", abs(_fold_octava(99) - 99) < 0.01),
        ("144 se mantiene", abs(_fold_octava(144) - 144) < 0.01),
        ("0 -> 0", _fold_octava(0) == 0),
    ]
    return all(_check(n, c) for n, c in casos)


def test_mood():
    from export_library import mood_por_bpm
    casos = [
        ("143 -> accion", mood_por_bpm(143) == "accion"),
        ("120 -> energia", mood_por_bpm(120) == "energia"),
        ("100 -> enfoque", mood_por_bpm(100) == "enfoque"),
        ("80 -> relax", mood_por_bpm(80) == "relax"),
    ]
    return all(_check(n, c) for n, c in casos)


def test_split_title():
    from export_library import split_title
    t, a = split_title("Adele - Skyfall.flac")
    casos = [
        ("autor/título separados", t == "Skyfall" and a == "Adele"),
        ("sin guion -> sin autor", split_title("Intro.flac") == ("Intro", "")),
    ]
    return all(_check(n, c) for n, c in casos)


def test_transicion():
    import numpy as np
    from transition import calcular_transicion_optima

    def seg(idx, n=30):
        ch = np.zeros((n, 12)); ch[:, idx] = 1.0
        beats = [i * 0.5 for i in range(1, n)]
        return {"rms": [0.3] * n, "chroma": ch.tolist(),
                "spectral_centroid": [2000.0] * n, "beats": beats}

    r1 = calcular_transicion_optima(seg([0, 4, 7]), seg([0, 4, 7]), 120, 122)
    r4 = calcular_transicion_optima(seg([0, 4, 7]), seg([1, 6, 11]), 90, 150)
    casos = [
        ("estructura JSON válida", "tipo_transicion" in r1 and "parametros" in r1),
        ("BPM cercano + misma armonía -> crossfade_suave",
         r1["tipo_transicion"] == "crossfade_suave"),
        ("tipo es uno de los 4 válidos",
         r4["tipo_transicion"] in ("crossfade_suave", "barrido_filtro", "eco_delay", "freno_vinilo")),
        ("duración positiva", r1["parametros"]["duracion_seg"] > 0),
    ]
    return all(_check(n, c) for n, c in casos)


def main():
    suites = [
        ("Corrección de octava del BPM", test_fold_octava),
        ("Clasificación de mood", test_mood),
        ("Parseo autor/título", test_split_title),
        ("Motor de transiciones", test_transicion),
    ]
    ok = True
    for nombre, fn in suites:
        print(f"\n== {nombre} ==")
        try:
            ok = fn() and ok
        except Exception as e:
            print(f"  ✘ EXCEPCIÓN: {e}")
            ok = False
    print("\n" + ("✅ TODOS LOS TESTS PASARON" if ok else "❌ HAY TESTS FALLANDO"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
