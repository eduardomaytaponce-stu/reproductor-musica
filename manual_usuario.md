# Manual de Usuario: Reproductor Inteligente FLAC & DJ AI 🎧🤖

Este manual te guiará paso a paso para comenzar a reproducir y mezclar tu música favorita una vez finalizada la **Fase 4 (Interfaz Web Premium y Mixer DSP)**.

---

## 🚀 Paso 1: Iniciar el Servidor de Música
Asegúrate de estar en la carpeta del proyecto en tu terminal y arranca el backend:
```bash
uv run main.py
```
*El terminal te indicará que el servidor está corriendo en:* `http://127.0.0.1:8000`

---

## 🌐 Paso 2: Abrir la Interfaz de Usuario
Abre tu navegador de preferencia (se recomienda Google Chrome, Brave o Firefox para la mejor compatibilidad con Web Audio API) e ingresa a:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

Verás la interfaz Glassmorphism con el plato de vinilo giratorio en el centro, la lista de canciones a la izquierda y el asistente de chat a la derecha.

---

## 📁 Paso 3: Cargar y Escanear tus Canciones (Tu Primera Vez)
1. En el panel izquierdo de **Biblioteca FLAC**, verifica que la ruta sea `/home/carloseduardo/Música/`.
2. Haz clic en el botón **Escanear**.
3. El reproductor comenzará a analizar los archivos nuevos en segundo plano. Las canciones aparecerán automáticamente en la lista a medida que se procesen.

---

## 🎚️ Paso 4: Elegir el Modo de Audio (Hi-Fi vs DJ)

El reproductor tiene **dos modos**, conmutables con el interruptor de la esquina del panel central. **Solo un modo posee la interfaz de audio (DAC) a la vez.**

### 🟢 Modo Hi-Fi · bit-perfect (por defecto)
- **Qué es**: el audio se reproduce **en el equipo servidor** (backend `mpv → ALSA exclusivo`) directamente a tu DAC **Kiwi Ears Allegro**, a la frecuencia y profundidad **nativas** del archivo (ej. 96 kHz/24-bit salen intactos). Es la misma ruta que VLC en modo exclusivo, o mejor.
- **La web es un MANDO a distancia + visualizador**: el navegador no reproduce sonido, solo envía órdenes (play/pausa/siguiente) y muestra el espectro (sincronizado al BPM real).
- **Transiciones**: **corte gapless inteligente** al punto óptimo (sin crossfade ni efectos: es físicamente imposible mezclar dos pistas en un flujo bit-perfect).
- **Volumen**: fijo al 100%; ajústalo en el DAC o el sistema (así no se alteran los bits).
- La insignia del banner muestra en vivo la calidad real, p. ej. `96.0 kHz · s32 · BIT-PERFECT`.

### 🟣 Modo DJ · mezcla
- **Qué es**: el audio se reproduce **en el navegador** (Web Audio API). Permite **crossfade real, barrido de filtro, eco y freno de vinilo**, además de beatmatch.
- **Calidad**: **no bit-perfect** (el navegador remuestrea a 48 kHz). Suena bien, pero no a resolución nativa.
- Úsalo cuando quieras las mezclas creativas o cuando necesites que la música conviva con otras apps (ver aviso abajo).

> [!WARNING]
> **Modo exclusivo y juegos/otras apps.** Mientras el **modo Hi-Fi** está reproduciendo, toma el DAC en **exclusivo**: ninguna otra app (un juego, el navegador, sonidos del sistema) podrá usar **ese mismo DAC** hasta que pauses o cambies a modo DJ. No bloquea el juego (sigue corriendo), pero no sonará por el Kiwi. Y al revés: si otra app ya está usando el DAC, el modo Hi-Fi **fallará al abrirlo**; cierra esa app primero.
> **Regla práctica**: usa **Hi-Fi** para sesiones de escucha dedicada y **DJ/compartido** cuando juegues o trabajes con audio de varias apps a la vez. Bit-perfect exclusivo y compartir el DAC son mutuamente excluyentes por naturaleza.

