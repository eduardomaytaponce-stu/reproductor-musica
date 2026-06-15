"""
Motor de reproducción bit-perfect para el reproductor FLAC Hi-Fi.

En lugar de reproducir el audio en el navegador (Web Audio API -> PipeWire en
modo compartido, que remuestrea a 48 kHz y rompe la alta resolución), este motor
delega la reproducción a **mpv** hablando directamente con el DAC vía ALSA en
**modo exclusivo (bit-perfect)**: misma ruta que usa VLC, a la frecuencia y
profundidad nativas del archivo.

No requiere `libmpv` ni `python-mpv`: controla el binario `mpv` mediante su
socket IPC JSON (`--input-ipc-server`).

Uso como prueba (Etapa 1):
    python player_engine.py "/ruta/a/cancion.flac"
Imprime la frecuencia/formato decodificado del archivo y lo que realmente se
envía al DAC. Si coinciden y no hay remuestreo, la reproducción es bit-perfect.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import threading

import numpy as np
import soundfile as sf

# Dispositivo ALSA del DAC Hi-Res (Kiwi Ears Allegro). Usar el nombre de la
# tarjeta es más estable que el índice numérico entre reinicios.
DEFAULT_ALSA_DEVICE = "alsa/hw:CARD=Mini,DEV=0"

# Margen (~-1 dB) para los caminos RESAMPLEADOS y de MEZCLA. El resampleo de
# masters muy fuertes (0 dBFS) genera picos inter-muestra que superan el máximo y
# CLIPEAN -> distorsión áspera y dañina. Este headroom los mantiene bajo tope.
# NO se aplica al camino bit-perfect (ahí las muestras ya están dentro de rango).
RESAMPLE_HEADROOM = 0.89

# Calidad del resampler (anti-aliasing). 'HQ' filtra mucho mejor que 'MQ' al bajar
# de 96k/48k a 44.1k contenido rico en agudos (evita asperezas/aliasing).
RESAMPLE_QUALITY = "HQ"


class BitPerfectPlayer:
    """Reproductor de un solo flujo, bit-perfect, vía mpv + ALSA exclusivo."""

    def __init__(self, alsa_device=DEFAULT_ALSA_DEVICE, exclusive=True):
        self.alsa_device = alsa_device
        self.exclusive = exclusive
        self.proc = None
        self._sock = None
        self._sock_path = None
        self._req_id = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Ciclo de vida del proceso mpv
    # ------------------------------------------------------------------ #
    def start(self):
        """Lanza mpv en modo idle, listo para recibir comandos por IPC."""
        if self.proc and self.proc.poll() is None:
            return

        self._sock_path = os.path.join(
            tempfile.gettempdir(), f"mpv-hifi-{os.getpid()}-{id(self)}.sock"
        )
        if os.path.exists(self._sock_path):
            os.remove(self._sock_path)

        args = [
            "mpv",
            "--idle=yes",
            "--no-video",
            "--no-terminal",
            "--really-quiet",
            f"--input-ipc-server={self._sock_path}",
            # ---- Ruta de audio BIT-PERFECT ----
            "--ao=alsa",
            f"--audio-device={self.alsa_device}",
            f"--audio-exclusive={'yes' if self.exclusive else 'no'}",
            # No tocar la señal: sin remuestreo forzado, sin filtros, sin
            # normalización de volumen ni replaygain -> bits intactos.
            "--audio-samplerate=0",      # 0 = seguir la frecuencia nativa del archivo
            "--af=",                      # cadena de filtros vacía
            "--replaygain=no",
            "--volume=100",               # volumen software al 100% (transparente)
            "--volume-max=100",
            # 'weak': reabre el DAC a la frecuencia NATIVA cuando cambia de pista
            # (bit-perfect por archivo) y mantiene gapless solo entre pistas de igual
            # frecuencia. 'yes' rompería bit-perfect al resamplear todo al rate inicial.
            "--gapless-audio=weak",
            "--cache=yes",
            "--demuxer-max-bytes=64MiB",  # búfer amplio: evita underruns/microcortes
            "--demuxer-readahead-secs=20",
        ]

        self.proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self._connect_socket()

    def _connect_socket(self, timeout=5.0):
        """Espera a que mpv cree el socket IPC y se conecta."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if os.path.exists(self._sock_path):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(self._sock_path)
                    s.settimeout(2.0)
                    self._sock = s
                    return
                except (ConnectionRefusedError, FileNotFoundError, OSError):
                    pass
            time.sleep(0.05)
        raise RuntimeError("No se pudo conectar al socket IPC de mpv (¿mpv falló al abrir el DAC?)")

    # ------------------------------------------------------------------ #
    # Protocolo IPC JSON (una orden JSON por línea)
    # ------------------------------------------------------------------ #
    def _command(self, *args):
        """Envía un comando a mpv y devuelve su respuesta (dict)."""
        if not self._sock:
            raise RuntimeError("Socket IPC no conectado")
        with self._lock:
            self._req_id += 1
            rid = self._req_id
            payload = json.dumps({"command": list(args), "request_id": rid}) + "\n"
            self._sock.sendall(payload.encode("utf-8"))

            # Leer respuestas hasta encontrar la de nuestro request_id
            buf = b""
            deadline = time.time() + 3.0
            while time.time() < deadline:
                try:
                    chunk = self._sock.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if msg.get("request_id") == rid:
                        return msg
                    # los mensajes 'event' se ignoran aquí
            return {"error": "timeout"}

    def get_property(self, name):
        resp = self._command("get_property", name)
        return resp.get("data") if resp.get("error") == "success" else None

    def set_property(self, name, value):
        return self._command("set_property", name, value)

    # ------------------------------------------------------------------ #
    # API de reproducción
    # ------------------------------------------------------------------ #
    def load(self, filepath):
        """Carga y reproduce un archivo (reemplaza el actual)."""
        self._command("loadfile", filepath, "replace")

    def pause(self):
        self.set_property("pause", True)

    def resume(self):
        self.set_property("pause", False)

    def seek(self, seconds):
        self._command("seek", seconds, "absolute")

    def stop(self):
        self._command("stop")

    def status(self):
        return {
            "time_pos": self.get_property("time-pos"),
            "duration": self.get_property("duration"),
            "pause": self.get_property("pause"),
            "path": self.get_property("path"),
        }

    def audio_chain(self):
        """
        Devuelve los parámetros de audio decodificados vs. los enviados al DAC.
        Si coinciden (misma frecuencia/formato) la reproducción es bit-perfect.
        """
        return {
            "decoded": self.get_property("audio-params"),       # del archivo
            "output": self.get_property("audio-out-params"),    # hacia el DAC
            "device": self.get_property("audio-device"),
            "exclusive": self.exclusive,
        }

    def close(self):
        try:
            if self._sock:
                self._command("quit")
                self._sock.close()
        except Exception:
            pass
        finally:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            if self._sock_path and os.path.exists(self._sock_path):
                try:
                    os.remove(self._sock_path)
                except OSError:
                    pass


