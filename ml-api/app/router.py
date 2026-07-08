import os
import tempfile

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile

from app.features import derive_mood_features
from app.model import MODEL_VERSION
from app.schemas import (
    AnalysisResponseApp,
    AnalysisResponsePC,
    HealthResponse,
    MoodFeatures,
    MoodPrediction,
    Platform,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    state = request.app.state
    dsp_loaded = bool(getattr(state, "dsp_loaded", False))
    mood_loaded = getattr(state, "mood_classifier", None) is not None
    status = "ok" if (dsp_loaded and mood_loaded) else "degraded"
    return HealthResponse(
        status=status,
        dsp_loaded=dsp_loaded,
        mood_model_loaded=mood_loaded,
        modelo_version=MODEL_VERSION,
    )


@router.post("/predict", response_model=MoodPrediction)
async def predict(features: MoodFeatures, request: Request):
    mood_classifier = request.app.state.mood_classifier
    if mood_classifier is None:
        raise HTTPException(status_code=503, detail="El modelo no está cargado.")
    return mood_classifier.predict(features.model_dump())


@router.post("/analyze", response_model=AnalysisResponsePC | AnalysisResponseApp)
async def analyze(request: Request, file: UploadFile, platform: Platform = Query(...)):
    state = request.app.state
    if not state.dsp_loaded:
        raise HTTPException(status_code=503, detail="El pipeline DSP no está disponible.")
    if state.mood_classifier is None:
        raise HTTPException(status_code=503, detail="El modelo no está cargado.")

    suffix = os.path.splitext(file.filename or "")[1] or ".audio"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        from app.dsp import run_dsp_analysis
        try:
            result = run_dsp_analysis(tmp_path)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"No se pudo analizar el audio: {e}")

        mood_features = derive_mood_features(
            result["cue_points"], result["macro_sections"], result["duration"]
        )
        mood_pred = state.mood_classifier.predict(mood_features)

        if platform == "pc":
            from app.vectorize import extraer_vector_track
            vector_track = extraer_vector_track(tmp_path)
            return AnalysisResponsePC(**result, mood_prediction=mood_pred, vector_track=vector_track)

        return AnalysisResponseApp(
            bpm=result["bpm"],
            mood=mood_pred.mood,
            macroSections=result["macro_sections"],
        )
    finally:
        os.unlink(tmp_path)


@router.post("/hook-points")
async def hook_points(request: Request, file: UploadFile, top_k: int = Query(5, ge=1, le=20)):
    if not request.app.state.dsp_loaded:
        raise HTTPException(status_code=503, detail="El pipeline DSP no está disponible.")

    suffix = os.path.splitext(file.filename or "")[1] or ".audio"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        from app.hook_scorer import mejores_puntos_enganche
        from app.vectorize import extraer_vector_track
        try:
            vector_track = extraer_vector_track(tmp_path)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"No se pudo vectorizar el audio: {e}")
        return {"puntos_enganche": mejores_puntos_enganche(vector_track, top_k=top_k)}
    finally:
        os.unlink(tmp_path)


@router.post("/mixup-plan")
async def mixup_plan(request: Request, file_a: UploadFile, file_b: UploadFile):
    if not request.app.state.dsp_loaded:
        raise HTTPException(status_code=503, detail="El pipeline DSP no está disponible.")

    def _suffix(f: UploadFile) -> str:
        return os.path.splitext(f.filename or "")[1] or ".audio"

    with tempfile.NamedTemporaryFile(suffix=_suffix(file_a), delete=False) as tmp_a, \
         tempfile.NamedTemporaryFile(suffix=_suffix(file_b), delete=False) as tmp_b:
        tmp_a.write(await file_a.read())
        tmp_b.write(await file_b.read())
        path_a, path_b = tmp_a.name, tmp_b.name

    try:
        from app.mixup_planner import generar_plan
        try:
            return generar_plan(path_a, path_b)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"No se pudo generar el plan: {e}")
    finally:
        os.unlink(path_a)
        os.unlink(path_b)
