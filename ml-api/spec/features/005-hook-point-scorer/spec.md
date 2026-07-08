# 005 — Scorer de "punto de enganche" (hook point)

## Qué hace

Dada la serie continua de vectores de 004, puntúa **cualquier** timestamp de
la canción como candidato para *iniciar* un clip corto, según el patrón que
ya se observa en TikTok/Instagram: el clip no arranca en el punto más
energético de la canción, arranca un poco antes, sube hasta abarcar ese pico,
y no corta ahí — sigue hasta que la energía baja a un nivel *parecido* (no
idéntico) al de inicio, para que el arco se sienta resuelto y no cortado a la
mitad.

Para un candidato `t_start`, el algoritmo:

1. Busca el pico local de energía (combinación de `rms`+`onset` del vector
   de 004) dentro de una ventana adelante de `t_start` (ej. 15-45s).
2. Exige que `t_start` **no** esté ya cerca de un pico — debe haber
   crecimiento real entre `t_start` y el pico (penaliza arrancar en la cima).
3. Busca, después del pico, el primer punto `t_end` donde la energía vuelve a
   un nivel cercano al de `t_start` — dentro de una banda de tolerancia (ni
   igual/loop perfecto, ni tan lejos que no se sienta resuelto).
4. Combina: prominencia del pico, pendiente de subida, calidad de la bajada,
   duración total del arco (target ~15-45s, rango típico de un clip corto),
   en un score 0-1.

Devuelve una lista rankeada de candidatos `{t_start, t_peak, t_end, score,
componentes}` para la canción completa — no un único punto "correcto".

## Por qué esto es una heurística y no un modelo entrenado (por ahora)

No existe hoy ningún dataset de "estos timestamps son buenos puntos de
enganche" — ni en este proyecto ni etiquetado a mano. Sin labels no hay señal
de supervisión para entrenar un clasificador. La heurística de forma de curva
(subida-pico-bajada-a-nivel-similar) es lo que se puede construir *ahora* y
generaliza a cualquier canción nueva sin entrenamiento, porque opera sobre la
curva de 004, no sobre un catálogo. Es exactamente el "no es perfecto, funciona
para el 80% de las más populares" que se espera — canciones con estructura
poco convencional (crescendos muy largos, sin picos claros, drones
ambientales) van a puntuar mal en todos los candidatos, y eso es una señal
correcta del scorer, no un bug.

## Camino futuro (fuera de alcance de esta feature)

Si más adelante se registra qué puntos sugeridos el usuario efectivamente usó
o descartó (aceptar/rechazar en la UI), esos serían los labels que hoy no
existen, y ahí sí tendría sentido entrenar un clasificador sobre los vectores
de 004 en vez de la heurística fija. No se planifica ahora por falta de datos.

## Criterios de aceptación

- [ ] Para una canción con un pico claro y aislado (ej. un "drop"), el
      candidato de mayor score tiene su `t_peak` cerca de ese drop y su
      `t_start` claramente antes (no en el mismo bin).
- [ ] `t_end` nunca es igual a `t_start` ni está forzado a coincidir con un
      `transition_point`/`cue_point` ya existente — se deriva sólo de la
      forma de la curva de 004.
- [ ] Canciones sin picos claros (curva plana, ambient) producen scores
      consistentemente bajos en todos los candidatos, no un candidato
      arbitrario con score alto.
- [ ] La función corre sobre una canción no analizada previamente (fuera de
      `library.json`) sin ningún paso adicional de "entrenamiento" —
      confirma la generalización a canciones nuevas.
- [ ] Los pesos de cada componente del score están en constantes nombradas
      (no números mágicos dispersos), para poder ajustarlos al validar contra
      canciones reales.

## Fuera de alcance

- Entrenar un clasificador — ver "Camino futuro".
- Detección de letra/vocals para alinear el hook con una frase cantada —
  sólo señal instrumental (rms/onset/spectral_centroid/chroma).
