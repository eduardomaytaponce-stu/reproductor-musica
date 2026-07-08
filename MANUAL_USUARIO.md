# Manual de Usuario — Cloud-Fi 🎧

Dos reproductores que comparten la misma biblioteca:

- **PC "el estudio"** — reproductor Hi-Fi bit-perfect + mezclador DJ (navegador). Analiza la música y **exporta** los metadatos.
- **Android "Cloud-Fi Go"** — reproductor autónomo **100% offline** para deporte, viajes y juegos de mesa. No analiza nada: consume lo que exporta el PC.

> Para arquitectura interna y cómo desarrollar, ver **GUIA_DESARROLLADOR.md**.

---

# Parte A — Reproductor de PC

## 1. Iniciar el servidor
Desde la carpeta del proyecto:
```bash
uv run main.py
```
Abre **http://127.0.0.1:8000** en Chrome/Firefox/Brave.

## 2. Escanear tu música (primera vez)
1. En **Biblioteca FLAC** (panel izquierdo), verifica la ruta `/home/usuario/Música/`.
2. Pulsa **Escanear**. Analiza solo los archivos **nuevos** y guarda el resultado en `music_library.db`.
   - ~25-60 s por canción (el nuevo motor analiza la canción completa sección por sección).
   - Es **incremental**: si añades canciones, solo analiza las nuevas.

> **Si añades canciones y no aparecen:** el análisis se guarda en `music_library.db`; si el escaneo falla en silencio, suele ser porque el **disco está en solo lectura**. Verifica con
> `touch "/media/.../proyectos propios/reproductor de musica/.t" && rm .t` — si da "solo lectura", repara el disco (`sudo fsck`) o reinicia.

### 2.1 Re-analizar toda la biblioteca (tras actualizaciones del motor)
Cuando el motor de análisis mejora (como ocurrió con la v2 de BPM por secciones), hay que re-analizar todas las canciones para que los datos guardados se actualicen. Desde la carpeta del proyecto:

```bash
python scan_library.py --reanalyze-db
```

Esto re-analiza las **168 canciones** registradas. Tarda entre 30 y 90 minutos. Para re-analizar solo las canciones de un directorio nuevo (y forzar las ya registradas):

```bash
python scan_library.py "/home/usuario/Música/" --reanalyze-all
```

---

## 2A. Qué se analiza en cada canción

### Segmentación estructural
El motor divide cada canción en **secciones** detectando dónde cambia el carácter del audio (energía, brillo tímbrico, densidad rítmica). Una canción típica de 4 minutos produce 3–7 secciones. Esto permite:
- Calcular el BPM de cada sección por separado (más preciso).
- Identificar los **mejores puntos de transición**: los límites entre secciones son los momentos donde la música cambia de carácter y donde una mezcla suena más natural.

### BPM por sección (v2)
En la versión anterior el BPM se estimaba tomando 30 segundos del centro de la canción — si ese fragmento era la parte más energética (o la más tranquila), el resultado era incorrecto para el resto de la canción. Ahora:

1. Se analiza cada sección individualmente.
2. Las secciones con **beat claro** (alta "densidad de onset") aportan más peso al BPM global.
3. Si todas las secciones tienen señal rítmica débil y el BPM parece el doble del tempo real, el sistema lo corrige automáticamente dividiendo a la mitad.

**Ejemplos concretos:**
- *Alps* (Motorama): antes 136 BPM → ahora **68 BPM** (canción tranquila; el sistema detectó la señal débil y corrigió).
- *De la Nada* (William Luna): antes 152 BPM → ahora **56 BPM** (huayno lento; todas las secciones consistentes y débiles).
- *Tabaco y Chanel* (Bacilos): 95.7 BPM (**sin cambio**, cumbia a tempo real).

### Perfil emocional (arousal / valence por sección)
Cada sección recibe dos coordenadas en el Plano de Russell:
- **Arousal** (energía percibida, 0–1): 0 = sección silenciosa/suave, 1 = sección más energética de la canción.
- **Valence** (brillo/positividad tímbrica, 0–1): 0 = timbre oscuro/grave, 1 = timbre brillante/agudo.

Esto no es un modelo de ML: son métricas acústicas directas. Sirve para que la selección de playlists y el chat por mood sean más precisos.

### Alertas del análisis
Cuando el sistema detecta que el BPM puede ser incorrecto, lo muestra al analizar:

