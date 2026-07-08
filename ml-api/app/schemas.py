from typing import Literal

from pydantic import BaseModel, Field

Mood = Literal["relax", "enfoque", "energia", "accion"]
Platform = Literal["pc", "app"]


class CuePoint(BaseModel):
    t: float
    energia: float
    clase: str
    tipo: str


class MacroSection(BaseModel):
    t_start: float
    t_end: float
    bpm: float
    arousal: float


class MoodFeatures(BaseModel):
    duration: float = Field(gt=0, description="Duración de la canción en segundos.")
    arousal_mean: float = Field(ge=0, le=1)
    energia_mean: float = Field(ge=0, le=1)
    energia_max: float = Field(ge=0, le=1)


class MoodPrediction(BaseModel):
    mood: Mood
    confianza: float
    probabilidades: dict[str, float]
    tiempo_inferencia_ms: float
    modelo_version: str


class VectorBin(BaseModel):
    t_start: float
    t_end: float
    rms: float
    onset: float
    spectral_centroid: float
    chroma: list[float]


class AnalysisResponsePC(BaseModel):
    bpm: float
    duration: float
    cue_points: list[CuePoint]
    macro_sections: list[MacroSection]
    intro_beats: list[float]
    outro_beats: list[float]
    mood_prediction: MoodPrediction
    vector_track: list[VectorBin]


class AnalysisResponseApp(BaseModel):
    bpm: float
    mood: Mood
    macroSections: list[MacroSection]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    dsp_loaded: bool
    mood_model_loaded: bool
    modelo_version: str
