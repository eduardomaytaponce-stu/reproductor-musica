# Dockerfile para la ml-api  (entregable OPCIONAL)
#
# IMPORTANTE — cómo construir:
# La API importa analyzer.py / transition.py / export_library.py, que viven en
# la carpeta PADRE de ml-api/. Por eso el contexto de build debe ser la RAÍZ
# del repositorio, no ml-api/. Desde la raíz del repo:
#
#     docker build -f ml-api/Dockerfile -t ml-api .
#     docker run --rm -p 8123:8123 ml-api
#
# Luego abre http://127.0.0.1:8123/docs

FROM python:3.12-slim

# Librerías de sistema que necesita librosa/soundfile (audio) y sklearn.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsndfile1 ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Instalar dependencias primero (mejor cacheo de capas).
COPY ml-api/requirements.txt /code/ml-api/requirements.txt
RUN pip install --no-cache-dir -r /code/ml-api/requirements.txt

# Copiar el código DSP de la raíz (lo importa app/dsp.py) y el dataset.
COPY analyzer.py transition.py export_library.py /code/
COPY export/library.json /code/export/library.json

# Copiar la API.
COPY ml-api/ /code/ml-api/

# app/dsp.py calcula la raíz del repo como el padre de ml-api/ → aquí /code.
WORKDIR /code/ml-api

EXPOSE 8123
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8123"]
