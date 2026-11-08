# Plan de implementación: skill `entrevista-ingles`

## Resumen

Skill de Claude Code que simula una entrevista de trabajo en inglés con un panel de
4 entrevistadores que **hablan y escuchan por voz**. Hacen las 15 preguntas del
JOB INTERVIEW SIMULATOR, empezando siempre por la pregunta 1 y las demás al azar, en modo
práctica (15 preguntas) o examen (rondas de 6–8), y al terminar evalúan al candidato con
los 7 criterios y el formato de feedback de 5 puntos de la especificación.

## Hechos comprobados en esta máquina

| Hecho | Consecuencia |
|---|---|
| Windows solo tiene reconocedores es-ES y fr-FR | El reconocimiento nativo no sirve; hace falta Whisper local |
| Windows solo tiene una voz en inglés (Zira) | No alcanza para 4 voces; hacen falta voces neuronales (Zira queda de respaldo) |
| Python 3.14 (por defecto) y 3.12 instalados | Usar 3.12 en un `.venv` por compatibilidad de paquetes compilados |
| Sin ffmpeg | Decodificar audio sin ffmpeg (`soundfile` + `sounddevice`) |
| i5-12500H, 16 GB, RTX 3050 4 GB | Whisper usa la gráfica con las DLL de CUDA de `requirements-gpu.txt`; la CPU queda de respaldo |
| Micrófonos activos: AB13X USB y Realtek; permiso de micrófono concedido | Falta comprobar cuál es el predeterminado y que entregue señal |
| `/voice` de Claude Code solo dicta, no lee respuestas | Hace falta un bucle de voz propio |
| `allowed-tools` solo vale durante el turno que invoca la skill | Toda la entrevista debe ser una cadena continua de llamadas sin terminar el turno |

## Decisiones de arquitectura

1. **Claude Code es el cerebro; los scripts son la boca y el oído.** Claude genera
   reacciones y repreguntas; un script Python habla y escucha. No requiere API key.
2. **Cada turno es una llamada que bloquea:** habla → pita → graba hasta el silencio →
   transcribe → devuelve JSON. Claude decide el siguiente paso y llama de nuevo.
3. **Regla crítica: Claude no puede terminar su turno durante la entrevista.** Nada lo
   reactivaría, porque el usuario habla al micrófono y no escribe en el chat. Cada salida
   JSON incluye un campo `next` que recuerda qué hacer, también tras una compactación.
4. **El script es dueño de las preguntas.** El texto exacto vive en `panel.json` y el orden
   lo sortea el script al crear cada entrevista: la pregunta 1 abre siempre y las demás van
   al azar. Este requisito del usuario sustituye al orden fijo de la especificación
   original. Claude solo aporta una frase de transición, así que no puede saltarse, alterar
   ni inventar preguntas.
5. **Cuatro personajes, no cuatro subagentes.** Lanzar agentes en cada turno añadiría
   latencia y perdería el contexto compartido. Lo que los distingue es la voz, el rol y
   la pregunta asignada.
6. **Rotación estricta de 4, por turno.** Los entrevistadores se turnan por posición, no por
   pregunta. Con el orden al azar, un reparto fijo por pregunta podría dejar a alguno sin
   hablar en una ronda; por turnos, los 4 hablan en cualquier ronda de 6–8. Emma, que dirige
   el panel, abre siempre con la pregunta 1.

   | Entrevistador | Rol | Turnos |
   |---|---|---|
   | Emma | Hiring Manager (dirige el panel) | 1, 5, 9, 13 |
   | Olivia | HR Manager | 2, 6, 10, 14 |
   | Liam | Team Lead | 3, 7, 11, 15 |
   | James | Department Director | 4, 8, 12 |

7. **Rondas de examen con estado en disco.** Por defecto 8 + 7, la única forma de cubrir
   las 15 respetando 6–8 junto con 7 + 8. Si se elige 6, la última ronda puede ser más
   corta. El sorteo se guarda al crear la sesión: al reanudar, la ronda siguiente continúa
   con las preguntas pendientes, sin repetir ni saltar ninguna. Solo una entrevista nueva
   vuelve a empezar por la pregunta 1.
8. **La voz se evalúa con mediciones, no fingiendo oírla.** Claude solo recibe texto, así
   que el script mide ritmo, pausas, muletillas, confianza del reconocedor por palabra,
   variación de tono y volumen. Pronunciación y entonación se presentan como estimaciones
   basadas en esos datos. En modo texto no se evalúa la voz.
9. **Reconocimiento local (`faster-whisper`), síntesis en la nube (`edge-tts`).** La voz
   del usuario no sale de su equipo. El texto de los entrevistadores sí va a Microsoft.
   Sin internet se usa Zira.
10. **No interrumpir tiene prioridad sobre responder rápido.** Se cierra la grabación tras
    un silencio largo (3,5 s por defecto, configurable), para respetar la regla 5.
11. **Ubicación:** skill de proyecto en `.claude/skills/entrevista-ingles/`. El `.venv` y
    las sesiones quedan fuera de la skill para que esta siga siendo ligera.
12. **Transcripción en la gráfica, con la CPU de respaldo.** En esta máquina una respuesta corta
    tarda 0,3 s frente a 1,8 s, con la misma precisión. `setup.py` instala las DLL de CUDA solo si
    detecta una NVIDIA, y si la gráfica falla el script vuelve solo a la CPU.
