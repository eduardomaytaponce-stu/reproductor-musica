#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import queue
import socket
import threading
from collections import deque
import numpy as np
try:
    import sounddevice as sd
except OSError as e:
    msg = (
        "No se encontró la biblioteca de sistema 'PortAudio' (libportaudio2).\n"
        "Para corregirlo, instala la dependencia en tu sistema Linux ejecutando:\n"
        "    sudo apt install libportaudio2"
    )
    raise ImportError(msg) from e

import librosa
import requests
from openwakeword.model import Model
from faster_whisper import WhisperModel

# --- CONFIGURACIÓN ---
SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80 ms a 16 kHz (requerido por openwakeword)
VOICE_PROFILE_FILE = "voice_profile.json"
CUSTOM_MODEL_PATH = "models/activa_reproductor.onnx"
SERVER_URL = "http://127.0.0.1:8000"

# --- ESTADO GLOBAL ---
audio_queue = queue.Queue()
rolling_buffer = deque(maxlen=SAMPLE_RATE * 2)  # 2 segundos de audio en float32
is_recording = False
whisper_model = None

# Cargar perfil de voz
voice_profile = {"reference_pitch": 150.0, "tolerance": 0.25, "calibrated": False}
if os.path.exists(VOICE_PROFILE_FILE):
    try:
        with open(VOICE_PROFILE_FILE, "r") as f:
            voice_profile = json.load(f)
            print(f"📖 Perfil de voz cargado: Pitch de referencia = {voice_profile['reference_pitch']} Hz, Tolerancia = {voice_profile['tolerance']}")
    except Exception as e:
        print(f"⚠️ Error al leer {VOICE_PROFILE_FILE}: {e}")
else:
    print(f"ℹ️ Perfil de voz no calibrado. Se usará validación general de voz humana.")

# --- UTILITIES ---

