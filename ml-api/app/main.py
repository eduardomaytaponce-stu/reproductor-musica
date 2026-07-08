from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.model import MoodClassifier, dsp_ready
from app.router import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dsp_loaded = dsp_ready()
    try:
        app.state.mood_classifier = MoodClassifier()
    except Exception as e:
        print(f"No se pudo cargar el clasificador de mood: {e}")
        app.state.mood_classifier = None
    yield


app = FastAPI(title="ml-api", lifespan=lifespan)
app.include_router(router)
