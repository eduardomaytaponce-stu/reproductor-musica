# Arquitectura y Plan de Implementación: Reproductor FLAC Inteligente

Este documento detalla la arquitectura, tecnologías y estrategia para desarrollar tu reproductor de música FLAC con inteligencia artificial, transiciones inteligentes (crossfading dinámico basado en MASF) e integración biométrica.

---

## 1. Estrategia de Despliegue: ¿Nube (AWS) o WebApp Local?

**Recomendación: WebApp Local (Arquitectura Local-First) para Producción Inicial**
*   **¿Por qué no AWS al inicio?** Los archivos FLAC son muy pesados. Subir una biblioteca de música entera a la nube y luego hacer streaming de FLAC requeriría un ancho de banda masivo y generaría altos costos de almacenamiento (S3) y transferencia de datos. El objetivo es **Costo $0**.
*   **La Solución:** Un backend en **Python (FastAPI)** que corra en tu máquina local, gestionado por `uv`. Este backend servirá una interfaz web (HTML/CSS/JS o React/Next.js) a tu navegador o mediante Electron/Tauri para crear una app de escritorio.
*   **Manejo de FLAC vs Análisis:** Para la reproducción se lee el archivo `.flac` original garantizando máxima fidelidad (usando un motor de audio integrado como `python-vlc` o la API de Web Audio). Para la vectorización (Essentia, MSAF), el backend creará temporalmente una versión `.ogg` o `.mp3` de baja calidad en memoria o en disco temporal. Esto reduce el costo computacional de procesamiento en más de un 80%.

---

## 2. Stack Tecnológico y Repositorios

### Entorno y Backend
*   **Gestor:** `uv` (extremadamente rápido).
*   **Framework API:** `FastAPI` (ligero, asíncrono, ideal para servir audio y manejar websockets para el chat).
*   **Base de Datos (Costo 0):** `SQLite` para metadatos + `ChromaDB` o `FAISS` (en memoria/local) para buscar similitud de vectores de canciones (sentimientos/géneros).

