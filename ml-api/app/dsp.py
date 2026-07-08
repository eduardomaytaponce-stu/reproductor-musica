import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import analyzer
from export_library import compute_macro_sections


def _build_cue_points(transition_points: list[dict]) -> list[dict]:
    return [
        {
            "t": p.get("timestamp_seg"),
            "energia": p.get("energia"),
            "clase": p.get("clase"),
            "tipo": p.get("tipo"),
        }
        for p in transition_points
    ]


def run_dsp_analysis(filepath: str) -> dict:
    analysis = analyzer.analyze_song(filepath)
    if analysis is None:
        raise ValueError(f"El análisis DSP falló para el archivo: {filepath!r}")

    return {
        "bpm": round(float(analysis["bpm"]), 2),
        "duration": round(float(analysis["duration"]), 2),
        "cue_points": _build_cue_points(analysis["transition_points"]),
        "macro_sections": compute_macro_sections(analysis["sections"]),
        "intro_beats": [round(float(x), 3) for x in analysis["intro"].get("beats", [])],
        "outro_beats": [round(float(x), 3) for x in analysis["outro"].get("beats", [])],
    }
