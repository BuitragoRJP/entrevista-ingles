# Tareas: skill `entrevista-ingles`

Plan y decisiones en `tasks/plan.md`.

## Estado al 2026-11-07

Comprobado con el código final, con `--model opus --effort max` y sin saltar permisos:

| Prueba | Resultado |
|---|---|
| `pytest tests` | 74 pasan |
| Examen de 6 por voz, con el audio completo | 21/21 |
| Práctica de 15 por voz, con el sorteo real (antes del audio completo) | 19/19 |
| Examen de 6 por escrito, pedido con una frase natural (antes del audio completo) | 16/16 |
| Examen 8 + 7 entero por línea de comandos, con el sorteo real | Correcto: las 15 preguntas, una vez cada una |
| `setup.py` y `doctor` en un proyecto vacío, con caché de modelos vacía | Correcto: 94 s con la caché de `pip`, 2,5 GB; repetir tarda 6 s |

`effort: low` se respeta según los tiempos. Con el mismo esfuerzo máximo, sin esa línea el examen
tardaba 288 s, con pausas de 76 s y 74 s en la evaluación; con ella tarda unos 115 s, y la mayor pausa
de las evaluaciones finales fue de 24 s en el examen y 33 s en la práctica.

Prueba real hecha el 2026-11-07 con `/entrevista-ingles`, en la sesión `entrevistas/2026-11-07_020531`:
práctica completa por voz, con 15 preguntas y 18 respuestas grabadas. El usuario la dio por buena. El
micrófono captó la voz baja, a −39 dBFS, y una respuesta se cortó mientras el usuario pensaba.

### Audio completo de la ronda

Lo pidió el usuario tras la prueba real, porque las grabaciones solo tenían su voz.

- [x] Cada frase del panel se guarda en `audio/panel-NNN.wav`, y la sesión anota en `recording` el orden
  de todos los tramos
- [x] `close` une la ronda en `entrevista-ronda-<n>.mp3` con el volumen igualado. Si la unión falla, la
  ronda se cierra igual y devuelve `audio_error`
- [x] En el modo texto no se graba audio

Verificación:
- `pytest`: 74 pasan, con dos pruebas nuevas, primero en rojo.
- Examen simulado por voz: 21/21, con dos comprobaciones nuevas:
  - el MP3 incluye las 11 intervenciones del candidato;
  - Claude dice dónde quedó el audio.
- Sesión real: se le añadieron las frases del panel, sintetizadas otra vez con su texto exacto y las mismas
  voces, y el MP3 se rehízo con el código de la skill:
  - 60 tramos en 16,5 minutos;
  - cortado el MP3 por tramos y transcrito, cada tramo coincide con su original (mediana de parecido 1,00);
  - volumen: el panel queda a −19,9 dBFS y el candidato a −20,0 dBFS; antes estaba a −32,7 dBFS.

Las evaluaciones se lanzan de una en una y en primer plano: Claude Code detuvo por falta de memoria
las que corrían en segundo plano.

## Fase 0: Herramientas

### Tarea 1: Instalar `skill-creator`

**Descripción:** Instalar la skill oficial de creación de skills. El nombre pedido,
`create-skills`, lo usan varios autores con muy poca adopción; la de referencia es
`anthropics/skills@skill-creator`.

**Criterios de aceptación:**
- [x] Aparece en `~/.claude/skills/skill-creator` con su `SKILL.md`
- [x] Se leyó su contenido antes de seguir sus instrucciones

**Verificación:**
- [x] `npx skills list -g` la muestra

**Dependencias:** Ninguna
**Archivos:** ninguno del proyecto
**Alcance:** XS

## Fase 1: Viabilidad de la voz

### Tarea 2: Entorno reproducible y diagnóstico

**Descripción:** Un comando crea el `.venv` con Python 3.12, instala dependencias y
descarga el modelo. `doctor` comprueba de forma real cada pieza de la voz.

**Criterios de aceptación:**
- [x] `setup.py` deja el entorno listo y puede ejecutarse dos veces sin romper nada
- [x] `doctor` informa dispositivo de entrada, salida y señal real del micrófono
- [x] `doctor` genera audio con las 4 voces y distingue fallo de cada componente

