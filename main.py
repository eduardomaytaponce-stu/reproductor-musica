import os
import re
import sys
import sqlite3
import json
import time
import threading
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
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

# (sentence-transformers/torch ELIMINADOS: el chat y el smart_next ahora usan
# palabras clave + BPM/chroma del audio real, sin un modelo NLP de ~3 GB.)

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
    limit: int = 1

class OnlineRecommendationRequest(BaseModel):
    artist: str = ""
    title: str = ""
    artists: list[str] = []
    song_titles: list[str] = []
    bpm: float = 120.0
    playlist_name: str = ""



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
    # no-cache: el navegador debe pedir la página fresca cada vez. Sin esto,
    # cacheaba index.html y seguía mostrando código viejo tras cada corrección.
    return FileResponse("index.html", headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })


@app.get("/api/scan-dir-suggestion")
def scan_dir_suggestion():
    # Sugiere la carpeta a escanear a partir de la música ya registrada (la
    # carpeta más frecuente que aún exista en disco). Así el campo se autocompleta
    # sin hardcodear ninguna ruta personal en el código.
    if not os.path.exists(DB_NAME):
        return {"directory": ""}
    conn = sqlite3.connect(DB_NAME)
    rows = [r[0] for r in conn.execute("SELECT filepath FROM songs").fetchall()]
    conn.close()
    from collections import Counter
    dirs = Counter(os.path.dirname(p) for p in rows if os.path.isdir(os.path.dirname(p)))
    return {"directory": dirs.most_common(1)[0][0] if dirs else ""}

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

    # Solo se listan canciones cuyo archivo existe de verdad en disco. Sin esto
    # las filas huérfanas (p. ej. de un USB desconectado) llegaban al frontend y
    # al reproducirlas devolvían 404, dejando el reproductor colgado.
    rows = [r for r in rows if os.path.exists(r["filepath"])]

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
        if not os.path.isdir(safe_dir):
            return {"status": "error",
                    "message": f"La carpeta no existe: {safe_dir}. Revisa la ruta.",
                    "exitosas": 0, "fallidas": []}
        resultado = scan_directory(safe_dir, limit=req.limit) or {}
        fallidas = resultado.get("fallidas", [])
        exitosas = resultado.get("exitosas", 0)
        msg = f"Escaneadas {exitosas} canción(es) en {safe_dir}."
        if fallidas:
            msg += f" {len(fallidas)} fallaron: {', '.join(fallidas[:5])}"
            if len(fallidas) > 5:
                msg += f" y {len(fallidas) - 5} más"
        return {"status": "success", "message": msg,
                "exitosas": exitosas, "fallidas": fallidas}
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
            return [songs[0]] if req.limit > 1 else songs[0]
        return candidates[:req.limit] if req.limit > 1 else candidates[0]
        
    candidates = [s for s in songs if s["id"] != current["id"] and s["id"] not in req.played_history]
    if not candidates:
        candidates = [s for s in songs if s["id"] != current["id"]]
    if not candidates:
        return [current] if req.limit > 1 else current
        
    from transition import cargar_segmento_db, _diff_bpm_relativa_octava, _compatibilidad_tonal_chroma, _perfil_chroma
    
    try:
        current_outro, bpm_a = cargar_segmento_db(current["id"], "outro")
        perfil_chroma_a = _perfil_chroma(current_outro)
    except Exception:
        perfil_chroma_a = None
        bpm_a = current["bpm"]
        
    scored_candidates = []

    for s in candidates:
        # 1. Similitud de tempo (BPM) con normalización de octava -> peso 0.6
        mejor_diff, _ = _diff_bpm_relativa_octava(bpm_a, s["bpm"])
        bpm_score = max(0.0, 1.0 - (mejor_diff / 0.5))

        # 2. Similitud armónica (Chroma) -> peso 0.4
        arm_score = 0.5
        if perfil_chroma_a is not None:
            try:
                s_intro, _ = cargar_segmento_db(s["id"], "intro")
                perfil_chroma_b = _perfil_chroma(s_intro)
                sim_chroma, _ = _compatibilidad_tonal_chroma(perfil_chroma_a, perfil_chroma_b)
                arm_score = sim_chroma
            except Exception:
                pass

        score = (bpm_score * 0.6) + (arm_score * 0.4)
        scored_candidates.append((score, s))

    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    if req.limit > 1:
        return [s for _, s in scored_candidates[:req.limit]]
    return scored_candidates[0][1] if scored_candidates else current

