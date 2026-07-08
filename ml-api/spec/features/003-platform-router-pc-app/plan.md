# Plan — 003

## `schemas.py` (añadir a lo de 002)

```python
class AnalysisResponsePC(AnalysisResponse):
    """Alias explícito de AnalysisResponse — respuesta completa para PC."""
    pass

class AnalysisResponseApp(BaseModel):
    bpm: float
    mood: Literal["relax", "enfoque", "energia", "accion"]
    macroSections: list[MacroSection]

Platform = Literal["pc", "app"]
```

## `router.py`

```python
@router.post("/analyze", response_model=AnalysisResponsePC | AnalysisResponseApp)
async def analyze(file: UploadFile, platform: Platform = Query(...)):
    result = run_dsp_analysis(...)       # una sola vez, igual que en 002
    features = derive_mood_features(result)   # función compartida de 002
    mood_pred = mood_classifier.predict(features)

    if platform == "pc":
        return AnalysisResponsePC(**result, mood_prediction=mood_pred)

    return AnalysisResponseApp(
        bpm=result["bpm"],
        mood=mood_pred.mood,
        macroSections=result["macro_sections"],
    )
```

`response_model` con unión de tipos: FastAPI serializa según el tipo real
devuelto — validar con un test que el `openapi.json` generado documenta
ambos shapes (relevante para que quien consuma el endpoint desde Kotlin/Retrofit
sepa qué esperar).

## Riesgo conocido

Pydantic con `response_model` como unión (`A | B`) a veces requiere
`response_model_exclude_none` o un discriminador explícito para no intentar
forzar el shape incorrecto. Si da problemas, alternativa más simple y explícita:
dos funciones de serialización (`_to_pc()`, `_to_app()`) y `response_model=None`
con retorno manual — más control, menos "magia" de FastAPI, preferible si el
primer enfoque se complica.
