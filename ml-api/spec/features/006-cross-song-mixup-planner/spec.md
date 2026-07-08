# 006 — Planificador de mixup entre dos canciones

## Qué hace

Dadas dos canciones (A y B — cualquiera de las dos puede ser nueva, no
requiere estar en la librería), produce un **plan de edición ordenado**: qué
tramo de A usar, en qué punto pasar a B, qué tramo de B usar, y con qué
parámetros de transición — pensado para armar el soundtrack de un video con
ambas canciones, agrupando tramos por sentimiento/BPM en vez de fusionarlas
de golpe.

Pipeline (todo reutilizando piezas ya existentes, ninguna se reimplementa):

1. Si A o B no están en la librería, correr `analyzer.py` +
   `extraer_vector_track` (004) sobre ellas — no hace falta que ya existan
   en `music_library.db`.
2. Correr `mejores_puntos_enganche` (005) sobre A → candidatos de **salida**
   (usamos `t_end` de cada arco de A como posible punto de corte: ya resolvió
   su propio arco, es un lugar natural para ceder el paso a B). Correr sobre
   B → candidatos de **entrada** (usamos `t_start` de cada arco de B: el
   punto donde B empieza a construir su propio pico).
3. Agrupar los candidatos de A y B por nivel de energía/sentimiento (mismo
   `arousal` que ya usan `macro_sections`) — igual que
   `ordenar_cola_por_tempo` ya encadena canciones por BPM cercano, aquí se
   encadenan *tramos* por arousal cercano, para que el salto A→B no sea un
   cambio brusco de intensidad.
4. Para cada par candidato `(salida_A, entrada_B)` compatible en
   arousal/BPM, llamar a `calcular_transicion_optima` (`transition.py`,
   **sin modificar**) pasándole los vectores locales de esos puntos — ya
   decide tipo de transición, duración, beatmatching.
5. Rankear los pares por: score de 005 de ambos lados + compatibilidad de
   `calcular_transicion_optima` (bpm_compatibles, acordes_compatibles) +
   cercanía de arousal.
6. Devolver el mejor plan: `{tramo_A: [0, t_salida], transicion: {...de
   transition.py...}, tramo_B: [t_entrada, fin]}`, más las siguientes N
   mejores alternativas por si el resultado top no convence a ojo.

## Por qué no fusionar todo el catálogo de puntos con todo el catálogo

Con 004 dando ~80 bins por canción y 005 dando varios candidatos por canción,
comparar cada candidato de A contra cada uno de B es manejable (decenas ×
decenas, no miles) — no hace falta indexar ni aproximar vecinos, un
doble-loop simple con el filtro de arousal/BPM primero (descarta la mayoría
de pares antes de llamar a `calcular_transicion_optima`, que es lo más caro
de los tres) alcanza.

## Respuesta directa a la duda del usuario: ¿esto sólo funciona para
## canciones que ya conoce?

No. El pipeline completo (004 → 005 → agrupar por arousal → 006) es DSP +
heurísticas sobre la señal de audio de A y B, no una tabla de canciones
conocidas. Cualquier par de canciones nuevas puede pasar por los mismos 3
pasos. Lo único que "conoce" de antemano es el clasificador de mood de 001
(entrenado sobre las 160 canciones etiquetadas) — si se usa aquí, es sólo
para poner una etiqueta legible (relax/enfoque/energía/acción) al tramo en el
plan de salida, no para decidir la compatibilidad, que corre siempre sobre
`arousal` (ya derivado de la curva, no del clasificador).

## Criterios de aceptación

- [ ] Corre sobre dos canciones que no están en `music_library.db` (verificar
      explícitamente con dos archivos de audio fuera de la librería actual).
- [ ] El plan devuelto nunca corta A exactamente en su punto de mayor
      energía absoluta (usa el `t_end` de un arco de 005, que por diseño ya
      pasó el pico y bajó).
- [ ] Si ningún par de candidatos supera un umbral mínimo de compatibilidad
      (BPM+arousal), la respuesta lo dice explícitamente
      (`plan_encontrado: false` + razón) en vez de forzar el par menos malo
      sin avisar.
- [ ] El plan incluye los parámetros de `calcular_transicion_optima` sin
      reimplementarlos (tipo de transición, duración, beatmatch) — 006 sólo
      decide *qué puntos* pasarle, no *cómo* transicionar.
- [ ] Documentado con un ejemplo real: dos canciones de géneros/BPM distintos
      de la librería, plan resultante con timestamps concretos.

## Fuera de alcance

- Renderizar el audio/video final (mezclar los archivos, exportar un .mp4 o
  .flac editado) — esta feature sólo devuelve el **plan** (timestamps +
  parámetros), no ejecuta la edición.
- Más de dos canciones en un mismo plan — se deja para una iteración futura
  si ésta funciona bien con pares.
- Garantizar un resultado para el 100% de los pares — el criterio de
  aceptación del usuario es ~80% en canciones populares, no cobertura total.
