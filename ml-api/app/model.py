import os
import time

import joblib

from app.features import features_to_vector
from app.schemas import MoodPrediction

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "mood_classifier.joblib")
MODEL_VERSION = "1.0.0"


class MoodClassifier:
    version = MODEL_VERSION

    def __init__(self, model_path: str = MODEL_PATH):
        self.pipeline = joblib.load(model_path)

    def predict(self, features: dict) -> MoodPrediction:
        vector = [features_to_vector(features)]
        t0 = time.perf_counter()
        mood = self.pipeline.predict(vector)[0]
        proba = self.pipeline.predict_proba(vector)[0]
        tiempo_ms = (time.perf_counter() - t0) * 1000.0

        classes = self.pipeline.classes_
        probabilidades = {cls: round(float(p), 4) for cls, p in zip(classes, proba)}
        return MoodPrediction(
            mood=mood,
            confianza=round(float(max(proba)), 4),
            probabilidades=probabilidades,
            tiempo_inferencia_ms=round(tiempo_ms, 3),
            modelo_version=MODEL_VERSION,
        )


def dsp_ready() -> bool:
    try:
        from app import dsp  # noqa: F401
        return True
    except Exception:
        return False