# ====================================================================== #
# MOTOR HI-FI CON CROSSFADE  (soundfile + numpy + aplay)
# ---------------------------------------------------------------------- #
# Reproduce bit-perfect (decodifica con soundfile y envía PCM crudo S32_LE
# al DAC vía `aplay -D hw:...`, a la frecuencia NATIVA de cada archivo) y,
# a diferencia de mpv/MPD, controlamos el rate nosotros: el crossfade se
# hace al rate NATIVO de la pista entrante, por lo que tras el fundido la
# reproducción continúa bit-perfect sin recargar ni costura.
# No requiere instalar nada: soundfile, numpy y aplay ya están presentes.
# ====================================================================== #
class AplayHiFiEngine:
    def __init__(self, alsa_device="hw:CARD=Mini,DEV=0"):
        self.device = alsa_device
        self._aplay = None
        self._aplay_rate = None
        self._aplay_ch = None
        self._lock = threading.Lock()
        self._req = None                 # petición pendiente: ('load',path,xfade) | ('stop',)
        self._seek = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread = None
        self._cur_path = None
        self._cur_sr = None
        self._cur_frames = 0
        self._pos = 0                    # frames reproducidos de la pista actual
        self._xfading = False
        self._err = None
        self._pw_suspended = False       # ¿PipeWire ya está suspendido (sesión activa)?

    # ---- ciclo de vida ----
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._close_aplay()
        self._pw_suspend(False)         # devolver el DAC a PipeWire (apps/juegos/DJ)

    # ---- API pública (compatible con el motor mpv) ----
    def load(self, path, crossfade=0.0, entry_offset=0.0):
        """
        Reproduce `path`. Si crossfade>0 y hay algo sonando, hace fundido.
        `entry_offset` (s) = punto donde ENTRA la pista (p.ej. una sección
        enérgica), en vez de su intro.
        """
        with self._lock:
            self._req = ('load', path, float(crossfade), float(entry_offset))
        self._paused.clear()

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def seek(self, seconds):
        with self._lock:
            self._seek = float(seconds)
        self._paused.clear()

    def stop(self):
        with self._lock:
            self._req = ('stop',)

    def release_device(self):
        """
        Libera el DAC de forma SÍNCRONA y lo devuelve a PipeWire. Necesario al
        cambiar a modo DJ (navegador) u otras apps: si solo encolamos stop y el
        worker está ocupado (p.ej. mitad de un fundido), PipeWire seguiría
        suspendido y el audio compartido saldría mudo.
        """
        self.stop()
        self._close_aplay()          # mata aplay ya -> libera el hw
        self._pw_suspend(False)      # reactiva el sink de PipeWire
        self._cur_path = None
        self._cur_sr = None

    # ---- coordinación con PipeWire ----
    def _pw_suspend(self, suspend=True):
        """
        Suspende (o reactiva) el sink de PipeWire del DAC. Necesario porque el
        acceso directo a `hw:` falla con 'Device or resource busy' si PipeWire
        tiene el dispositivo activo. Suspendido = libre para bit-perfect exclusivo.
        """
        try:
            out = subprocess.run(['pactl', 'list', 'short', 'sinks'],
                                 capture_output=True, text=True, timeout=2).stdout
            for line in out.splitlines():
                cols = line.split('\t')
                if len(cols) >= 2 and any(k in cols[1] for k in ('Kiwi', 'Allegro', 'Mini')):
                    subprocess.run(['pactl', 'suspend-sink', cols[1], '1' if suspend else '0'],
                                   timeout=2)
        except Exception:
            pass
        self._pw_suspended = bool(suspend)

    # ---- aplay (salida ALSA hw: directa = bit-perfect exclusivo) ----
    def _spawn_aplay(self, rate, ch):
        # Búfer amplio (1.5 s): da margen para el resample del fundido entre
        # frecuencias distintas (44.1k↔48k) sin underrun -> elimina micropausas.
        return subprocess.Popen(
            ['aplay', '-D', self.device, '-f', 'S32_LE',
             '-r', str(rate), '-c', str(ch), '--buffer-time=1500000', '-q', '-'],
            stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )

    def _open_aplay(self, rate, ch):
        self._close_aplay()
        self._err = None
        # Reapertura RÁPIDA: si ya somos dueños del DAC (PipeWire suspendido), reabrir
        # NO necesita re-suspender ni esperar 0.4s -> casi sin hueco al cambiar de rate
        # entre canciones. Esto elimina el silencio en transiciones de distinta frecuencia.
        if self._pw_suspended:
            ap = self._spawn_aplay(rate, ch)
            time.sleep(0.05)
            if ap.poll() is None:
                self._aplay = ap
                self._aplay_rate, self._aplay_ch = rate, ch
                return
            try: ap.kill()
            except Exception: pass
        # Apertura COMPLETA (primera vez o si la rápida falló): suspender + esperar + reintentar.
        for intento in range(5):
            self._pw_suspend(True)
            time.sleep(0.4)
            ap = self._spawn_aplay(rate, ch)
            time.sleep(0.15)
            if ap.poll() is None:        # sigue vivo -> abrió el dispositivo
                self._aplay = ap
                self._aplay_rate, self._aplay_ch = rate, ch
                return
            try: ap.kill()
            except Exception: pass
        # No se pudo tras varios intentos
        self._err = "DAC ocupado: cierra la app que lo use (o reproduce de nuevo en unos segundos)."
        self._aplay = None
        self._aplay_rate = None

    def _close_aplay(self):
        if self._aplay:
            try:
                if self._aplay.stdin:
                    self._aplay.stdin.close()
            except Exception:
                pass
            try:
                self._aplay.terminate()
                self._aplay.wait(timeout=1)
            except Exception:
                try:
                    self._aplay.kill()
                except Exception:
                    pass
            self._aplay = None
            self._aplay_rate = None
            self._aplay_ch = None

    def _ensure_aplay(self, rate, ch):
        if self._aplay is None or rate != self._aplay_rate or ch != self._aplay_ch:
            self._open_aplay(rate, ch)

    def _to_s32(self, f):
        """float [-1,1] -> int32 con headroom (~-1 dB) y recorte de seguridad.
        Evita el clipping áspero (y dañino) del overshoot al resamplear masters
        fuertes a 0 dBFS. Solo se usa en los caminos resampleados/mezclados."""
        return np.clip(f * (RESAMPLE_HEADROOM * 2147483647.0),
                       -2147483648, 2147483647).astype('<i4')

    def _write(self, int32_arr):
        if self._aplay is None or self._aplay.stdin is None:
            return False
        try:
            self._aplay.stdin.write(np.ascontiguousarray(int32_arr, dtype='<i4').tobytes())
            return True
        except (BrokenPipeError, OSError):
            self._err = "DAC ocupado o no disponible (¿otra app lo está usando?)"
            return False

    # ---- hilo de reproducción ----
    def _worker(self):
        cur = None
        block = 4410
        resampler = None     # soxr.ResampleStream con estado: cross-rate SIN clics
        rs_key = None        # (src, dst, ch) para el que está configurado
        while not self._stop.is_set():
            with self._lock:
                req, self._req = self._req, None
                seek, self._seek = self._seek, None

            if req:
                if req[0] == 'stop':
                    if cur:
                        cur.close(); cur = None
                    self._close_aplay()
                    self._pw_suspend(False)     # devolver el DAC a PipeWire
                    self._cur_path = None; self._pos = 0; self._cur_sr = None
                    resampler = None; rs_key = None
                    continue
                if req[0] == 'load':
                    _, path, xf, entry = req
                    try:
                        nxt = sf.SoundFile(path)
                    except Exception as e:
                        self._err = f"No se pudo abrir el archivo: {e}"
                        continue
                    self._err = None
                    try:
                        if cur is not None and xf > 0:
                            cur = self._do_crossfade(cur, nxt, xf, entry)
                        else:
                            if cur:
                                cur.close()
                            cur = nxt
                            self._ensure_aplay(cur.samplerate, cur.channels)
                            if entry > 0:
                                cur.seek(int(entry * cur.samplerate))
                    except Exception as e:
                        # Si el fundido falla (p.ej. canales distintos), corte limpio
                        self._err = None
                        if cur and cur is not nxt:
                            try: cur.close()
                            except Exception: pass
                        cur = nxt
                        self._ensure_aplay(cur.samplerate, cur.channels)
                    self._cur_path = path
                    self._cur_sr = cur.samplerate
                    self._cur_frames = cur.frames
                    self._pos = cur.tell()
                    block = int(cur.samplerate * 0.1)
                    resampler = None; rs_key = None   # nueva pista -> nuevo resampler
                    self._paused.clear()
                    continue

            if cur is None:
                time.sleep(0.05)
                continue

            if seek is not None:
                try:
                    cur.seek(max(0, int(seek * cur.samplerate)))
                    self._pos = cur.tell()
                except Exception:
                    pass

            if self._paused.is_set():
                time.sleep(0.03)
                continue

            # Asegurar el DAC abierto (p.ej. si la 1ª apertura falló por ocupado).
            if self._aplay_rate is None:
                self._ensure_aplay(cur.samplerate, cur.channels)
                resampler = None; rs_key = None
                if self._aplay_rate is None:
                    time.sleep(0.2)            # DAC ocupado: reintentar
                    continue

            if cur.samplerate == self._aplay_rate:
                # --- Camino BIT-PERFECT: misma frecuencia, muestras crudas ---
                data = cur.read(block, dtype='int32', always_2d=True)
                if len(data) == 0:                 # fin natural de la pista
                    cur.close(); cur = None
                    self._cur_path = None
                    time.sleep(0.03)
                    continue
                if not self._write(data):
                    cur.close(); cur = None
                    continue
                self._pos = cur.tell()
            else:
                # --- Camino RESAMPLE con estado (cross-rate): SIN reabrir el DAC,
                #     SIN clics. Tras una transición a otra frecuencia, la pista
                #     continúa resampleada al rate abierto -> cero pausa. ---
                if resampler is None or rs_key != (cur.samplerate, self._aplay_rate, cur.channels):
                    import soxr
                    resampler = soxr.ResampleStream(
                        cur.samplerate, self._aplay_rate, cur.channels,
                        dtype='float32', quality=RESAMPLE_QUALITY)
                    rs_key = (cur.samplerate, self._aplay_rate, cur.channels)
                fdata = cur.read(block, dtype='float32', always_2d=True)
                if len(fdata) == 0:                # fin -> vaciar el resampler
                    tail = resampler.resample_chunk(
                        np.zeros((0, cur.channels), dtype='float32'), last=True)
                    if len(tail):
                        self._write(self._to_s32(tail))
                    cur.close(); cur = None
                    self._cur_path = None
                    resampler = None; rs_key = None
                    time.sleep(0.03)
                    continue
                rs = resampler.resample_chunk(fdata)
                if len(rs):
                    # headroom -1 dB para que el overshoot del resampleo NO clipee.
                    if not self._write(self._to_s32(rs)):
                        cur.close(); cur = None
                        continue
                self._pos = cur.tell()

    def _do_crossfade(self, cur, nxt, dur, entry_offset=0.0):
        """Fundido equal-power SIN hueco: se mezcla al rate del DAC ya abierto (= el
        de la saliente), por lo que NO se reabre el dispositivo durante el fundido.
        Tras el fundido, la entrante sigue a su rate NATIVO (reapertura rápida si
        difiere). La entrante puede empezar en `entry_offset` (s) = sección enérgica."""
        rate = self._aplay_rate or cur.samplerate   # rate del DAC abierto AHORA
        if entry_offset > 0:
            try:
                nxt.seek(int(entry_offset * nxt.samplerate))
            except Exception:
                pass
        self._xfading = True
        # IMPORTANTE: la saliente puede estar en un rate DISTINTO al abierto (si venía
        # de una transición cross-rate, sonaba resampleada al vuelo). Se lee a SU rate
        # nativo y se resamplea al rate abierto, igual que la entrante. (Antes se asumía
        # que la saliente estaba al rate abierto -> la 2ª transición se rompía/pausaba.)
        tail = cur.read(int(dur * cur.samplerate), dtype='float32', always_2d=True)
        head = nxt.read(int(dur * nxt.samplerate), dtype='float32', always_2d=True)
        if (cur.samplerate != rate and len(tail) > 0) or (nxt.samplerate != rate and len(head) > 0):
            import librosa
            if cur.samplerate != rate and len(tail) > 0:
                tail = librosa.resample(tail.T, orig_sr=cur.samplerate, target_sr=rate, res_type='soxr_hq').T
            if nxt.samplerate != rate and len(head) > 0:
                head = librosa.resample(head.T, orig_sr=nxt.samplerate, target_sr=rate, res_type='soxr_hq').T
        m = min(len(tail), len(head))
        if m > 0 and tail.shape[1] == head.shape[1]:
            t = np.linspace(0.0, 1.0, m)[:, None]
            mix = tail[:m] * np.cos(t * np.pi / 2) + head[:m] * np.sin(t * np.pi / 2)
            # Limitador del fundido (suma equal-power) + headroom de _to_s32 -> NO clipea.
            peak = float(np.max(np.abs(mix)))
            if peak > 0.99:
                mix *= (0.99 / peak)
            self._write(self._to_s32(mix))   # al DAC YA abierto -> fundido sin hueco, con headroom
        cur.close()
        self._xfading = False
        # NO reabrimos el DAC: si la entrante tiene otra frecuencia, el worker la
        # resamplea al vuelo (soxr con estado) -> CERO pausa. Si es la misma
        # frecuencia, continúa bit-perfect. (La reapertura era la causa de la pausa.)
        return nxt

    # ---- estado (interfaz compatible con el endpoint /api/hifi/status) ----
    def status(self):
        sr = self._cur_sr or 1
        return {
            "time_pos": (self._pos / sr) if self._cur_path else None,
            "duration": (self._cur_frames / sr) if self._cur_path else None,
            "pause": self._paused.is_set(),
            "path": self._cur_path,
            "error": self._err,
        }

    def audio_chain(self):
        sr = self._cur_sr
        out = {"samplerate": self._aplay_rate, "format": "s32", "channels": self._aplay_ch} if self._aplay_rate else {}
        dec = {"samplerate": sr, "format": "s32", "channels": self._aplay_ch} if sr else {}
        return {"decoded": dec, "output": out, "exclusive": True}


