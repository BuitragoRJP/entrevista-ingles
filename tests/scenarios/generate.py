"""Genera las grabaciones del candidato con guion: acento hispano y errores reales.

Cada archivo se llama como el turno al que contesta (`q05-main-0`, `q05-follow_up-1`), así que el
candidato responde a lo que se le pregunta aunque el panel añada repreguntas o cambie el orden.

Uso: python tests/scenarios/generate.py <carpeta de salida>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude" / "skills" / "entrevista-ingles" / "scripts"))
import numpy as np
import soundfile as sf
import voice

VOICE = "es-MX-JorgeNeural"
FIRST = {"practica": "Regular practice, please.", "examen": "Examination, with six questions."}
# Intentos por pregunta. El panel debe descartar el primero cuando hay dos.
ANSWERS = {
    1: ["Hello, my name is Carlos and I am from Mexico. I has worked as a software developer during five years in a bank. I like very much to solve problems and work with people."],
    2: ["I am perfectionist."],  # demasiado corta: pide repregunta
    3: ["Could you repeat the question, please?",
        "My greatest strength is that I learn very fast, and I am very responsible person. In my last job I learned a new programming language in two months."],
    4: ["I don't know what to say. Can you give me an example of a good answer?",  # pide una pista
        "In three or five years I want to be a team leader and help to the others developers. I also want to improve my English."],
    5: ["You should hire me because I have experience, I work hard and I can to learn quickly."],
    6: ["I am looking for around sixty thousand dollars per year, but it depends of the benefits."],
    7: ["Yes, I am a team player. In my last project we was five persons, and I always help my colleagues when they have problems."],
    8: ["My biggest mistake was when I deleted a table in production. I told to my boss immediately and we restored the backup in one hour."],
    9: ["One time the payments system was very slow. I analyzed the database, I found a missing index and the system was faster after that."],
    10: ["My greatest achievement was to lead the migration to the cloud. We finished before the deadline and the company saved a lot of money."],
    11: ["I prefer job satisfaction, because if you enjoy your work you do it better, but of course the money is important too."],
    12: ["Under pressure I stay calm. I make a list of priorities and I work on the most important things first."],
    13: ["My biggest failure was a project that we didn't finish because I didn't ask for help on time. Now I communicate problems earlier."],
    14: ["My boss would say that I am reliable and hardworking, and my coworkers would say that I am friendly."],
    15: ["I don't like to work with people who don't respect the others or who don't do their part of the work."],
}
# Lo que añade si le repreguntan en cada pregunta.
FOLLOW_UPS = {
    1: "In my last job I was responsible of the payments system, and I worked with a team of five persons.",
    2: "Sometimes I spend too much time in the details, and this make me slow. Now I try to use deadlines for finish on time.",
    3: "For example, when the company changed the database, I learned it in two weeks and I explained it to my team.",
    4: "I would like to lead a small team of developers in a bank, because I enjoy to help the people to grow.",
    5: "I can bring five years of experience in banks, and I know how to make the systems more fast and more secure.",
    6: "I would accept between fifty-five and sixty-five thousand dollars, it depends of the health insurance and the vacations.",
    7: "For example, last year a colleague had a problem with a deadline, and I stayed two days more for help him.",
    8: "After that mistake I always make a backup before I change anything in production.",
    9: "The reports took ten minutes to load, and after my change they took only ten seconds.",
    10: "The project took six months, and I coordinated four developers and two providers.",
    11: "If I have to choose, I choose the satisfaction, because I spend most of my day at work.",
    12: "For example, one day the system failed during the closing of the month, and I organized the tasks with my team.",
    13: "It was a mobile application for the clients, and we lost three months of work.",
    14: "My last boss told me that I always finish what I promise.",
    15: "For example, I had a colleague who never answered the messages, and this made slow to all the team.",
}
OTHER = "I'm sorry, I think that is all I can say about it."


def turns() -> dict[str, str]:
    """Texto de cada turno de la entrevista, con el nombre que le da `interview.py`."""
    script = {"otro": OTHER}
    for n, attempts in ANSWERS.items():
        for attempt, text in enumerate(attempts):
            script[f"q{n:02d}-main-{attempt}"] = text
        # El número es el de turnos anteriores, contando el intento descartado.
        for previous in (1, 2):
            script[f"q{n:02d}-follow_up-{previous}"] = FOLLOW_UPS[n]
    return script


def main() -> None:
    root = Path(sys.argv[1])
    cache = root / "cache"
    for name, opening in FIRST.items():
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        for turn, text in {".ultima-escucha": opening, **turns()}.items():
            audio, rate, engine = voice.synthesize(text, VOICE, "+0%", cache)
            assert engine == "edge", "Hace falta la voz en línea para generar el guion."
            pad = np.zeros(int(rate * 0.8), dtype="float32")
            sf.write(folder / f"{turn}.wav", np.concatenate([pad, audio]), rate, subtype="PCM_16")
    print("Listo:", root)


if __name__ == "__main__":
    main()