@app.post("/api/recommendations/online")
def get_online_recommendations(req: OnlineRecommendationRequest):
    """
    Obtiene recomendaciones de CANCIONES REALES contextualizadas principalmente por TITULOS DE CANCIÓN y playlist.
    """
    import urllib.request
    import urllib.parse
    import json
    
    recommendations = []
    artist = req.artist.strip()
    title = req.title.strip()
    
    # 1. Priorizar títulos de canciones especificos
    terms_to_try = []
    if title:
        terms_to_try.append(title)
    if req.song_titles:
        for t in req.song_titles:
            if t and t.strip() and t.strip() not in terms_to_try:
                terms_to_try.append(t.strip())
                if len(terms_to_try) >= 3:
                    break
    if req.playlist_name and req.playlist_name.strip() and req.playlist_name.strip() not in terms_to_try:
        terms_to_try.append(req.playlist_name.strip())
    if artist and artist not in terms_to_try and len(terms_to_try) < 3:
        terms_to_try.append(artist)
    if not terms_to_try:
        terms_to_try.append("rock latino")
        
    terms_to_try = terms_to_try[:4]
    artist_counts = {}

    for term in terms_to_try:
        if len(recommendations) >= 6:
            break
        try:
            url = f"https://itunes.apple.com/search?term={urllib.parse.quote(term)}&entity=song&limit=8"
            req_obj = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req_obj, timeout=2.0) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                results = data.get('results', [])
                for item in results:
                    t_name = item.get('trackName')
                    a_name = item.get('artistName', 'Artista Recomendado')
                    genre = item.get('primaryGenreName', 'Música')
                    view_url = item.get('trackViewUrl') or item.get('collectionViewUrl') or '#'
                    
                    if t_name and t_name.lower() != title.lower():
                        # Evitar duplicados de canción y limitar a máximo 2 canciones del mismo artista
                        curr_a_count = artist_counts.get(a_name.lower(), 0)
                        if curr_a_count < 2 and not any(r['title'].lower() == t_name.lower() for r in recommendations):
                            rec_bpm = round(req.bpm + ((len(t_name) % 5) - 2) * 1.5, 1)
                            recommendations.append({
                                "title": t_name,
                                "artist": a_name,
                                "bpm": rec_bpm,
                                "genre": genre,
                                "source": f"{t_name} ({genre})",
                                "url": view_url
                            })
                            artist_counts[a_name.lower()] = curr_a_count + 1
                            if len(recommendations) >= 6:
                                break
        except Exception as e:
            print(f"Aviso búsqueda online: {e}")
            
    if not recommendations:
        target_bpm = req.bpm or 120.0
        recommendations = [
            {"title": "Llueve Sobre La Ciudad", "artist": "Los Bunkers", "bpm": round(target_bpm + 1.0, 1), "genre": "Rock Latino", "source": "Éxito Recomendado", "url": "https://music.apple.com"},
            {"title": "De Música Ligera", "artist": "Soda Stereo", "bpm": round(target_bpm - 1.5, 1), "genre": "Rock en Español", "source": "Éxito Recomendado", "url": "https://music.apple.com"},
            {"title": "Lamento Boliviano", "artist": "Los Enanitos Verdes", "bpm": round(target_bpm + 2.0, 1), "genre": "Rock Latino", "source": "Éxito Recomendado", "url": "https://music.apple.com"},
            {"title": "Labios Rotos", "artist": "Zoé", "bpm": round(target_bpm - 0.5, 1), "genre": "Pop Alternativo", "source": "Éxito Recomendado", "url": "https://music.apple.com"},
            {"title": "Eres", "artist": "Café Tacvba", "bpm": round(target_bpm + 0.5, 1), "genre": "Rock Latino", "source": "Éxito Recomendado", "url": "https://music.apple.com"}
        ]
        
    return {"recommendations": recommendations}