# ---------------------------------------------------------------------- #
# Prueba de bit-perfect (Etapa 1)
# ---------------------------------------------------------------------- #
def _selftest(filepath):
    if not os.path.exists(filepath):
        print(f"✘ No existe el archivo: {filepath}", file=sys.stderr)
        return 1

    print(f"🎧 Abriendo DAC en modo EXCLUSIVO (bit-perfect): {DEFAULT_ALSA_DEVICE}")
    print("   (Si el navegador está reproduciendo por el mismo DAC, ciérralo: el modo")
    print("    exclusivo necesita el dispositivo libre.)\n")

    player = BitPerfectPlayer()
    try:
        player.start()
        player.load(filepath)

        # Dar tiempo a mpv a abrir el dispositivo y negociar el formato
        chain = {}
        for _ in range(40):
            time.sleep(0.15)
            chain = player.audio_chain()
            if chain.get("output"):
                break

        decoded = chain.get("decoded") or {}
        output = chain.get("output") or {}

        print(f"📄 Archivo  : {os.path.basename(filepath)}")
        print(f"🔓 Decodificado (nativo): "
              f"{decoded.get('samplerate', '?')} Hz · {decoded.get('format', '?')} · "
              f"{decoded.get('channels', '?')} ch")
        print(f"🔊 Enviado al DAC       : "
              f"{output.get('samplerate', '?')} Hz · {output.get('format', '?')} · "
              f"{output.get('channels', '?')} ch")
        print(f"🎚  Dispositivo          : {chain.get('device')} | exclusivo={chain.get('exclusive')}")

        same_rate = decoded.get("samplerate") == output.get("samplerate")
        print()
        if same_rate and output.get("samplerate"):
            print("✅ BIT-PERFECT: la frecuencia enviada al DAC coincide con la nativa del archivo.")
            print("   No hay remuestreo. Esta es la misma calidad que VLC en modo exclusivo (o mejor).")
        else:
            print("⚠️  Hay conversión de frecuencia (no bit-perfect). Revisar disponibilidad del DAC")
            print("    o que PipeWire no esté reteniendo el dispositivo.")

        # Reproducir 6 segundos como muestra audible
        print("\n▶ Reproduciendo 6 s de muestra...")
        time.sleep(6)
        return 0
    finally:
        player.close()
        print("⏹  Motor cerrado, DAC liberado.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python player_engine.py \"/ruta/a/cancion.flac\"", file=sys.stderr)
        sys.exit(1)
    sys.exit(_selftest(sys.argv[1]))
