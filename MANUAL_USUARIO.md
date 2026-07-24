# Manual de Usuario — Cloud-Fi 🎧

## ¿Qué es esto?

Un reproductor de música que **analiza tus canciones** y las mezcla solo, como
un DJ. Tiene dos partes:

| | Dónde | Para qué |
|---|---|---|
| 🖥 **Cloud-Fi Estudio** | Tu PC, en el navegador | Escuchar, mezclar y **analizar** tu música |
| 📱 **Cloud-Fi Go** | Tu celular Android | Escuchar sin internet (deporte, viajes) |

El PC hace el trabajo pesado (analizar). El celular solo reproduce lo que el PC
ya analizó.

**Qué necesitas:** una carpeta con música (FLAC, MP3, WAV, OGG o M4A) y un
navegador. Nada más.

---

# Parte A — En tu PC

## Paso 1 · Encender el reproductor

Abre una terminal en la carpeta del proyecto y escribe:

```bash
uv run main.py
```

Luego abre **http://127.0.0.1:8000** en tu navegador.

> **Para apagarlo:** vuelve a esa terminal y pulsa `Ctrl + C`.
> Mientras esté abierta, el reproductor está encendido.

## Paso 2 · Cargar tu música (solo la primera vez)

1. En el panel izquierdo (**Biblioteca**), escribe la carpeta donde tienes tu
   música. Ejemplo: `/home/tu-usuario/Música/`
2. Pulsa **Escanear** y espera.

**Esto tarda.** El programa escucha cada canción entera para sacarle el ritmo y
sus mejores momentos: entre **25 y 60 segundos por canción**. Con 100 canciones,
calcula alrededor de una hora. Déjalo trabajar.

> ✅ **Solo se hace una vez.** Si después agregas canciones nuevas, vuelve a
> pulsar Escanear: solo analizará las nuevas, no repetirá las anteriores.

Al terminar te dirá cuántas se analizaron bien y **cuántas fallaron** (si alguna
está dañada, te dice su nombre).

## Paso 3 · Escuchar

- Toca cualquier canción de la lista para reproducirla.
- **▶ / ⏸** en el centro para pausar y seguir.
- Cuando una canción está por acabar, **el programa elige la siguiente solo** y
  las mezcla. No tienes que hacer nada.
- **¡MEZCLAR YA!** salta a la siguiente en ese momento, sin esperar.

---

## Los dos modos de sonido

Arriba a la derecha hay un botón que cambia entre dos formas de sonar:

### 🟣 DJ · mezcla — **es el modo por defecto**

**Funciona en cualquier computadora, sin configurar nada.** El sonido sale por
el navegador, igual que un video de YouTube.

Es el modo recomendado para empezar y el que usa casi todo el mundo:
- Mezcla las canciones con efectos reales (crossfade, filtros, eco).
- Puedes controlar el volumen desde la web.

### 🟢 Hi-Fi · bit-perfect — **opción avanzada**

Solo si tienes un **DAC** (un aparato externo para audio de alta fidelidad)
ya configurado en tu equipo. Si no sabes lo que es un DAC, **no necesitas este
modo**: quédate en DJ.

En este modo el sonido **no sale por el navegador**, sale directo del PC a tu
DAC sin tocar la calidad original. A cambio:
- No hay mezcla con efectos, solo corte limpio entre canciones.
- El volumen se ajusta en el DAC, no en la web.
- El DAC queda ocupado en exclusiva: ninguna otra aplicación sonará por él
  hasta que vuelvas al modo DJ.

> 💡 **¿Cuál elijo?** Si dudas, deja el modo DJ. Es el que viene puesto.

---

## Chat por estado de ánimo

En el panel derecho puedes pedir música escribiendo normal:

- *"pon algo relajante para estudiar"*
- *"quiero entrenar con música rápida"*
- *"pon música alegre"*

El programa filtra por ritmo y energía y arma la secuencia.

---

# Parte B — En tu celular (Cloud-Fi Go)

## Paso 1 · Preparar los datos en el PC

En la terminal, dentro de la carpeta del proyecto:

```bash
python export_library.py
```

Esto crea el archivo **`export/library.json`**, que es el "resumen" de todo el
análisis.

> ⚠️ **Importante:** haz esto **cada vez que agregues canciones nuevas**. Si no,
> el celular seguirá viendo la lista antigua y las canciones nuevas no
> aparecerán, aunque en el PC sí estén.

## Paso 2 · Pasarlo al celular

Copia **solo el archivo `library.json`** a la **misma carpeta** donde tienes tu
música en el celular.

> No copies los audios otra vez si ya están en el teléfono: ocuparías el doble
> de espacio para nada.

## Paso 3 · Importar en la app

1. Abre la app → pestaña **Player** → botón **📁 Carpeta**.
2. Elige la carpeta donde está tu música (la que tiene el `library.json`).
3. Verás un aviso del tipo *"N pistas · catálogo de la carpeta"*. Listo.

## Las 4 pestañas

| Pestaña | Qué hace |
|---|---|
| ▶ **Player** | Reproducir, barra de progreso, tu biblioteca |
| 🎚 **Playlists** | Tus listas y las automáticas por energía |
| 💬 **Chat** | Órdenes por texto o voz, sin internet ("modo combate", "relájate") |
| 📈 **Sensores** | Detecta si caminas o corres y ajusta la música al ritmo |

## Modo actividad

El celular usa el **acelerómetro** para notar qué tan activo estás y elegir el
ritmo adecuado: quieto → relax, caminando → enfoque, corriendo → energía.

También puedes decirlo por voz, útil cuando estás sentado pero quieres música
intensa (por ejemplo jugando): *"modo combate"*.

---

# Problemas frecuentes

### Agregué canciones y no aparecen

**En el PC:** vuelve a pulsar **Escanear**. Si alguna canción falló, el mensaje
final te dirá su nombre.

**En el celular:** ¿corriste `python export_library.py` después de escanear?
Ese es el paso que suele olvidarse. El celular no ve la biblioteca del PC
directamente, solo lee el `library.json`.

### Una canción no suena o dice "No disponible"

Significa que el archivo ya no está donde estaba (lo moviste, lo borraste, o
estaba en un **disco externo que ahora está desconectado**).

El reproductor lo detecta solo: te avisa y **pasa a la siguiente canción**.

- Si era de un **disco externo**: conéctalo y recarga la página (F5). Vuelven a
  aparecer solas, no se perdió nada.
- Si la **borraste** de verdad: pulsa **Escanear** una vez y se limpiará de la
  lista.

### No se oye nada

1. Confirma que estás en modo **DJ · mezcla** (arriba a la derecha).
2. Sube el volumen en la web y en el sistema.
3. Si estabas en Hi-Fi y cambiaste de modo, espera 2 segundos y recarga (F5).

### El escaneo parece congelado

Es normal: cada canción tarda hasta un minuto. Mira la terminal donde arrancaste
el programa: ahí verás el avance canción por canción.

---

# Para saber más

Este manual cubre el uso diario. Si quieres entender **cómo** analiza la música
(detección de secciones, cálculo de BPM, perfil emocional) o modificar el
código, revisa **GUIA_DESARROLLADOR.md**.