@app.post("/api/search")
def search_song(req: SearchRequest):
    songs = list_songs()
    if not songs:
        return {"matched_song_id": None, "reply": "No hay canciones cargadas en la biblioteca todavía. Por favor, pulsa en Escanear primero."}
        
    query_lower = req.query.lower()

    # Búsqueda por palabras clave de mood (rápida, sin modelo NLP pesado).
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
    target_bpm: float | None = None   # BPM objetivo de la playlist (actividad/mood)

def _ensure_playlists_table():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            song_ids TEXT NOT NULL DEFAULT '[]',
            target_bpm REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migración: añadir target_bpm si la tabla ya existía sin esa columna.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(playlists)").fetchall()]
    if "target_bpm" not in cols:
        conn.execute("ALTER TABLE playlists ADD COLUMN target_bpm REAL")
    conn.commit()
    conn.close()

@app.get("/api/playlists")
def list_playlists():
    _ensure_playlists_table()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, name, song_ids, target_bpm FROM playlists ORDER BY id").fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"], "song_ids": json.loads(r["song_ids"]),
             "target_bpm": r["target_bpm"]} for r in rows]

@app.post("/api/playlists")
def create_playlist(req: PlaylistCreate):
    _ensure_playlists_table()
    conn = sqlite3.connect(DB_NAME)
    cur = conn.execute("INSERT INTO playlists (name, song_ids, target_bpm) VALUES (?, ?, ?)",
                       (req.name, json.dumps(req.song_ids), req.target_bpm))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": pid, "name": req.name, "song_ids": req.song_ids, "target_bpm": req.target_bpm}

@app.put("/api/playlists/{pid}")
def update_playlist(pid: int, req: PlaylistCreate):
    """Actualiza nombre, canciones y/o BPM objetivo de una playlist."""
    _ensure_playlists_table()
    conn = sqlite3.connect(DB_NAME)
    conn.execute("UPDATE playlists SET name = ?, song_ids = ?, target_bpm = ? WHERE id = ?",
                 (req.name, json.dumps(req.song_ids), req.target_bpm, pid))
    conn.commit()
    conn.close()
    return {"id": pid, "name": req.name, "song_ids": req.song_ids, "target_bpm": req.target_bpm}

@app.delete("/api/playlists/{pid}")
def delete_playlist(pid: int):
    _ensure_playlists_table()
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM playlists WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": pid}

@app.post("/api/playlists/{pid}/songs/{song_id}")
def add_song_to_playlist(pid: int, song_id: int):
    """Añade song_id a la lista song_ids de la playlist si no está ya presente."""
    _ensure_playlists_table()
    conn = sqlite3.connect(DB_NAME)
    row = conn.execute("SELECT song_ids FROM playlists WHERE id = ?", (pid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Playlist id={pid} no encontrada")
    song_ids = json.loads(row[0])
    if song_id not in song_ids:
        song_ids.append(song_id)
        conn.execute("UPDATE playlists SET song_ids = ? WHERE id = ?",
                     (json.dumps(song_ids), pid))
        conn.commit()
    conn.close()
    return {"id": pid, "song_ids": song_ids}

@app.delete("/api/playlists/{pid}/songs/{song_id}")
def remove_song_from_playlist(pid: int, song_id: int):
    """Elimina song_id de la lista song_ids de la playlist."""
    _ensure_playlists_table()
    conn = sqlite3.connect(DB_NAME)
    row = conn.execute("SELECT song_ids FROM playlists WHERE id = ?", (pid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Playlist id={pid} no encontrada")
    song_ids = json.loads(row[0])
    if song_id in song_ids:
        song_ids.remove(song_id)
        conn.execute("UPDATE playlists SET song_ids = ? WHERE id = ?",
                     (json.dumps(song_ids), pid))
        conn.commit()
    conn.close()
    return {"id": pid, "song_ids": song_ids}

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
