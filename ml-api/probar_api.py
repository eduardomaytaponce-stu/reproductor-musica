import sys

import requests

BASE_URL = "http://127.0.0.1:8123"

AYUDA = """Uso:
    python probar_api.py "/ruta/cancion.flac"
    python probar_api.py "/ruta/cancion_A.flac" "/ruta/cancion_B.flac"
    python probar_api.py "/ruta/1.flac" "/ruta/2.flac" "/ruta/3.flac"  (playlist)
"""


def separador(titulo):
    print("\n" + "=" * 70)
    print(f"  {titulo}")
    print("=" * 70)


def revisar_salud():
    separador("1) GET /health")
    r = requests.get(f"{BASE_URL}/health")
    print(f"HTTP {r.status_code}")
    data = r.json()
    print(data)
    return data.get("status") == "ok"


def analizar(ruta_cancion, platform):
    separador(f"2) POST /analyze?platform={platform}")
    with open(ruta_cancion, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/analyze",
            params={"platform": platform},
            files={"file": f},
        )
    print(f"HTTP {r.status_code}")
    if r.status_code != 200:
        print("Error:", r.json())
        return None

    data = r.json()
    if platform == "pc":
        mp = data["mood_prediction"]
        print(f"  BPM: {data['bpm']}  |  Duracion: {data['duration']} s")
        print(f"  Mood (modelo ML): {mp['mood']}  (confianza {mp['confianza']})")
        print(f"  Tiempo de inferencia: {mp['tiempo_inferencia_ms']} ms")
        print(f"  Cue points: {len(data['cue_points'])}  |  Vector track: {len(data['vector_track'])} bins")
    else:
        print(f"  BPM: {data['bpm']}  |  Mood: {data['mood']}")
        print(f"  Macro-secciones: {len(data['macroSections'])}  (respuesta ligera, sin cue_points)")
    return data


def puntos_de_enganche(ruta_cancion):
    separador("3) POST /hook-points")
    with open(ruta_cancion, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/hook-points",
            params={"top_k": 3},
            files={"file": f},
        )
    print(f"HTTP {r.status_code}")
    if r.status_code != 200:
        print("Error:", r.json())
        return
    for i, p in enumerate(r.json()["puntos_enganche"], 1):
        print(f"  #{i}  inicio {p['t_start']}s -> climax {p['t_peak']}s -> fin {p['t_end']}s  (score {p['score']})")


def predecir_mood_directo():
    separador("4) POST /predict (modelo ML sin audio)")
    features = {
        "duration": 210.0,
        "arousal_mean": 0.65,
        "energia_mean": 0.55,
        "energia_max": 0.9,
    }
    print(f"  Features enviadas: {features}")
    r = requests.post(f"{BASE_URL}/predict", json=features)
    print(f"HTTP {r.status_code}")
    print("  Respuesta:", r.json())


def plan_mixup(ruta_a, ruta_b):
    separador(f"5) POST /mixup-plan\n     A = {ruta_a.split('/')[-1]}\n     B = {ruta_b.split('/')[-1]}")
    print("  (tarda ~15-20s: la API carga SOLO estas 2 canciones y las analiza)")
    with open(ruta_a, "rb") as fa, open(ruta_b, "rb") as fb:
        r = requests.post(
            f"{BASE_URL}/mixup-plan",
            files={"file_a": fa, "file_b": fb},
        )
    print(f"HTTP {r.status_code}")
    if r.status_code != 200:
        print("Error:", r.json())
        return
    data = r.json()
    if not data.get("plan_encontrado"):
        print(f"  Sin plan. Razon: {data.get('razon')}")
        return
    t = data["transicion"]
    print(f"  Plan (score {data['score']}):")
    print(f"    Tramo A: {data['tramo_A'][0]}s -> {data['tramo_A'][1]}s")
    print(f"    Transicion: {t['tipo_transicion']}")
    print(f"    Tramo B: {data['tramo_B'][0]}s -> {data['tramo_B'][1]}s")


def main():
    if len(sys.argv) < 2:
        print(AYUDA)
        sys.exit(1)

    canciones = sys.argv[1:]

    try:
        if not revisar_salud():
            print("\nLa API respondio 'degraded'. Revisa que el modelo este entrenado.")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"\nNo pude conectar a {BASE_URL}. Levanta la API primero:")
        print("    uvicorn app.main:app --port 8123")
        sys.exit(1)

    primera = canciones[0]
    analizar(primera, "pc")
    analizar(primera, "app")
    puntos_de_enganche(primera)
    predecir_mood_directo()

    if len(canciones) >= 2:
        for i in range(len(canciones) - 1):
            plan_mixup(canciones[i], canciones[i + 1])
    else:
        print("\n(Pasa 2 o mas canciones para probar /mixup-plan.)")

    print("\nListo. Todos los pedidos terminaron.")


if __name__ == "__main__":
    main()