| Alerta | Significado | Qué hacer |
|--------|-------------|-----------|
| ⚠️ BPM posiblemente sobreestimado | Señal rítmica débil: canción suave/ambient con BPM > 100 | El sistema ya corrigió dividiendo a la mitad si las secciones concordaban |
| ⚠️ BPM de baja confianza | Las secciones no acuerdan el tempo (canción con cambios de velocidad) | Revisar manualmente y corregir en la BD si es necesario |
| ℹ️ Tempo variable | El BPM varía más de 25 entre secciones | Normal en canciones que cambian de carácter (intro lenta + outro rápido) |

## 3. Modos de audio (Hi-Fi vs DJ)
Solo **un** modo usa el DAC a la vez.

- **🟢 Hi-Fi · bit-perfect (por defecto):** el audio suena **en el PC** (`aplay → ALSA exclusivo`) hacia tu DAC **Kiwi Ears Allegro**, a la frecuencia/bits nativos. La web es **mando + visualizador** (no suena en el navegador). Transición = **corte gapless** al punto óptimo (no hay crossfade en bit-perfect). Volumen fijo al 100% (ajústalo en el DAC).
- **🟣 DJ · mezcla:** el audio suena **en el navegador** (Web Audio). Permite crossfade real, barrido de filtro, eco y freno de vinilo + beatmatch. **No** es bit-perfect (remuestrea a 48 kHz).

> ⚠️ En Hi-Fi el DAC queda en **exclusivo**: ninguna otra app sonará por él hasta que pauses o cambies a DJ. Si al cambiar de modo no se oye, espera 1-2 s y recarga (F5).

## 4. Reproducir y mezclar
- **▶/⏸** central, o toca cualquier canción.
- **Transición automática** ~15 s antes del final (su Outro): elige la siguiente y mezcla con el efecto activo (en Hi-Fi es corte gapless).
- **¡MEZCLAR YA!** fuerza la transición al instante sin esperar el final.
- **Efectos** (modo DJ): Crossfade suave · Barrido de filtro · Freno de vinilo · Eco/Delay.

## 5. Chat / asistente por mood
En el panel derecho escribe en lenguaje natural: *"pon algo relajante para estudiar"*, *"quiero entrenar con música rápida"*, *"pon música alegre"*. Filtra por BPM/energía y programa la siguiente.

---

# Parte B — App Android "Cloud-Fi Go"

## 1. Llevar tu música y datos al celular
En el PC:
```bash
python export_library.py        # genera export/library.json (NO uses --copy si la música ya está en el celular)
```
Copia **`library.json`** a la **misma carpeta** donde están tus FLAC en el celular (la app lo detecta por su nombre). No dupliques los audios.

## 2. Importar en la app
1. Pestaña **Player → 📁 Carpeta**.
2. Elige la carpeta con tu música (la que tiene el `library.json`).
3. El aviso dirá *"N pistas (M con BPM/transiciones) · catálogo de la carpeta"*.

## 3. Las 4 pestañas
- **▶ Player** — Now Playing con ⏮ / PLAY / ⏭, **barra de progreso arrastrable**, visualizador de onda y la biblioteca.
- **🎚 Playlists** — tus playlists (importadas del PC o creadas con ➕) y las **automáticas por energía** (mood + BPM). Tócalas para reproducir; 🗑 para borrar; 💾 para guardar una automática.
- **💬 Chat** — comandos offline ("modo combate", "relájate", "sube el ritmo", "enfoque") por texto o 🎤 voz; interruptor **IA** (conversacional, requiere configurar modelo).
- **📈 Sensores** — actividad física (acelerómetro) y control de voz.

## 4. Reproducción inteligente
- Al tocar **cualquier** canción, la app encadena por **BPM más cercano** (octava-aware), como el PC.
- Las **playlists** se reproducen en su orden (ya ordenado por tempo desde el export).
- **Modo Pro** (transición con beatmatch real): en desarrollo — requiere exportar los beats y portar la alineación (ver GUIA_DESARROLLADOR.md).

## 5. Modo actividad (clave)
El **acelerómetro** estima tu intensidad → zona de BPM objetivo (quieto→relax, caminar→enfoque, correr→energía, intenso→**combate**). Override manual con los chips de mood y **voz offline** para casos sedentarios (ej. Warhammer): *"modo combate"*.