### Procesamiento de Audio (ETL y Transiciones)
*   **Extracción de Features:** [**Essentia**](https://github.com/MTG/essentia) (Python). Es el estándar de la industria desarrollado por el MTG. Extrae BPM, escala, y descriptores de bajo nivel.
*   **Análisis Estructural (Puntos de Transición):** [**MSAF**](https://github.com/urinieto/msaf) (Music Structure Analysis Framework). Ideal para encontrar fronteras (boundaries) y segmentar la canción en al menos 8 partes.
*   **Mood/Sentimientos:** Modelos pre-entrenados del [**Essentia Models Hub**](https://essentia.upf.edu/machine_learning.html) que clasifican emociones (valence/arousal) directamente desde el audio sin costo computacional adicional.

### Inteligencia Artificial (Chat y Clasificación NLP)
*   **Opción Costo 0 (Local):** Usar [**SentenceTransformers**](https://github.com/UKPLab/sentence-transformers) (modelo `all-MiniLM-L6-v2`, pesa solo ~80MB) para convertir descripciones y prompts del chat en vectores y cruzarlos con tu base de datos (ChromaDB).
*   **Opción Cloud (Respaldo):** API de **Groq** (modelos LLaMA 3 gratis y ultrarrápidos) o la capa gratuita de **Gemini API** para extraer palabras clave de descripciones largas si el modelo local no basta.

### Biometría (Smartwatch Xiaomi)
*   **Extracción de Pulso:** Extraer datos en tiempo real de bandas Xiaomi (Mi Band) suele requerir Bluetooth LE. Se puede usar [**Gadgetbridge**](https://github.com/Freeyourgadget/Gadgetbridge) (Android) enviando datos por red local, o un script de Python con [**Bleak**](https://github.com/hbldh/bleak) conectándose al MAC address del reloj para leer el characteristic de Heart Rate cada minuto.

---

## 3. Flujo Lógico de Reproducción y DJ Inteligente

1.  **Ingesta (Una sola vez):** Se agrega un FLAC. Se genera un MP3 temporal. `Essentia` extrae BPM y "Mood". `MSAF` detecta puntos de transición (A, B, C... H). `Transformers` extrae el vector semántico del género/descripción. Se guarda en ChromaDB/SQLite.
2.  **Playlist Inicial:** Basada en BPM, un prompt inicial ("modo enfoque") o la primera canción.
3.  **Algoritmo de Transición:**
    *   La canción A se reproduce en FLAC.
    *   Mientras se reproduce, se planea el salto a la canción B en el punto de transición óptimo detectado (ej. fin del estribillo).
    *   El motor de audio realiza un `crossfade` (2-10s) calculando curvas logarítmicas de volumen para mantener la energía constante.
4.  **Interrupción Interactiva:**
    *   El reloj reporta BPM > 120 (sudor/ejercicio) o el usuario escribe "inicia la pelea".
    *   El NLP asocia esto a "alta energía/épico" y BPM alto.
    *   El sistema busca el punto de transición más cercano en la canción actual (< 3s).
    *   Si lo encuentra, hace el salto a una nueva canción épica. Si no, hace un "enmascaramiento" (efecto de filtro pasa-bajos o eco) y hace el crossfade forzado.

---

## 4. División de Trabajo (Antigravity vs Claude)

Para avanzar rápido y sin errores, dividiremos el trabajo según las fortalezas de cada IA.

### 🧠 Antigravity (Tu compañero en el código, Yo)
**Rol:** Arquitectura, Backend, Integración Local y Entorno.
*   **Qué pedirme:**
    *   *"Inicia el proyecto con `uv` e instala las dependencias base de FastAPI y Essentia."*
    *   *"Crea el script en Python que toma una carpeta de archivos FLAC, usa ffmpeg para bajar la calidad a un tmp y corre Essentia para sacar los BPM."*
    *   *"Configura la base de datos ChromaDB local para guardar los vectores de las canciones."*
    *   *"Escribe el endpoint del backend que reciba el input del chat y busque la canción más similar."*
    *   *"Ayúdame a crear el script Bluetooth con `bleak` para leer la Mi Band."*

### 🎨 Claude (El especialista en lógica profunda y UI)
**Rol:** Algoritmos matemáticos complejos, Diseño Frontend UI/UX, Prompts complejos.
*   **Qué pedirle:**
    *   *"Diséñame un dashboard en HTML/CSS/JS (o React) que se vea premium, vibrante y oscuro para un reproductor de música, con animaciones fluidas."*
    *   *"Escribe la lógica matemática (la función) para calcular el tiempo de crossfade ideal entre dos canciones asumiendo que tengo los datos de MASF de sus puntos de transición."*
    *   *"Ayúdame a afinar el prompt del sistema que le pasaré a un LLM para que entienda que 'estoy triste' debe buscar canciones de 'low valence' y bajar el BPM de la lista."*

---

## 5. Prompts de Desarrollo (Copia y Pega para iniciar)

A continuación, los prompts exactos que debes usar para que construyamos esto paso a paso. No intentes construir todo de una vez.

### Fase 1: Entorno y ETL de Audio (Pídemelo a mí - Antigravity)
> **Prompt:** "Vamos a iniciar el backend del reproductor de música. Usa `uv` para crear un nuevo proyecto Python en este directorio. Luego, escribe un script `analyzer.py` que: 1. Acepte la ruta de un archivo FLAC. 2. Cree una copia comprimida temporal en memoria o en `/tmp`. 3. Use `essentia` (o librosa si essentia es muy pesado de instalar ahora) para extraer los BPM. 4. Guarde el resultado de los BPM y la ruta original del FLAC en una base de datos SQLite. Asegúrate de optimizar los recursos."

### Fase 2: Puntos de Transición MASF (Pídeselo a Claude, luego me traes el código)
> **Prompt (para Claude):** "Actúa como un ingeniero de audio e IA. Necesito integrar MSAF (Music Structure Analysis Framework) en un script de Python. Dada una ruta de un archivo de audio, necesito que escribas una clase en Python que devuelva una lista de al menos 8 'puntos de transición óptimos' (timestamps en segundos). Explícame cómo configurarías los parámetros para detectar fronteras de secciones (estribillo, verso) que sirvan para mezclar canciones (DJing)."

### Fase 3: NLP Local para Etiquetas y Chat (Pídemelo a mí)
> **Prompt:** "Necesitamos el módulo de NLP de costo 0. Crea un script usando `sentence-transformers` (all-MiniLM) y `ChromaDB` local. El script debe tomar una canción (nombre y género), crear un embedding de esas palabras clave y guardarlo. Luego, crea una función que reciba un input del usuario (ej: 'inicia la batalla') e identifique por similitud coseno cuáles son las 5 canciones más cercanas en sentimiento a ese texto."

### Fase 4: Lógica de Reproducción y Crossfading
> **Prompt (para mí o Claude):** "Diseña la máquina de estados de reproducción en Python. Cuando se reproduce la canción A, y faltan 5 segundos para su 'punto de transición', debe dispararse un evento. Si el usuario escribe algo en el chat que cambia el mood (ej: 'relajarse'), ¿cómo interrumpes el flujo para saltar al próximo punto de transición inmediatamente en un tiempo máximo de 3 segundos? Muestra la estructura lógica de este controlador de audio."

### Fase 5: Frontend Premium (Pídeselo a Claude)
> **Prompt (para Claude):** "Eres un diseñador UX/UI experto. Escribe el HTML, Vanilla CSS y JS para la interfaz de mi reproductor de música IA. Requiere un diseño moderno (glassmorphism, modo oscuro, colores vibrantes como un verde neón o violeta). Debe tener: Un visualizador de carátula circular, un slider de progreso, un input de chat para hablar con la IA, y un indicador de las BPM actuales del usuario (leídas del reloj). No uses Tailwind, usa CSS puro con variables. Haz que el botón de play tenga una micro-animación."

### Fase 6: Biometría (Pídemelo a mí)
> **Prompt:** "Escribe un script de prueba de concepto en Python utilizando `bleak` para intentar conectarnos al Heart Rate monitor de una Xiaomi Mi Band (Bluetooth LE). El script debe correr en un hilo secundario, escuchar los latidos por minuto cada 60 segundos, calcular la media y moda, y actualizar una variable global."