> [!NOTE]
> **Escalabilidad / multiusuario.** El modo Hi-Fi es un modelo de **un equipo, un DAC, un oyente** (el de la máquina servidor): si abres la web desde otro dispositivo, el sonido sale del DAC del servidor, no del tuyo. Para varios usuarios o equipos sin DAC, usa el **modo DJ** (cada quien reproduce en su propio dispositivo, no bit-perfect).

> [!CAUTION]
> **Al cambiar entre modos (Hi-Fi ⇄ DJ).** El cambio cede el DAC de un motor al otro. Si tras cambiar a **DJ** no se oye nada, o al cambiar de canción no suena:
> 1. Espera 1–2 s (el sistema de audio está reconfigurando el dispositivo).
> 2. Si sigue sin sonar, **recarga la página (F5)** y vuelve a reproducir.
> 3. Asegúrate de que ninguna otra app tenga tomado el DAC.
> *(Estamos endureciendo este traspaso; por ahora recargar es el atajo fiable.)*

---

## 🎵 Paso 5: Controlar la Reproducción y las Mezclas DJ
- **Reproducir/Pausar**: Haz clic en el botón grande central `▶`/`⏸` o selecciona directamente cualquier canción de la lista.
- **Transición Automática**: Cada canción tiene programada una autodetección a los **15 segundos antes de terminar** (su sección de Outro). El reproductor seleccionará la siguiente pista y ejecutará la transición automáticamente. *(En Hi-Fi es un corte gapless; en DJ es el efecto de mezcla que tengas seleccionado.)*
- **Efectos de Transición**: Puedes alternar en tiempo real el efecto de mezcla:
  - **Crossfade Suave**: Atenuación y ganancia cruzada tradicional.
  - **Barrido de Filtro**: Corte progresivo de agudos mediante un filtro Pasa-Bajos.
  - **Freno de Vinilo**: Parada simulada por fricción en el deck saliente.
  - **Eco/Cola de Delay**: Desvanecimiento espacial de la pista activa mientras la nueva entra con fuerza.
- **Mezclar Ya!**: Si deseas cambiar de canción inmediatamente sin esperar a que termine, haz clic en **¡MEZCLAR YA!** para activar la transición DSP seleccionada al instante.

---

## 💬 Paso 6: Hablar con tu DJ de Inteligencia Artificial
En el panel derecho, escribe peticiones en lenguaje natural para que el DJ analice tu estado de ánimo:
- *“Pon algo relajante para estudiar”* (Filtra canciones de BPM bajo y tonos suaves).
- *“Quiero entrenar con música rápida”* (Busca canciones de alta energía y alto BPM).
- *“Pon música alegre”* (Selecciona pistas con ritmos vibrantes).

El asistente te responderá de inmediato y programará la canción en el Deck B para iniciar la transición.

---

## 📊 Estimación de Tiempo para Escaneo Completo

Actualmente tienes **143 archivos de audio** detectados en tu carpeta `/home/carloseduardo/Música/`.

### ⏱ ¿Cuánto tiempo tomará escanear toda tu biblioteca?
- **Tiempo promedio por canción**: De **15 a 25 segundos** (el análisis extrae BPM precisos, RMS, Chroma y centroide espectral por ventanas de tiempo usando CPU local).
- **Escaneo total estimado**: Aproximadamente de **35 a 60 minutos** para las 143 canciones en tu primer arranque.

> [!IMPORTANT]
> **El análisis se realiza una única vez por canción.**
> Una vez procesadas, las pistas se guardan de forma permanente en la base de datos `music_library.db`. Las siguientes veces que inicies el reproductor, la carga de tu biblioteca será **instantánea (menos de 50 ms)**.
>
> Además, el escáner es **incremental e inteligente**: si agregas canciones nuevas en el futuro, el escáner se saltará en milisegundos las canciones que ya estén en la base de datos y solo analizará las nuevas.