13. **El informe se guarda con `report`, no con la herramienta de escritura.** `allowed-tools` solo
    cubre el script, y otra herramienta pediría permiso a mitad de la cadena. `close` exige que el
    informe de la ronda exista, para que no se pierda.
14. **`effort: low` en la skill.** Durante la entrevista el esfuerzo apenas cambia la espera, pero
    en la evaluación el esfuerzo máximo añadía dos pausas de unos 75 s. La skill lo limita aunque
    la sesión use el máximo.
15. **Audio completo de cada ronda.** Cada frase del panel se guarda en el momento de decirla,
    junto a las respuestas, y `close` lo une todo en `entrevista-ronda-<n>.mp3`. Guardarlas al
    momento evita tener que sintetizarlas otra vez al final. El volumen se iguala porque el
    micrófono captaba al candidato unos 16 dB por debajo del panel. Si la unión falla, la ronda
    se cierra igual, porque el informe ya está guardado.

## Estructura

```
AgenteEntrevistadorIngles/
├── .claude/
│   └── skills/entrevista-ingles/
│       ├── SKILL.md                   flujo y reglas de la entrevista
│       ├── references/evaluation.md   criterios, feedback, lectura de métricas
│       ├── data/panel.json            4 entrevistadores y 15 preguntas exactas
│       ├── data/config.json           modelo, silencios y dispositivos
│       ├── evals/evals.json           entrevistas simuladas de comprobación
│       └── scripts/
│           ├── interview.py           CLI: doctor, start, say, listen, ask, follow-up, report...
│           ├── session.py             estado de la entrevista
│           ├── voice.py               síntesis, captura, fin de habla, transcripción
│           ├── metrics.py             medidas de voz
│           ├── setup.py               crea .venv, instala dependencias, baja el modelo
│           ├── requirements.txt
│           └── requirements-gpu.txt   DLL de CUDA, solo con gráfica NVIDIA
├── .venv/                             entorno Python (no forma parte de la skill)
├── entrevistas/                       sesiones: estado, audio e informes
├── tests/                             pruebas automáticas
│   └── scenarios/                     candidato con guion y calificación de las simulaciones
└── tasks/                             este plan
```

## Lista de tareas

El detalle y los criterios de aceptación están en `tasks/todo.md`.

### Fase 0: Herramientas
- [x] Tarea 1: Instalar `skill-creator`

### Fase 1: Viabilidad de la voz (lo más arriesgado primero)
- [x] Tarea 2: Entorno reproducible y diagnóstico `doctor`
- [x] Tarea 3: Un turno de voz completo (hecha; la conservación de errores es parcial, ver `todo.md`)

### Punto de control: la voz funciona
- [x] Micrófono, altavoz, 4 voces y transcripción verificados en esta máquina (en la prueba real del 2026-11-07)
- [x] Latencia medida y modelo de Whisper elegido con datos

### Fase 2: Lógica de la entrevista
- [x] Tarea 4: Panel y máquina de estados
- [x] Tarea 5: Medidas de voz
- [x] Tarea 6: CLI completa y modo texto

### Punto de control: entrevista simulada
- [x] Una entrevista completa corre de principio a fin con micrófono simulado

### Fase 3: La skill
- [x] Tarea 7: Escribir la skill con `skill-creator`
- [x] Tarea 8: Funcionamiento sin pedir permisos
- [x] Tarea 9: Evaluaciones de comportamiento

### Punto de control: completo
- [ ] Todos los criterios de aceptación cumplidos (solo queda parcial la conservación de errores en la transcripción)
- [x] Prueba real con la voz del usuario (2026-11-07)

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Whisper corrige la gramática o quita muletillas, y el feedback evalúa un texto más limpio que lo dicho | Alto | `initial_prompt` con disfluencias, medir con frases con errores a propósito y avisar del límite en el informe |
| El usuario hace una pausa larga y se corta su respuesta | Alto | Silencio de 3,5 s configurable, detector probado con audio sintético |
| Claude termina su turno a mitad de entrevista | Alto | Regla explícita en SKILL.md, campo `next` en cada JSON |
| Pedir permiso en cada turno rompe la voz | Alto | `allowed-tools` en la skill, válido durante el turno de la entrevista. Una regla permanente en `.claude/settings.json` queda a decisión del usuario: el modo automático bloqueó que la añadiera Claude |
| Latencia incómoda entre respuesta y pregunta | Medio | Medirla, elegir modelo con datos, pitidos de inicio y fin |
| Micrófono equivocado por defecto | Medio | `doctor` muestra el dispositivo y permite fijarlo por configuración |
| `edge-tts` es un servicio no oficial y puede fallar | Medio | Respaldo automático a Zira con aviso |
| Una compactación hace perder la entrevista | Medio | Estado en disco; comandos `status` y `summary` lo recuperan |
| No poder probar con voz humana sin el usuario | Medio | Micrófono simulado con WAV; la prueba real queda como paso explícito del usuario |

## Preguntas abiertas (con valor por defecto, no bloquean)

- **Idioma del feedback:** inglés, como la especificación. Se puede pedir en español.
- **Nivel de inglés:** se estima a partir de las respuestas, sin preguntar antes, porque
  la especificación solo pide confirmar el modo.
- **Tamaño de ronda en examen:** 8 si el usuario no indica otro.