**Verificación:**
- [x] Ejecutar `setup.py` y `doctor` en esta máquina y revisar el JSON
- [x] Manual: la señal del micrófono no es silencio digital

**Dependencias:** Ninguna
**Archivos:** `scripts/setup.py`, `scripts/requirements.txt`, `scripts/voice.py`, `scripts/interview.py`
**Alcance:** M

### Tarea 3: Un turno de voz completo

**Descripción:** Hablar con una voz, avisar con un pitido, grabar hasta el silencio y
devolver la transcripción. Elegir el modelo de Whisper midiendo tiempos y precisión.

**Criterios de aceptación:**
- [x] El detector de fin de habla no corta pausas menores a 3,5 s y cierra tras ellas
- [ ] Los errores gramaticales de un audio de prueba se conservan en la transcripción (parcial: 17 de 18 con voz nativa y 13 de 18 con acento; ver la tabla)
- [x] El silencio total devuelve `no_speech`, sin texto inventado

**Verificación:**
- [x] `pytest tests/test_voice.py` con audio sintético
- [x] Tabla de latencia y precisión por modelo registrada en este archivo

**Dependencias:** Tarea 2
**Archivos:** `scripts/voice.py`, `tests/test_voice.py`
**Alcance:** S

#### Medición de modelos de Whisper (2026-11-06)

Frases con 18 errores gramaticales puestos a propósito, leídas por una voz nativa y por una con
acento hispano. Tiempo relativo a la duración del audio, en CPU.

| Modelo | Haz | Errores conservados, nativa | Errores conservados, acento | Tiempo |
|---|---|---|---|---|
| base.en | 5 | 15/18 | 10/18 | 0,75 (además inventa repeticiones) |
| **small.en** | **1** | **17/18** | **13/18** | **1,06** |
| small.en | 5 | 17/18 | 13/18 | 1,13 |
| medium.en | 1 | 16/18 | 14/18 | 2,72 |
| medium.en | 5 | 16/18 | 13/18 | 2,88 |

Elegido `small.en` con haz 1. Límites conocidos: «must to finish» siempre sale como «must have
finished», y el acento puede cambiar una palabra entera («I has worked» salió como «He has worked»).

#### Velocidad de `small.en` por dispositivo (2026-11-06)

| Dispositivo | Respuesta corta | 1 minuto | 2 minutos |
|---|---|---|---|
| **Gráfica RTX 3050, `int8_float16`** | **0,3 s** | **1,5 s** | **3,3 s** |
| CPU, 12 hilos | 1,8 s | 5,7 s | 11,2 s |
| CPU, 8 hilos | 2,3 s | | |
| CPU, 6 hilos | 2,5 s | | |
| CPU, 4 hilos | 3,0 s | | |

La gráfica conserva los mismos errores que la CPU. Usa la gráfica si puede y vuelve sola a la CPU
con 12 hilos si falla.

### Punto de control: la voz funciona
- [x] Micrófono, altavoz, 4 voces y transcripción verificados (en la prueba real del 2026-11-07)
- [x] Latencia medida y modelo elegido

## Fase 2: Lógica de la entrevista

### Tarea 4: Panel y máquina de estados

**Descripción:** `panel.json` guarda las 15 preguntas literales y los 4 entrevistadores;
`session.py` controla modo, rondas, orden, repreguntas y reanudación.

**Criterios de aceptación:**
- [x] Las 15 preguntas coinciden carácter a carácter con la especificación
- [x] Toda entrevista nueva abre con la pregunta 1 y sortea las demás
- [x] Máximo una repregunta por pregunta; sin repetir ni saltar preguntas
- [x] Una ronda de examen 6–8 incluye a los 4 entrevistadores y se reanuda donde quedó

**Verificación:**
- [x] `pytest tests/test_session.py`

**Dependencias:** Ninguna
**Archivos:** `data/panel.json`, `scripts/session.py`, `tests/test_session.py`
**Alcance:** S

