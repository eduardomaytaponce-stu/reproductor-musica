# Intelligent FLAC Player & DJ Mixer 🎧🤖

Este es un reproductor de música inteligente de alta fidelidad (FLAC, MP3, WAV, etc.) local-first que utiliza procesamiento de señal digital (DSP) en el navegador (Web Audio API) para mezclas suaves y transiciones automáticas, combinado con un Asistente de IA (NLP) local para buscar música según tu estado de ánimo.

---

## Características Principales ✨
- **Motor DSP en Navegador (Web Audio API)**: Realiza transiciones con 4 efectos interactivos de nivel profesional:
  - **Crossfade Suave**: Curva logarítmica de volumen para mantener la energía constante.
  - **Barrido de Filtro (Lowpass Sweep)**: Atenúa progresivamente las frecuencias altas antes del corte.
  - **Freno de Vinilo (Vinyl Brake)**: Simula apagar un tocadiscos desacelerando la velocidad de reproducción.
  - **Eco/Cola de Delay (Echo Tail)**: Envía la señal del outro a una línea de retardo con feedback espacial y corta la señal seca.
- **Detección Automática de Outro**: Detecta cuando faltan 15 segundos para que termine una canción y prepara e inicia de forma asíncrona la transición con la siguiente pista.
- **Adaptación Dinámica de Ritmo (Beatmatching)**: Ajusta la velocidad de reproducción (`playbackRate`) del deck receptor para sincronizar el ritmo si la diferencia de BPM es menor al 8%.
- **Análisis de Audio Optimizado (Sin ffmpeg)**: Extrae BPM y vectores de transición (RMS, Chroma y Centroide Espectral) cargando de forma selectiva trozos específicos del archivo directamente en memoria usando `librosa` y `soundfile`, optimizando el consumo de CPU e I/O de disco.
- **Asistente de Voz y Chat de Ánimo (NLP Local)**: Utiliza `sentence-transformers` locales para mapear descripciones textuales ("quiero entrenar", "pon algo relajante") al tempo (BPM) e intención de la pista mediante similitud semántica.

---

## Estructura del Proyecto 📁
- `main.py`: Servidor backend en **FastAPI** que sirve la interfaz de usuario, endpoints de streaming de audio con soporte de cabeceras HTTP Range y motor de consulta semántica.
- `analyzer.py`: Motor extractor de características musicales (BPM, RMS, Chroma, Beats).
- `scan_library.py`: Utilidad para escanear directorios recursivamente y añadir canciones a la base de datos de SQLite.
- `index.html`: Interfaz web premium con diseño Glassmorphism, degradados vibrantes, visualizador de espectro en tiempo real y chat con el DJ de IA.
- `music_library.db`: Base de datos local SQLite que almacena los metadatos y vectores analizados.

---

## Configuración y Ejecución 🚀

Este proyecto está gestionado mediante `uv` para garantizar la máxima velocidad y aislamiento de dependencias.

### 1. Prerrequisitos
Asegúrate de tener instalado `uv` en tu sistema:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Iniciar el Servidor de Reproducción
Para instalar las dependencias automáticamente y arrancar la aplicación, simplemente ejecuta:
```bash
uv run main.py
```
El servidor se iniciará en [http://127.0.0.1:8000](http://127.0.0.1:8000). Abre este enlace en cualquier navegador web moderno (Chrome/Firefox/Edge).

### 3. Cargar y Escanear tus Canciones 🎵
Tienes dos formas de cargar tus canciones en el reproductor:

#### Opción A: Desde la Interfaz Web (Recomendado)
1. Abre el reproductor en tu navegador: [http://127.0.0.1:8000](http://127.0.0.1:8000)
2. En el panel izquierdo de **Biblioteca FLAC**, ingresa la ruta absoluta de tu carpeta de música (por defecto está configurada como `/home/carloseduardo/Música/`).
3. Haz clic en **Escanear**. La interfaz mostrará un loader y cargará/analizará tus archivos en segundo plano, agregándolos a la lista de reproducción instantáneamente.

#### Opción B: Desde la Terminal
Si deseas escanear una carpeta directamente desde la consola, ejecuta:
```bash
# Escanear hasta 15 canciones de tu directorio de música
uv run scan_library.py "/home/carloseduardo/Música/" --limit 15
```

---

## Lógica de Desarrollo e IA 🧠
- **Fase 1: Extracción de Características (ETL)**:
  - Se estima el BPM global leyendo 30 segundos centrales del audio.
  - Se extraen curvas de RMS, Chroma y Centroides espectrales de los primeros 15s (Intro) y últimos 15s (Outro).
  - Toda la información se almacena en SQLite serializada como JSON.
- **Fase 2: Motor de Decisiones de Transición (`transition.py`)**:
  - Compara la diferencia de BPM. Si es menor al 8%, calcula el factor de ajuste de velocidad (`playbackRate`) del track entrante (B) para sincronizar rítmicamente la fase de los beats.
  - Calcula la similitud coseno entre los perfiles de Chroma del outro de A y el intro de B.
  - Árbol de decisiones DSP:
    - **Crossfade Suave** (`crossfade_suave`): BPM alineables y alta similitud armónica ($>0.75$). Mezcla larga y fluida.
    - **Barrido de Filtro** (`barrido_filtro`): BPM alineables pero disonancia armónica. Se aplica un filtro pasa-bajos progresivo en A para ocultar el choque antes del corte.
    - **Eco / Cola de Delay** (`eco_delay`): Choque de BPM pero armonía compatible. Se aplica eco rítmico en A, cortando el sonido seco para que B entre a su propio tempo.
    - **Freno de Vinilo** (`freno_vinilo`): Choque total de ritmo y acordes. Se desacelera rápidamente el track A a velocidad cero y se dispara B con potencia.
- **Búsqueda Semántica (Mood Agent)**:
  - El chat inteligente procesa la similitud de tus peticiones cruzando embeddings generados en tiempo real contra los metadatos e intención rítmica de tu biblioteca local de manera instantánea y privada.