def is_online(host="8.8.8.8", port=53, timeout=1.0):
    """Verifica si hay conexión a Internet conectándose a un servidor DNS."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except OSError:
        return False

def play_beep(freq=880, duration=0.15, sr=SAMPLE_RATE):
    """Genera y reproduce un pitido de confirmación sintético."""
    try:
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        beep = np.sin(2 * np.pi * freq * t) * 0.25
        # Desvanecimiento (fade out) para evitar clics de audio
        fade_len = int(sr * 0.02)
        fade = np.ones_like(beep)
        fade[-fade_len:] = np.linspace(1.0, 0.0, fade_len)
        beep *= fade
        sd.play(beep, sr)
        sd.wait()
    except Exception as e:
        print(f"⚠️ Error al reproducir el pitido: {e}")

def record_command(duration=3.0, sr=SAMPLE_RATE):
    """Graba el comando del micrófono por un tiempo fijo."""
    try:
        print(f"🎤 Grabando comando por {duration} segundos...")
        recording = sd.rec(int(duration * sr), samplerate=sr, channels=1, dtype='float32')
        sd.wait()
        return recording.flatten()
    except Exception as e:
        print(f"⚠️ Error durante la grabación: {e}")
        return np.zeros(int(duration * sr), dtype=np.float32)

def calculate_f0(audio_data, sr=SAMPLE_RATE):
    """Calcula el pitch promedio (F0) usando librosa.yin en rango de habla humana."""
    try:
        if len(audio_data) == 0 or np.max(np.abs(audio_data)) < 1e-4:
            return 0.0
        
        fmin, fmax = 65, 280
        # yin calcula la frecuencia fundamental por tramos
        f0 = librosa.yin(audio_data, fmin=fmin, fmax=fmax, sr=sr, frame_length=512, hop_length=128)
        
        # Filtrar valores válidos dentro del rango de voz humana real
        valid_f0 = f0[np.isfinite(f0) & (f0 > fmin + 1) & (f0 < fmax - 1)]
        if len(valid_f0) > 0:
            return float(np.mean(valid_f0))
        return 0.0
    except Exception as e:
        print(f"⚠️ Error en análisis de pitch F0: {e}")
        return 0.0

# --- FUNCIONES CLAVE ---

def calibrate_voice(duration=3.0, sr=SAMPLE_RATE):
    """Rutina de calibración del pitch del usuario."""
    print("\n=== CALIBRACIÓN DE ASISTENTE DE VOZ ===")
    print("1. Prepárate para hablar al escuchar el pitido.")
    print("2. Di la frase clave: 'Activa reproductor' con tu tono de voz natural.")
    print("Iniciando en 3...")
    time.sleep(1.0)
    print("Iniciando en 2...")
    time.sleep(1.0)
    print("Iniciando en 1...")
    time.sleep(1.0)
    
    play_beep(freq=1000, duration=0.2)
    audio = record_command(duration=duration, sr=sr)
    play_beep(freq=600, duration=0.2)
    
    print("🔍 Analizando tono acústico...")
    avg_pitch = calculate_f0(audio, sr=sr)
    if avg_pitch > 60:
        profile = {
            "reference_pitch": round(avg_pitch, 1),
            "tolerance": 0.25,
            "calibrated": True
        }
        with open(VOICE_PROFILE_FILE, "w") as f:
            json.dump(profile, f, indent=2)
        print(f"\n✅ ¡Calibración exitosa!")
        print(f"🎙️ Pitch F0 promedio: {profile['reference_pitch']:.1f} Hz")
        print(f"Configuración guardada en '{VOICE_PROFILE_FILE}'")
    else:
        print("\n❌ Error: No se pudo detectar voz clara. Ajusta tu volumen/micrófono e intenta de nuevo.")

def transcribe_offline_async(audio_data):
    """Realiza la transcripción offline con Faster-Whisper en un hilo secundario."""
    global whisper_model
    
    def run_whisper():
        global whisper_model
        if whisper_model is None:
            print("🤖 Inicializando Faster-Whisper local...")
            try:
                whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
            except Exception as e:
                print(f"❌ Error al inicializar Faster-Whisper: {e}")
                return
        
        print("💾 Transcribiendo audio localmente...")
        start_time = time.time()
        try:
            segments, info = whisper_model.transcribe(audio_data, beam_size=5, language="es")
            text = " ".join([seg.text for seg in segments]).strip()
            elapsed = time.time() - start_time
            print(f"🔊 Transcripción offline completada en {elapsed:.2f}s: '{text}'")
            
            # Enviar el comando transcrito al backend
            resp = requests.post(f"{SERVER_URL}/api/voice/command", json={"text": text})
            if resp.status_code == 200:
                print("✔ Comando offline enviado con éxito.")
            else:
                print(f"⚠️ Error al enviar comando: {resp.status_code}")
        except Exception as e:
            print(f"❌ Error durante la transcripción offline: {e}")
            
    threading.Thread(target=run_whisper, daemon=True).start()

# --- AUDIO STREAM CALLBACK ---

def audio_callback(indata, frames, time_info, status):
    """Callback de sounddevice para capturar audio de forma continua."""
    global is_recording
    if status:
        print(status, file=sys.stderr)
        
    chunk_int16 = indata[:, 0]
    # Convertir a float32 para análisis acústico
    chunk_float32 = chunk_int16.astype(np.float32) / 32768.0
    rolling_buffer.extend(chunk_float32)
    
    # Solo encolar para wake word si no estamos en medio de una grabación/transcripción
    if not is_recording:
        audio_queue.put(chunk_int16.copy())

# --- BUCLE DE CONTROL PRINCIPAL ---

def prediction_loop(oww_model, active_model_key):
    global is_recording
    print(f"🎧 Escuchando continuamente. Modelo activo: '{active_model_key}'...")
    
    while True:
        try:
            chunk = audio_queue.get(timeout=1.0)
        except queue.Empty:
            continue
            
        predictions = oww_model.predict(chunk)
        prob = predictions.get(active_model_key, 0.0)
        
        if prob > 0.55:
            print(f"\n🎯 Activación detectada (confianza: {prob:.2f})")
            
            # Extraer los últimos 1.5s de audio para pitch
            audio_segment = np.array(list(rolling_buffer))[-24000:]
            avg_pitch = calculate_f0(audio_segment)
            print(f"🎙️ Pitch F0 calculado: {avg_pitch:.1f} Hz")
            
            validated = True
            if voice_profile["calibrated"]:
                ref = voice_profile["reference_pitch"]
                tol = voice_profile["tolerance"]
                lower_bound = ref * (1 - tol)
                upper_bound = ref * (1 + tol)
                if not (lower_bound <= avg_pitch <= upper_bound):
                    print(f"❌ Validación de voz fallida. F0: {avg_pitch:.1f} Hz fuera del rango [{lower_bound:.1f}, {upper_bound:.1f}]. Comando ignorado.")
                    validated = False
            else:
                # Comportamiento permisivo si no está calibrado
                if avg_pitch < 60 or avg_pitch > 350:
                    print(f"⚠️ Validación de voz omitida. F0 {avg_pitch:.1f} Hz fuera de rango humano normal (60-350 Hz). Comando ignorado.")
                    validated = False
                else:
                    print("ℹ️ Validación de voz: perfil no calibrado. Tono dentro del rango humano permitido.")
            
            if validated:
                is_recording = True
                print("🔔 Dueño de voz confirmado. Reproduciendo pitido...")
                play_beep()
                
                # Graba el comando
                cmd_audio = record_command(duration=3.0)
                
                # Chequeo de conexión
                online = is_online()
                print(f"🌐 Conexión de red: {'ONLINE' if online else 'OFFLINE'}")
                
                if online:
                    print("📡 Enviando alerta al frontend para transcripción mediante Web Speech API...")
                    try:
                        requests.post(f"{SERVER_URL}/api/voice/wake", json={"online": True})
                    except Exception as e:
                        print(f"⚠️ No se pudo enviar evento al servidor: {e}")
                else:
                    print("💾 Modo offline detectado. Procesando con Faster-Whisper...")
                    transcribe_offline_async(cmd_audio)
                
                # Limpiar la cola de audio residual
                while not audio_queue.empty():
                    try:
                        audio_queue.get_nowait()
                    except queue.Empty:
                        break
                
                # Breve pausa para no auto-activarse
                time.sleep(0.5)
                is_recording = False
                print("🎧 Volviendo a modo escucha...")

# --- MAIN ---

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        calibrate_voice()
        return
        
    print("🔊 Iniciando Asistente de Voz Local...")
    
    # 1. Determinar modelos de wake word
    wakeword_model_paths = []
    if os.path.exists(CUSTOM_MODEL_PATH):
        print(f"⭐ Usando modelo de wake word personalizado: {CUSTOM_MODEL_PATH}")
        wakeword_model_paths.append(CUSTOM_MODEL_PATH)
    else:
        print(f"⚠️ No se encontró modelo personalizado en '{CUSTOM_MODEL_PATH}'.")
        import openwakeword
        paths = openwakeword.get_pretrained_model_paths()
        jarvis_path = [p for p in paths if "hey_jarvis" in p][0]
        print(f"ℹ️ Usando modelo preentrenado 'hey_jarvis' de openwakeword como fallback.")
        wakeword_model_paths.append(jarvis_path)
        
    active_model_key = os.path.splitext(os.path.basename(wakeword_model_paths[0]))[0]
    
    # 2. Inicializar openwakeword
    try:
        oww_model = Model(wakeword_model_paths=wakeword_model_paths, vad_threshold=0.5)
    except Exception as e:
        print(f"❌ Error al inicializar openwakeword: {e}")
        return
        
    # 3. Pre-cargar Faster-Whisper si estamos offline o para optimizar latencia
    global whisper_model
    print("🤖 Precargando Faster-Whisper local en segundo plano...")
    try:
        # Hilo separado para no retrasar el inicio del listener
        def load_whisper():
            global whisper_model
            whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
            print("✔ Faster-Whisper precargado y listo.")
        threading.Thread(target=load_whisper, daemon=True).start()
    except Exception as e:
        print(f"⚠️ Error al precargar Whisper: {e}")

    # 4. Iniciar hilo de predicción
    pred_thread = threading.Thread(target=prediction_loop, args=(oww_model, active_model_key), daemon=True)
    pred_thread.start()
    
    # 5. Iniciar stream del micrófono
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', 
                             blocksize=CHUNK_SIZE, callback=audio_callback):
            print("🎙️ Entrada de micrófono abierta con éxito. Presione Ctrl+C para salir.")
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n👋 Asistente de voz apagado.")
    except Exception as e:
        print(f"❌ Error en el flujo del micrófono: {e}")

if __name__ == "__main__":
    main()
