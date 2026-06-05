import os
import re
import sys
import sqlite3
import json
import time
import asyncio
import threading
from fastapi import FastAPI, HTTPException, Request, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

app = FastAPI(title="Intelligent FLAC Player")
DB_NAME = "music_library.db"

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"🔌 WebSocket cliente conectado. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"🔌 WebSocket cliente desconectado. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"⚠️ Error al enviar mensaje WebSocket: {e}")

manager = ConnectionManager()

class VoiceWakeRequest(BaseModel):
    online: bool

class VoiceCommandRequest(BaseModel):
    text: str

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Mantener conexión activa
            data = await websocket.receive_text()
            print(f"📥 WebSocket mensaje recibido: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/voice/wake")
async def voice_wake(req: VoiceWakeRequest):
    """Notifica al frontend que se detectó la frase clave."""
    print("📡 Emitiendo evento 'wake_word_detected' al frontend...")
    await manager.broadcast({"event": "wake_word_detected", "online": req.online})
    return {"status": "ok"}

@app.post("/api/voice/command")
async def voice_command(req: VoiceCommandRequest):
    """Recibe la transcripción del comando de voz local y la envía al frontend."""
    print(f"📡 Emitiendo comando offline '{req.text}' al frontend...")
    await manager.broadcast({"event": "offline_transcription", "text": req.text})
    return {"status": "ok"}

@app.on_event("startup")
def start_voice_assistant():
    if os.environ.get("DISABLE_VOICE_ASSISTANT") == "1":
        print("ℹ️ Asistente de voz desactivado mediante variable de entorno.")
        return
        
    def run():
        time.sleep(3.0)
        try:
            import voice_assistant
            print("🎙️ Iniciando hilo secundario de Asistente de Voz...")
            voice_assistant.main()
        except ImportError as e:
            print("\n" + "="*80)
            print("⚠️  AVISO DE ASISTENTE DE VOZ:")
            print(str(e))
            print("El reproductor web funcionará normalmente sin funciones de voz.")
            print("="*80 + "\n")
        except Exception as e:
            print(f"❌ Error al iniciar el Asistente de Voz: {e}", file=sys.stderr)
            
    threading.Thread(target=run, daemon=True).start()

# Asegurar inicialización y migración automática de la base de datos
from analyzer import init_db
init_db()


def verify_safe_path(filepath: str):
    """
    Ensure the path is safe against directory traversal by:
    1. Making it an absolute path.
    2. Preventing access to critical system folders.
    """
    abs_path = os.path.abspath(filepath)
    # Prevent traversal to system directories
    forbidden_prefixes = ["/etc", "/var", "/sys", "/proc", "/boot", "/root", "/dev"]
    for prefix in forbidden_prefixes:
        if abs_path.startswith(prefix):
            raise PermissionError("Acceso a directorio del sistema no permitido.")
    return abs_path

# Lazy-loaded NLP models
model = None
song_embeddings_cache = {}

def get_model():
    global model
    if model is None:
        print("🤖 Loading sentence-transformers model (all-MiniLM-L6-v2)...")
        from sentence_transformers import SentenceTransformer
        # Use local caching or download
        model = SentenceTransformer("all-MiniLM-L6-v2")
        print("✔ Model loaded successfully!")
    return model

def get_song_embedding(song_id, title, bpm):
    if song_id not in song_embeddings_cache:
        encoder = get_model()
        desc = f"A song titled {title} with a speed of {bpm:.0f} beats per minute."
        if bpm < 95:
            desc += " Relajante, tranquila, suave, melancólica, calmada, ritmo lento, ideal para dormir o descansar."
        elif bpm > 115:
            desc += " Energética, rápida, bailable, alegre, motivadora, activa, ideal para entrenar, bailar o hacer ejercicio."
        else:
            desc += " Tempo moderado, enfocada, balanceada, constante, ideal para estudiar o trabajar."
            
        song_embeddings_cache[song_id] = encoder.encode(desc, convert_to_tensor=True)
    return song_embeddings_cache[song_id]

