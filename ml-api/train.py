import json
import os
import sys

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from app.features import derive_mood_features, features_to_vector, FEATURE_NAMES

RANDOM_STATE = 42
LIBRARY_JSON = os.path.join(os.path.dirname(__file__), "..", "export", "library.json")
MODEL_OUT = os.path.join(os.path.dirname(__file__), "app", "models", "mood_classifier.joblib")


def load_dataset(path=LIBRARY_JSON):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    X, y = [], []
    for song in data["songs"]:
        feats = derive_mood_features(
            song.get("cue_points", []), song.get("macro_sections", []), song.get("duration", 0.0)
        )
        X.append(features_to_vector(feats))
        y.append(song["mood"])
    return np.array(X, dtype=float), np.array(y)


def build_pipeline():
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", GradientBoostingClassifier(random_state=RANDOM_STATE)),
    ])


def main():
    X, y = load_dataset()
    print(f"Dataset: {len(X)} canciones, features={FEATURE_NAMES}")
    print(f"Distribucion de mood: {dict(zip(*np.unique(y, return_counts=True)))}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )

    baseline = DummyClassifier(strategy="most_frequent", random_state=RANDOM_STATE)
    baseline.fit(X_train, y_train)
    baseline_f1 = f1_score(y_test, baseline.predict(X_test), average="macro", zero_division=0)

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
    model_f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)

    print("\n=== Baseline (clase mayoritaria) ===")
    print(f"F1 macro: {baseline_f1:.3f}")
    print("\n=== GradientBoostingClassifier ===")
    print(classification_report(y_test, y_pred, zero_division=0))
    print(f"F1 macro: {model_f1:.3f}  (baseline: {baseline_f1:.3f})")

    os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
    joblib.dump(pipeline, MODEL_OUT)
    print(f"\nModelo guardado en {MODEL_OUT}")


if __name__ == "__main__":
    main()