### Tarea 5: Medidas de voz

**Descripción:** Calcular a partir del audio y de la transcripción ritmo, pausas,
muletillas, repeticiones, confianza por palabra, tono y volumen.

**Criterios de aceptación:**
- [x] Ritmo, pausas y muletillas son correctos sobre casos construidos a mano
- [x] Una voz plana y una variada dan resultados de tono claramente distintos
- [x] Si una medida falla o no aplica devuelve `null`, nunca un valor inventado

**Verificación:**
- [x] `pytest tests/test_metrics.py`

**Dependencias:** Tarea 3
**Archivos:** `scripts/metrics.py`, `tests/test_metrics.py`
**Alcance:** S

### Tarea 6: CLI completa y modo texto

**Descripción:** `interview.py` une todo: `start`, `say`, `listen`, `ask`, `follow-up`,
`status`, `summary`, `close`, más un micrófono simulado para pruebas y el modo texto.

**Criterios de aceptación:**
- [x] Cada comando devuelve JSON válido en UTF-8 con un campo `next`
- [x] El avance solo ocurre con una respuesta válida; `ask --repeat` no consume pregunta
- [x] Las respuestas escritas no llevan medidas de voz

**Verificación:**
- [x] `pytest tests/test_cli.py` con una entrevista completa simulada

**Dependencias:** Tareas 3, 4 y 5
**Archivos:** `scripts/interview.py`, `tests/test_cli.py`
**Alcance:** M

### Punto de control: entrevista simulada
- [x] Práctica de 15 y examen 8 + 7 corren enteros con micrófono simulado

## Fase 3: La skill

### Tarea 7: Escribir la skill con `skill-creator`

**Descripción:** Redactar `SKILL.md` y `references/evaluation.md` siguiendo el proceso de
`skill-creator`, recogiendo todas las reglas de la especificación.

**Criterios de aceptación:**
- [x] Cubre las partes 1 a 5 de la especificación
- [x] Deja explícita la regla de no terminar el turno durante la entrevista
- [x] El feedback tiene los 5 puntos y los 7 criterios

**Verificación:**
- [x] La skill aparece en la lista y se puede invocar con `/entrevista-ingles`
- [x] `SKILL.md` tiene menos de 500 líneas

**Dependencias:** Tarea 6, Tarea 1
**Archivos:** `SKILL.md`, `references/evaluation.md`
**Alcance:** S

### Tarea 8: Funcionamiento sin pedir permisos

**Descripción:** Evitar que un aviso de permiso interrumpa la entrevista por voz con
`allowed-tools` en la skill, limitado a `interview.py`. Cambio respecto al plan inicial: el
modo automático bloqueó que Claude añadiera una regla permanente a `.claude/settings.json`
(autoconcesión de permisos). No se intenta por otra vía: esa regla queda a decisión del usuario.

**Criterios de aceptación:**
- [x] `allowed-tools` solo cubre el script de la entrevista
- [x] Los comandos del flujo real encajan con el patrón

**Verificación:**
- [x] Ejecutar la skill en una sesión nueva sin indicadores que salten permisos

**Dependencias:** Tarea 7
**Archivos:** `SKILL.md`
**Alcance:** XS

### Tarea 9: Evaluaciones de comportamiento

**Descripción:** Comprobar con `skill-creator` y micrófono simulado que un agente sigue
las reglas: orden exacto, sin feedback antes de tiempo, sin pistas, sin evaluar la voz en
modo texto.

**Criterios de aceptación:**
- [x] Las evaluaciones de modo práctica, examen y modo texto pasan
- [x] Corregidas las fallas encontradas en la skill

**Verificación:**
- [x] Resultados de las evaluaciones revisados

**Dependencias:** Tareas 7 y 8
**Archivos:** `evals/evals.json`, `SKILL.md`
**Alcance:** M

### Punto de control: completo
- [ ] Todos los criterios de aceptación cumplidos (solo queda parcial la conservación de errores en la transcripción)
- [x] Prueba real con la voz del usuario: `/entrevista-ingles` (2026-11-07)