# Range request streaming support
def get_range_response(file_path: str, range_header: str):
    file_size = os.path.getsize(file_path)
    
    # Parse Range Header
    match = re.match(r'bytes=(\d+)-(\d*)', range_header)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid Range Header")
        
    start = int(match.group(1))
    end = match.group(2)
    end = int(end) if end else file_size - 1
    
    if start >= file_size or end >= file_size:
        raise HTTPException(status_code=416, detail="Requested Range Not Satisfiable")
        
    chunk_size = end - start + 1
    
    def file_iterator():
        with open(file_path, 'rb') as f:
            f.seek(start)
            bytes_left = chunk_size
            while bytes_left > 0:
                chunk = f.read(min(16384, bytes_left))
                if not chunk:
                    break
                bytes_left -= len(chunk)
                yield chunk

    content_type = "audio/mpeg"
    if file_path.lower().endswith(".flac"):
        content_type = "audio/flac"
    elif file_path.lower().endswith(".wav"):
        content_type = "audio/wav"
    elif file_path.lower().endswith(".ogg"):
        content_type = "audio/ogg"
        
    headers = {
        'Content-Range': f'bytes {start}-{end}/{file_size}',
        'Accept-Ranges': 'bytes',
        'Content-Length': str(chunk_size),
    }
    
    return StreamingResponse(file_iterator(), status_code=206, headers=headers, media_type=content_type)

class ScanRequest(BaseModel):
    directory: str
    limit: int = 1000

class SearchRequest(BaseModel):
    query: str

class TransitionRequest(BaseModel):
    song_a_id: int
    song_b_id: int
    current_time_a: float = None

class SmartNextRequest(BaseModel):
    current_song_id: int
    played_history: list[int] = []

class HiFiPlayRequest(BaseModel):
    song_id: int
    crossfade: float = 0.0     # segundos de fundido; 0 = corte/selección directa
    entry_offset: float = 0.0  # segundos donde ENTRA la pista (sección enérgica)

class HiFiSeekRequest(BaseModel):
    seconds: float

# --------------------------------------------------------------------------- #
# Motor de reproducción BIT-PERFECT (mpv -> ALSA exclusivo en el DAC)
# Singleton perezoso: una sola instancia de mpv viva, controlada por IPC.
# --------------------------------------------------------------------------- #
_hifi_engine = None

def get_hifi_engine():
    global _hifi_engine
    if _hifi_engine is None:
        from player_engine import AplayHiFiEngine
        _hifi_engine = AplayHiFiEngine()
        _hifi_engine.start()
    return _hifi_engine

def _song_filepath(song_id: int) -> str:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT filepath FROM songs WHERE id = ?", (song_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Canción id={song_id} no encontrada")
    return row[0]

@app.on_event("shutdown")
def _shutdown_hifi():
    global _hifi_engine
    if _hifi_engine is not None:
        _hifi_engine.close()
        _hifi_engine = None

@app.get("/")
def read_root():
    return FileResponse("index.html")

