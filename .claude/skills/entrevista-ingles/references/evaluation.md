# Evaluación del candidato

Lee este archivo al terminar la ronda, con los datos de `summary` delante. El objetivo es
ayudar al candidato a mejorar su inglés y a prepararse para una entrevista real. Sé honesto,
constructivo y alentador, y adapta tus expectativas a su nivel de inglés.

## Principio: evalúa solo lo que tienes

Trabajas con una transcripción y con medidas calculadas, no con el audio. Esto delimita qué
puedes afirmar:

- **Gramática y vocabulario:** usa la transcripción. Cita solo lo que aparece en ella y nunca
  inventes frases. El reconocedor puede limpiar errores pequeños, como una «s» final que no se
  pronunció, de modo que la gramática real puede ser algo peor de lo que parece.
- **Errores que pueden ser del reconocedor:** también cambia palabras enteras. En las pruebas, un
  candidato que dijo «I has worked» quedó transcrito como «He has worked». Si algo no encaja con lo
  que venía diciendo, o es raro para su nivel, no lo presentes como un error suyo seguro ni lo uses
  para valorarlo: omítelo o avisa de que quizá sea un fallo de la transcripción. No retoques la cita
  para arreglarlo, porque la columna «You said» debe coincidir letra por letra con la transcripción:
  si una frase lleva esa palabra dudosa, no la pongas en la tabla.
- **Pronunciación y entonación:** son estimaciones a partir de las medidas. Dilo claramente en
  el informe. Nadie ha escuchado el audio, y simular que sí sería engañar al candidato.
- **Si una palabra no encaja:** si está en `unclear_words`, trátala como posible problema de
  pronunciación o de reconocimiento, no como error de vocabulario seguro.
- **Respuestas escritas o `voice_evaluable: false`:** no evalúes ritmo, pronunciación, entonación
  ni voz. En esas filas escribe «Not assessed: text answers». No des una puntuación inventada.
  La fluidez solo se valora en lo que el texto muestra: naturalidad y repeticiones.
- **Medida en `null`:** no hay dato. No la estimes ni la completes de memoria.

## Los 7 criterios

| Criterio | Qué valorar |
|---|---|
| Content and relevance | ¿Contestó de verdad la pregunta? ¿La respuesta fue significativa y apropiada? |
| Grammar | ¿Usó estructuras correctas? ¿Qué errores cometió? |
| Vocabulary | ¿Fue apropiado, variado y relacionado con el trabajo? ¿Qué expresiones mejorarían las respuestas? |
| Coherence | ¿Sus ideas fueron claras, lógicas y organizadas? |
| Fluency | ¿Sonó natural? ¿Fue demasiado dubitativo o repetitivo? |
| Pronunciation and intonation | ¿Se le entendió? ¿Usó acentuación y entonación apropiadas? Incluye ritmo y expresión vocal. |
| Professional communication | ¿Sonó educado, seguro y profesional? |

Valora también si las respuestas funcionarían en una entrevista real. Por ejemplo, una respuesta
sobre salario sin cifra ni rango, o una sobre debilidades que no menciona cómo las trabaja, es
floja aunque el inglés sea correcto.

## Cómo leer las medidas

Estos márgenes son orientativos, no estándares calibrados. Compáralos con el contenido y fíjate
en los patrones entre respuestas más que en una cifra aislada.

| Medida | Bien | Revisar | Qué puede indicar |
|---|---|---|---|
| `words_per_minute` | 110–160 | < 100 o > 170 | Lento: duda. Rápido: nervios o menor claridad |
| `pauses_per_minute` | hasta 8 | más de 12 | Búsqueda de palabras o de ideas |
| `longest_pause_s` | menos de 3 | 3 o más | Bloqueo puntual |
| `fillers_per_100_words` | menos de 3 | más de 7 | Muletillas que distraen. Puede quedarse corto: el reconocedor omite algunas |
| `recognition_confidence` | 0,85 o más | menos de 0,70 | Dicción poco clara, o mala calidad del micrófono |
| `unclear_words` | pocas | se repiten | Palabras candidatas a practicar. Son pistas, no prueba de un error |
| `pitch_variation_st` | 1,5–4 | menos de 1,5 | Voz plana o monótona |
| `volume_dbfs` | −30 a −12 | menos de −35 | Habla muy bajo o el micrófono está lejos |
| `seconds_to_speech_avg` | hasta 5 | más de 10 | Tiempo que tarda en empezar a contestar |

Si la confianza es baja en todas las respuestas y el volumen también, sospecha del micrófono antes
que de la pronunciación, y dilo.

## Nivel del candidato

Estima su nivel en la escala CEFR (A2, B1, B2, C1...) a partir de sus respuestas y dilo en el
informe. Exige en proporción: a un B1 no se le penaliza por no usar expresiones de C1, pero tampoco
se le regala la nota. La puntuación debe reflejar lo que un entrevistador real pensaría, con
expectativas ajustadas a ese nivel.

## Formato del informe

Redacta el informe en inglés, salvo que el candidato pida otro idioma, con esta estructura exacta.
Guárdalo con el comando `report` y después muéstralo completo en el chat.

```markdown
# Interview Feedback: Round <N>

**Mode:** <Practice | Examination> · **Questions answered:** <cantidad> · **Date:** <fecha>
**Estimated English level:** <CEFR>
**Answers given by:** <voice | text>

## 1. Strengths
<Lo que hizo bien, con ejemplos concretos sacados de sus respuestas.>

## 2. Mistakes
<Sus errores más importantes, no todos. Prioriza los que se repiten.>

| You said | Better version | Why |
|---|---|---|
| "<cita literal>" | "<versión corregida>" | <explicación breve> |

## 3. Better vocabulary
<Expresiones profesionales que pudo usar.>

| Instead of | You could say |
|---|---|
| "<lo que dijo>" | "<expresión más profesional>" |

## 4. Areas for improvement
<Recomendaciones específicas y aplicables. Evita consejos genéricos como «practica más».>

## 5. Performance score: <X>/10
<Por qué esa nota, en dos o tres frases.>

| Criterion | Score | Comment |
|---|---|---|
| Content and relevance | <x>/10 | <comentario> |
| Grammar | <x>/10 | <comentario> |
| Vocabulary | <x>/10 | <comentario> |
| Coherence | <x>/10 | <comentario> |
| Fluency | <x>/10 | <comentario> |
| Pronunciation and intonation | <x>/10 o Not assessed: text answers | <comentario> |
| Professional communication | <x>/10 | <comentario> |

## Voice measurements
<Solo con respuestas por voz: tabla con las cifras principales y qué significan. Termina con esta
frase: "Pronunciation and intonation are estimated from these measurements, since nobody
listened to the recording.">
```

No des respuestas modelo completas a las preguntas: el candidato debe formular las suyas. Corregir
sus frases y sugerir expresiones sí forma parte del feedback.

## Comentario hablado del panel

Después de escribir el informe, cada entrevistador da en voz alta una o dos frases sobre su área,
en una sola llamada a `say`, y Emma cierra anunciando la nota. Las áreas están en `feedback_focus`
dentro de `data/panel.json`:

- **Emma:** contenido y comunicación profesional.
- **Olivia:** gramática y vocabulario.
- **Liam:** coherencia y fluidez.
- **James:** pronunciación y entonación. Si las respuestas fueron escritas, comenta otro aspecto
  sin mencionar la voz.

Que suene a una conversación con el candidato, no a la lectura del informe: el detalle ya queda
escrito.
