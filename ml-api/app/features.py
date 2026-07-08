from __future__ import annotations


def derive_mood_features(cue_points: list[dict], macro_sections: list[dict], duration: float) -> dict:
    energias = [c.get("energia") for c in cue_points if c.get("energia") is not None]
    arousals = [m.get("arousal") for m in macro_sections if m.get("arousal") is not None]

    energia_mean = sum(energias) / len(energias) if energias else 0.0
    energia_max = max(energias) if energias else 0.0
    arousal_mean = sum(arousals) / len(arousals) if arousals else 0.0

    return {
        "duration": float(duration or 0.0),
        "arousal_mean": round(float(arousal_mean), 4),
        "energia_mean": round(float(energia_mean), 4),
        "energia_max": round(float(energia_max), 4),
    }


FEATURE_NAMES = ["duration", "arousal_mean", "energia_mean", "energia_max"]


def features_to_vector(features: dict) -> list[float]:
    return [features[name] for name in FEATURE_NAMES]