@app.get("/api/songs")
def list_songs():
    if not os.path.exists(DB_NAME):
        return []
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, filepath, bpm, duration, 
               intro_rms, intro_chroma, intro_spectral_centroid, intro_beats,
               outro_rms, outro_chroma, outro_spectral_centroid, outro_beats,
               transition_points
        FROM songs
    """)
    rows = cursor.fetchall()
    conn.close()
    
    songs_list = []
    for r in rows:
        try:
            tp_raw = r["transition_points"]
            transition_points = json.loads(tp_raw) if tp_raw else []
        except Exception:
            transition_points = []
            
        songs_list.append({
            "id": r["id"],
            "title": os.path.basename(r["filepath"]),
            "filepath": r["filepath"],
            "bpm": r["bpm"],
            "duration": r["duration"],
            "intro": {
                "rms": json.loads(r["intro_rms"]) if r["intro_rms"] else [],
                "chroma": json.loads(r["intro_chroma"]) if r["intro_chroma"] else [],
                "spectral_centroid": json.loads(r["intro_spectral_centroid"]) if r["intro_spectral_centroid"] else [],
                "beats": json.loads(r["intro_beats"]) if r["intro_beats"] else []
            },
            "outro": {
                "rms": json.loads(r["outro_rms"]) if r["outro_rms"] else [],
                "chroma": json.loads(r["outro_chroma"]) if r["outro_chroma"] else [],
                "spectral_centroid": json.loads(r["outro_spectral_centroid"]) if r["outro_spectral_centroid"] else [],
                "beats": json.loads(r["outro_beats"]) if r["outro_beats"] else []
            },
            "transition_points": transition_points
        })
    return songs_list

@app.get("/api/stream/{song_id}")
def stream_song(song_id: int, request: Request):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT filepath FROM songs WHERE id = ?", (song_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Song not found")
        
    filepath = row[0]
    try:
        filepath = verify_safe_path(filepath)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"File not found on system: {filepath}")
        
    content_type = "audio/mpeg"
    if filepath.lower().endswith(".flac"):
        content_type = "audio/flac"
    elif filepath.lower().endswith(".wav"):
        content_type = "audio/wav"
        
    return FileResponse(filepath, media_type=content_type)

@app.post("/api/scan")
def scan_library(req: ScanRequest):
    from scan_library import scan_directory
    try:
        safe_dir = verify_safe_path(req.directory)
        scan_directory(safe_dir, limit=req.limit)
        return {"status": "success", "message": f"Successfully scanned {safe_dir}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hifi/play")
def hifi_play(req: HiFiPlayRequest):
    """Reproduce una canción bit-perfect por el DAC (modo exclusivo)."""
    filepath = verify_safe_path(_song_filepath(req.song_id))
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {filepath}")
    try:
        engine = get_hifi_engine()
        engine.load(filepath, crossfade=req.crossfade, entry_offset=req.entry_offset)
        return {"status": "playing", "song_id": req.song_id,
                "crossfade": req.crossfade, "entry_offset": req.entry_offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Motor Hi-Fi: {e}")

@app.post("/api/hifi/pause")
def hifi_pause():
    get_hifi_engine().pause()
    return {"status": "paused"}

@app.post("/api/hifi/resume")
def hifi_resume():
    get_hifi_engine().resume()
    return {"status": "playing"}

@app.post("/api/hifi/seek")
def hifi_seek(req: HiFiSeekRequest):
    get_hifi_engine().seek(req.seconds)
    return {"status": "ok", "seconds": req.seconds}

@app.post("/api/hifi/stop")
def hifi_stop():
    # release_device libera el DAC y lo devuelve a PipeWire de forma síncrona
    # (necesario para que el modo DJ / otras apps tengan sonido al instante).
    get_hifi_engine().release_device()
    return {"status": "stopped"}

@app.get("/api/hifi/status")
def hifi_status():
    """Estado de reproducción + prueba de bit-perfect (frecuencia nativa vs. enviada al DAC)."""
    engine = get_hifi_engine()
    status = engine.status()
    chain = engine.audio_chain()
    decoded = chain.get("decoded") or {}
    output = chain.get("output") or {}
    status["audio"] = {
        "samplerate_nativo": decoded.get("samplerate"),
        "samplerate_dac": output.get("samplerate"),
        "formato_dac": output.get("format"),
        "bit_perfect": bool(output.get("samplerate")
                            and decoded.get("samplerate") == output.get("samplerate")),
        "exclusivo": chain.get("exclusive"),
    }
    return status

@app.post("/api/transition")
def get_transition(req: TransitionRequest):
    from transition import cargar_segmento_db, calcular_transicion_optima, cargar_segmento_cercano_db
    try:
        # Cargar segmento de A (si hay tiempo actual, buscar punto más cercano; si no, el outro por defecto)
        if req.current_time_a is not None:
            outro_a, bpm_a = cargar_segmento_cercano_db(req.song_a_id, req.current_time_a)
        else:
            outro_a, bpm_a = cargar_segmento_db(req.song_a_id, "outro")
            
        # Cargar segmento del intro de B (canción entrante)
        intro_b, bpm_b = cargar_segmento_db(req.song_b_id, "intro")
        
        # Calcular transición óptima
        resultado = calcular_transicion_optima(outro_a, intro_b, bpm_a, bpm_b)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/songs/smart_next")
def get_smart_next_song(req: SmartNextRequest):
    songs = list_songs()
    if not songs:
        raise HTTPException(status_code=404, detail="No songs found")
        
    current = next((s for s in songs if s["id"] == req.current_song_id), None)
    if not current:
        candidates = [s for s in songs if s["id"] not in req.played_history]
        if not candidates:
            return songs[0]
        return candidates[0]
        
    candidates = [s for s in songs if s["id"] != current["id"] and s["id"] not in req.played_history]
    if not candidates:
        candidates = [s for s in songs if s["id"] != current["id"]]
    if not candidates:
        return current
        
    from transition import cargar_segmento_db, _diff_bpm_relativa_octava, _compatibilidad_tonal_chroma, _perfil_chroma
    
    try:
        current_outro, bpm_a = cargar_segmento_db(current["id"], "outro")
        perfil_chroma_a = _perfil_chroma(current_outro)
    except Exception:
        perfil_chroma_a = None
        bpm_a = current["bpm"]
        
    from sentence_transformers import util
    encoder = get_model()
    current_emb = get_song_embedding(current["id"], current["title"], current["bpm"])
    
    best_candidate = None
    best_score = -999.0
    
    for s in candidates:
        # 1. Similitud semántica de embeddings (Género/Mood/Título) -> peso 0.5
        s_emb = get_song_embedding(s["id"], s["title"], s["bpm"])
        sem_sim = float(util.cos_sim(current_emb, s_emb)[0][0])
        
        # 2. Similitud de tempo (BPM) con normalización de octava -> peso 0.3
        mejor_diff, _ = _diff_bpm_relativa_octava(bpm_a, s["bpm"])
        bpm_score = max(0.0, 1.0 - (mejor_diff / 0.5))
        
        # 3. Similitud Armónica (Chroma) -> peso 0.2
        arm_score = 0.5
        if perfil_chroma_a is not None:
            try:
                s_intro, _ = cargar_segmento_db(s["id"], "intro")
                perfil_chroma_b = _perfil_chroma(s_intro)
                sim_chroma, _ = _compatibilidad_tonal_chroma(perfil_chroma_a, perfil_chroma_b)
                arm_score = sim_chroma
            except Exception:
                pass
                
        # Puntuación final combinada
        score = (sem_sim * 0.5) + (bpm_score * 0.3) + (arm_score * 0.2)
        
        if score > best_score:
            best_score = score
            best_candidate = s
            
    return best_candidate

@app.post("/api/search")
def search_song(req: SearchRequest):
    songs = list_songs()
    if not songs:
        return {"matched_song_id": None, "reply": "No hay canciones cargadas en la biblioteca todavía. Por favor, pulsa en Escanear primero."}
        
    query_lower = req.query.lower()
    
    # 1. Try semantic search first
    try:
        from sentence_transformers import util
        import torch
        
        encoder = get_model()
        query_emb = encoder.encode(req.query, convert_to_tensor=True)
        
        best_song = None
        best_score = -1.0
        
        for s in songs:
            song_emb = get_song_embedding(s["id"], s["title"], s["bpm"])
            score = float(util.cos_sim(query_emb, song_emb)[0][0])
            if score > best_score:
                best_score = score
                best_song = s
                
        if best_song and best_score > 0.38:
            bpm_desc = "rápido" if best_song["bpm"] > 115 else ("lento" if best_song["bpm"] < 95 else "moderado")
            reply = f"🎧 He encontrado la pista perfecta: **{best_song['title']}** ({best_song['bpm']:.0f} BPM). Se adapta bien a tu descripción y tiene un ritmo {bpm_desc}. ¡Iniciando la mezcla!"
            return {"matched_song_id": best_song["id"], "reply": reply}
    except Exception as e:
        print(f"⚠️ Semantic search fallback to keywords: {e}", file=sys.stderr)

    # 2. Keywords fallback
    MOOD_KEYWORDS = {
        "relaj": ("low_bpm", "bajar revoluciones, ideal para calmar el ritmo."),
        "calm": ("low_bpm", "un ambiente tranquilo y relajado."),
        "dormir": ("low_bpm", "ritmo lento, perfecto para descansar."),
        "triste": ("low_bpm", "tonos melancólicos y suaves."),
        "melan": ("low_bpm", "melancolía pura, ritmo calmado."),
        "enfoque": ("mid_bpm", "un tempo moderado para concentrarse."),
        "estud": ("mid_bpm", "ritmo constante, ideal para estudiar."),
        "trabaj": ("mid_bpm", "ritmo de enfoque, productividad constante."),
        "ejercic": ("high_bpm", "¡Alta energía! Ritmo para entrenar duro."),
        "entren": ("high_bpm", "¡BPM arriba! Perfecto para tu sesión deportiva."),
        "batall": ("high_bpm", "¡Épico! Energía y ritmo para la batalla."),
        "pelea": ("high_bpm", "Energía máxima para motivarte al límite."),
        "alegre": ("high_bpm", "Ritmo positivo y vibrante para subir el ánimo."),
        "fiesta": ("high_bpm", "¡De fiesta! Ritmo acelerado y bailable."),
        "bail": ("high_bpm", "Ritmo bailable de alta energía."),
    }

    matched_tempo = None
    reason = "alineación general de ritmo"
    
    for kw, (tempo_class, desc) in MOOD_KEYWORDS.items():
        if kw in query_lower:
            matched_tempo = tempo_class
            reason = desc
            break
            
    filtered_songs = []
    if matched_tempo == "low_bpm":
        filtered_songs = [s for s in songs if s["bpm"] < 95]
    elif matched_tempo == "high_bpm":
        filtered_songs = [s for s in songs if s["bpm"] > 115]
    elif matched_tempo == "mid_bpm":
        filtered_songs = [s for s in songs if s["bpm"] >= 95 and s["bpm"] <= 115]

    if not filtered_songs:
        filtered_songs = songs
        
    import random
    selected = random.choice(filtered_songs)
    
    reply = f"🎵 He seleccionado **{selected['title']}** ({selected['bpm']:.0f} BPM) para ti, que se adapta a un ritmo de **{reason}**."
    return {"matched_song_id": selected["id"], "reply": reply}

# --------------------------------------------------------------------------- #
# Playlists (agrupación por mood/acción, con nombre personalizable)
# --------------------------------------------------------------------------- #
class PlaylistCreate(BaseModel):
    name: str
    song_ids: list[int] = []

def _ensure_playlists_table():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            song_ids TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

@app.get("/api/playlists")
def list_playlists():
    _ensure_playlists_table()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, name, song_ids FROM playlists ORDER BY id").fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"], "song_ids": json.loads(r["song_ids"])} for r in rows]

@app.post("/api/playlists")
def create_playlist(req: PlaylistCreate):
    _ensure_playlists_table()
    conn = sqlite3.connect(DB_NAME)
    cur = conn.execute("INSERT INTO playlists (name, song_ids) VALUES (?, ?)",
                       (req.name, json.dumps(req.song_ids)))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": pid, "name": req.name, "song_ids": req.song_ids}

@app.put("/api/playlists/{pid}")
def update_playlist(pid: int, req: PlaylistCreate):
    """Actualiza nombre y/o canciones de una playlist (para añadir/quitar a mano)."""
    _ensure_playlists_table()
    conn = sqlite3.connect(DB_NAME)
    conn.execute("UPDATE playlists SET name = ?, song_ids = ? WHERE id = ?",
                 (req.name, json.dumps(req.song_ids), pid))
    conn.commit()
    conn.close()
    return {"id": pid, "name": req.name, "song_ids": req.song_ids}

@app.delete("/api/playlists/{pid}")
def delete_playlist(pid: int):
    _ensure_playlists_table()
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM playlists WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": pid}

@app.get("/api/playlists/suggest")
def suggest_playlists():
    """Agrupa la biblioteca en buckets de mood por BPM (sugerencias para guardar)."""
    songs = list_songs()
    buckets = {
        "⚔️ Acción / Pelea": [],
        "🏃 Energía / Ejercicio": [],
        "🎯 Enfoque / Trabajo": [],
        "🌙 Relax / Calma": [],
    }
    for s in songs:
        bpm = s.get("bpm") or 0
        if bpm >= 125:
            buckets["⚔️ Acción / Pelea"].append(s["id"])
        elif bpm >= 115:
            buckets["🏃 Energía / Ejercicio"].append(s["id"])
        elif bpm >= 95:
            buckets["🎯 Enfoque / Trabajo"].append(s["id"])
        else:
            buckets["🌙 Relax / Calma"].append(s["id"])
    return [{"name": k, "song_ids": v} for k, v in buckets.items() if v]

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Intelligent FLAC Player server at http://127.0.0.1:8000")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
