# Tasks — 005

- [x] Implementar `energia_normalizada`, `_score_candidato`,
      `mejores_puntos_enganche` en `hook_scorer.py`.
- [x] Validar con Arctic Monkeys - 505 (tiene un pico marcado de nivel_10 en
      t=173-180s según el análisis DSP existente): el candidato #2 de la
      heurística dio `t_peak=168s` — a un solo bin (3s) del pico real, sin
      que el scorer supiera de antemano dónde estaba. El top-1
      (`t_start=27, t_peak=51, t_end=54`) corresponde a la subida hacia el
      primer estribillo (energía sube de nivel_4 a nivel_7 entre t=19 y t=40
      en los cue_points existentes).
- [ ] Canción sin picos claros (ambient/drone): **no se pudo validar** — la
      librería actual (música curada personal) no tiene pistas puramente
      ambient. Se probó con una balada relax (Café Tacvba - Eres) y el
      scorer sí encontró arcos de score medio-alto (0.55-0.65): la
      normalización es relativa a la propia canción, así que incluso una
      balada con dinámica interna real (verso→coro) produce candidatos.
      Esto es razonable (una balada sí tiene una forma), pero significa que
      el criterio de aceptación "scores consistentemente bajos en canciones
      sin estructura" queda sin validar con un caso verdaderamente plano.
- [x] Exponer `POST /hook-points` — probado con curl, responde en ~1.9s.
- [x] Pesos usados: `PESO_PROMINENCIA=0.4, PESO_SUBIDA=0.3, PESO_BAJADA=0.2,
      PESO_DURACION=0.1`, banda de retorno `[0.03, 0.28]` (escala 0-1),
      arco entre 15-45s. No se ajustaron contra más canciones por falta de
      tiempo — son los valores iniciales del plan, funcionan razonablemente
      en las 2 canciones probadas pero no están calibrados a escala.
