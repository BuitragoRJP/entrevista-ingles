# Entrevista de trabajo en inglés por voz

Skill de [Claude Code](https://claude.com/claude-code) que simula una entrevista de trabajo en inglés con
un panel de cuatro entrevistadores que hablan y te escuchan. Contestas en voz alta por el micrófono y, al
terminar, recibes una evaluación de tu inglés y de tus respuestas.

No necesitas clave de API: la entrevista la dirige Claude dentro de tu sesión de Claude Code.

## Qué hace

| Entrevistador | Cargo | Voz |
|---|---|---|
| Emma Carter | Hiring Manager, dirige el panel | Inglés de Estados Unidos |
| Olivia Bennett | HR Manager | Inglés de Australia |
| Liam Walker | Team Lead | Inglés de Canadá |
| James Whitfield | Department Director | Inglés británico |

- **Preguntas:** hace 15 preguntas clásicas de entrevista. Siempre empieza por *Can you tell me a little
  about yourself?* y el resto va en orden aleatorio.
- **Durante la entrevista:** el panel reacciona con naturalidad y puede repreguntar una vez si tu
  respuesta es corta o no contesta la pregunta. No corrige, no da pistas y no opina hasta el final.
- **Evaluación:** valora 7 criterios: contenido, gramática, vocabulario, coherencia, fluidez,
  pronunciación y entonación, y comunicación profesional. Estima tu nivel en la escala CEFR y entrega un
  informe con cinco apartados: puntos fuertes, errores corregidos, vocabulario mejor, áreas de mejora y
  nota de 1 a 10. Después cada entrevistador comenta en voz alta su área.
- **Audio:** al terminar cada ronda queda un MP3 con la entrevista completa, las preguntas del panel y tus
  respuestas, para que puedas volver a escucharla.

## Requisitos

- Windows 10 u 11. Solo se ha probado en Windows 11.
- Claude Code.
- Python 3.12 instalado desde [python.org](https://www.python.org/downloads/), que incluye el lanzador `py`.
- Micrófono y auriculares o altavoces.
- Conexión a internet para las voces de los entrevistadores.
- Unos 2,5 GB de disco con una gráfica NVIDIA. Unos 1,8 GB de ellos son librerías de CUDA, que solo se
  instalan si hay una gráfica NVIDIA y aceleran la transcripción.

## Instalación

1. Clona el repositorio y abre Claude Code en su carpeta:

   ```
   git clone https://github.com/BuitragoRJP/entrevista-ingles.git
   cd entrevista-ingles
   claude
   ```

2. Escribe `/entrevista-ingles`. La primera vez, la skill prepara lo necesario: crea un entorno de Python
   en `.venv`, instala las dependencias y descarga el modelo de reconocimiento de voz. Claude Code te pedirá
   permiso para ejecutar la instalación, que tarda unos minutos.

Si prefieres instalarla tú antes, ejecuta en la carpeta del proyecto:

```
python .claude/skills/entrevista-ingles/scripts/setup.py
```

Se puede repetir sin problema: lo que ya está instalado no se vuelve a instalar.

### Usarla en otro proyecto

Copia la carpeta `.claude/skills/entrevista-ingles` dentro de la carpeta `.claude/skills/` de tu proyecto.
El entorno de Python se creará en la raíz de ese proyecto. No funciona en `~/.claude/skills`, porque los
comandos usan rutas relativas a la raíz del proyecto.

## Uso

| Escribe | Qué pasa |
|---|---|
| `/entrevista-ingles` | Emma te pregunta por voz qué modo prefieres |
| `/entrevista-ingles practica` | Práctica completa con las 15 preguntas |
| `/entrevista-ingles examen` | Examen en rondas de 6 a 8 preguntas |
| `/entrevista-ingles texto` | La entrevista por escrito, sin micrófono |

También puedes pedirlo con tus palabras, por ejemplo «quiero practicar mi entrevista en inglés». En ese
caso Claude Code te pedirá aprobar la skill una vez.

### Modos

- **Práctica:** las 15 preguntas seguidas y la evaluación al final.
- **Examen:** rondas de 6 a 8 preguntas, 8 si no indicas otro número, con evaluación al final de cada
  ronda. Con 8 harías una ronda de 8 y otra de 7. La siguiente ronda empieza cuando la pidas y nunca repite
  preguntas.
- **Texto:** escribes las respuestas en el chat. La pronunciación y la voz no se evalúan.

### Durante la entrevista

- Habla después del pitido agudo, que indica que el micrófono está abierto.
- Puedes hacer pausas para pensar. La grabación termina tras 3,5 segundos de silencio y un pitido más
  grave lo confirma.
- No hace falta tocar el teclado: todo es por voz.
- Si no hablas en 60 segundos, el entrevistador vuelve a hacer la pregunta. Cada respuesta puede durar
  hasta 4 minutos.
- Puedes pedir que repitan la pregunta, por ejemplo con *Could you repeat the question, please?* Si pides
  ayuda o un ejemplo de respuesta, el panel te pedirá que contestes con tus palabras.
- Si quieres parar, dilo: el panel evaluará lo que hayas respondido hasta ese momento.

### Resultado

El informe aparece en el chat. Cada entrevista se guarda en su propia carpeta dentro de `entrevistas/`:

```
entrevistas/<fecha y hora>/
├── informe-ronda-<n>.md        informe de la ronda
├── entrevista-ronda-<n>.mp3    audio completo de la ronda
├── audio/                      cada frase del panel y cada respuesta tuya, por separado
└── session.json                estado: orden de las preguntas, transcripciones y medidas de voz
```

El MP3 reúne las preguntas del panel y tus respuestas en el orden en que sonaron. El volumen se iguala para
que tus respuestas se oigan tan alto como el panel. En un examen hay un informe y un MP3 por ronda.

Una práctica completa ocupa unos 80 MB. En el modo texto no se graba audio.

## Privacidad

- Tu voz se graba y se transcribe en tu equipo. Las grabaciones, incluido el MP3 de cada ronda, se guardan
  en la carpeta `entrevistas/`, que el `.gitignore` deja fuera del repositorio.
- Claude lee las transcripciones de tus respuestas para dirigir la entrevista y evaluarte, como en
  cualquier conversación de Claude Code.
- Las frases de los entrevistadores se envían a Microsoft para generar sus voces, a través de la librería
  `edge-tts`. Sin conexión habla la voz de Windows, igual para los cuatro.

## Límites

- **La transcripción no es perfecta.** Puede corregir errores pequeños o cambiar una palabra: en las
  pruebas, «I has worked» se transcribió como «He has worked». Con frases que tenían 18 errores puestos a
  propósito, conservó 17 con voz nativa y 13 con acento hispano. Toma la nota de gramática como orientativa.
- **La pronunciación se estima.** Claude no escucha tu voz: la valora a partir de medidas como el ritmo,
  las pausas, la variación del tono, el volumen y la confianza del reconocedor.
- **Hay que esperar un poco entre preguntas.** El panel espera 3,5 segundos de silencio para no
  interrumpirte, y después necesita unos segundos más para contestar.
- **Solo funciona en Windows.** Usa rutas y la voz de respaldo de Windows.
- **Consume uso de Claude.** En las pruebas con un candidato simulado, cada entrevista con Opus gastó el
  equivalente a entre 0,40 y 0,65 dólares.

## Configuración

Los ajustes están en `.claude/skills/entrevista-ingles/data/config.json`:

| Opción | Valor inicial | Para qué sirve |
|---|---|---|
| `end_silence_s` | `3.5` | Segundos de silencio que cierran tu respuesta. Súbelo si te corta mientras piensas |
| `start_timeout_s` | `60` | Segundos que espera a que empieces a hablar |
| `max_answer_s` | `240` | Duración máxima de una respuesta, en segundos |
| `input_device` | `null` | Parte del nombre del micrófono. Con `null` usa el predeterminado de Windows |
| `output_device` | `null` | Parte del nombre de los auriculares o altavoces |
| `whisper_device` | `"auto"` | Pon `"cpu"` si la gráfica da problemas. Cada respuesta tardará unos 2 segundos más |
| `whisper_model` | `"small.en"` | Modelo de reconocimiento de voz |
| `speech_rate` | `"+0%"` | Velocidad de las voces, por ejemplo `"-10%"` para que hablen más despacio |

Para ver el nombre de tus dispositivos de audio, pídele a Claude que los liste o ejecuta:

```
.venv\Scripts\python.exe .claude\skills\entrevista-ingles\scripts\interview.py devices
```

### Evitar avisos de permiso

Con `/entrevista-ingles`, la entrevista por voz no pide permisos. Si usas el modo texto o la pides con tus
palabras, Claude Code te pedirá aprobaciones. Para evitarlas, crea `.claude/settings.local.json` con esto:

```json
{
  "permissions": {
    "allow": [
      "Skill(entrevista-ingles)",
      "Bash(.venv/Scripts/python.exe .claude/skills/entrevista-ingles/scripts/interview.py *)"
    ]
  }
}
```

## Solución de problemas

| Problema | Qué hacer |
|---|---|
| No te oye o el diagnóstico dice `microphone_silent` | Revisa en Windows, en *Configuración > Privacidad y seguridad > Micrófono*, que las aplicaciones de escritorio puedan usarlo, y elige el micrófono con `input_device` |
| Te corta mientras piensas | Sube `end_silence_s`, por ejemplo a `5` |
| Te capta con volumen bajo | Acerca el micrófono o sube su nivel en Windows. Un volumen bajo empeora la transcripción |
| Los cuatro hablan con la misma voz | No hay conexión con el servicio de voces y está hablando la voz de Windows |
| `No se encontró el lanzador 'py'` | Instala Python 3.12 desde python.org |
| Errores de la tarjeta gráfica | Pon `whisper_device` en `"cpu"` |

## Cómo funciona

Claude dirige la entrevista y escribe la evaluación. Un script en Python hace de voz y oído del panel:

- **Voces:** las genera con `edge-tts`.
- **Escucha:** graba hasta que detecta tu silencio.
- **Transcripción:** la hace con `faster-whisper` en tu equipo, en la gráfica si hay una NVIDIA.
- **Medidas de voz:** las calcula con Praat, mediante `praat-parselmouth`.
- **Audio de la ronda:** al cerrarla une en un MP3 las frases del panel y tus respuestas, con `soundfile`.

El estado de cada entrevista se guarda en disco, así que un examen puede continuar otro día.

```
.claude/skills/entrevista-ingles/
├── SKILL.md                  instrucciones de la entrevista para Claude
├── references/evaluation.md  criterios y formato del informe
├── data/panel.json           entrevistadores y preguntas
├── data/config.json          ajustes
├── evals/evals.json          evaluaciones de comportamiento
└── scripts/                  voz, reconocimiento, estado de la entrevista e instalación
tests/                        pruebas automáticas y entrevistas simuladas
```

## Desarrollo

Pruebas automáticas, que no consumen uso de Claude y tardan unos 2 minutos:

```
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest tests
```

En `tests/scenarios/` hay entrevistas simuladas con un candidato grabado que comete errores, contesta
demasiado corto, pide que repitan la pregunta y pide pistas. Cada una abre una sesión nueva de Claude Code
sin saltarse los permisos, así que consume uso de Claude. Los ejemplos guardan los resultados en
`simulaciones/`, que el `.gitignore` deja fuera del repositorio.

Primero crea las grabaciones del candidato. Necesita conexión:

```
.venv\Scripts\python.exe tests\scenarios\generate.py simulaciones\guion
```

Después lanza cada simulación y califícala:

- **Examen de 6 preguntas por voz:**

  ```
  .venv\Scripts\python.exe tests\scenarios\run.py simulaciones\examen-voz simulaciones\guion\examen "/entrevista-ingles"
  .venv\Scripts\python.exe tests\scenarios\grade.py simulaciones\examen-voz voz 6
  ```

- **Práctica de 15 preguntas por voz,** con el orden sorteado de verdad:

  ```
  .venv\Scripts\python.exe tests\scenarios\run.py simulaciones\practica-voz simulaciones\guion\practica "/entrevista-ingles" --sorteo
  .venv\Scripts\python.exe tests\scenarios\grade.py simulaciones\practica-voz voz 15
  ```

- **Examen de 6 preguntas por escrito,** pedido con una frase natural:

  ```
  .venv\Scripts\python.exe tests\scenarios\text_run.py simulaciones\examen-texto
  .venv\Scripts\python.exe tests\scenarios\grade.py simulaciones\examen-texto texto 6
  ```

`grade.py` escribe `grading.json` en la carpeta de la simulación y muestra las comprobaciones que fallaron.
Usa una carpeta nueva para cada simulación, porque los resultados se van añadiendo y se mezclarían con los
de la anterior. Lanza las simulaciones de una en una: cada una tarda unos minutos.

Los comandos son para PowerShell o la consola de Windows. En Git Bash, escribe las rutas con `/` y
ejecuta antes `export MSYS_NO_PATHCONV=1`. Si no, Git Bash convierte `/entrevista-ingles` en una ruta de
Windows.

Los casos de prueba están en `.claude/skills/entrevista-ingles/evals/evals.json`.
