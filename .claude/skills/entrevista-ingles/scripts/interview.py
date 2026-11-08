"""Interfaz de la entrevista. Cada comando imprime un único objeto JSON por la salida estándar.

El campo `next` de cada respuesta dice qué hacer a continuación. Durante la entrevista por
voz nadie escribe en el chat, así que ese recordatorio es lo que mantiene viva la cadena de
llamadas, también si el contexto de Claude se compacta a mitad de la sesión.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = SKILL_DIR.parents[2]
DATA_ROOT = Path(os.environ.get("INTERVIEW_DATA_DIR", PROJECT_DIR / "entrevistas"))
TTS_CACHE = DATA_ROOT / ".voces"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import metrics as speech_metrics  # noqa: E402
import voice  # noqa: E402
from session import InterviewError, RoundComplete, Session, interviewer_at, load_panel  # noqa: E402

MIC_OPEN_HZ = 880
MIC_CLOSED_HZ = 660
QUICK_END_SILENCE_S = 1.5  # respuestas de una palabra, como elegir práctica o examen

NEXT_ANSWERED = (
    "No termines el turno. Si la respuesta fue demasiado corta, confusa, incompleta o no contestó "
    "la pregunta, usa `follow-up`; si no, llama a `ask` con una transición."
)
NEXT_LAST = (
    "No termines el turno. Era la última pregunta de la ronda: usa `follow-up` si hace falta; "
    "si no, despide al candidato con `say` y llama a `summary`."
)
NEXT_NO_SPEECH = (
    "No termines el turno. No se oyó nada: llama a `ask` para repetir la misma pregunta. Si es el "
    "segundo intento seguido sin voz, pausa la entrevista y explica el problema en el chat."
)
NEXT_ROUND_DONE = "La ronda terminó: despide al candidato con `say` y llama a `summary`."
NEXT_AWAIT_TEXT = "Muestra la pregunta en el chat y termina el turno; registra la respuesta escrita con `answer`."
NEXT_SPOKEN = "No termines el turno: sigue enseguida con el paso que corresponda."
NEXT_HEARD = "No termines el turno: interpreta la respuesta y sigue enseguida."


CONFIG = json.loads((SKILL_DIR / "data" / "config.json").read_text(encoding="utf-8"))
PANEL = load_panel(SKILL_DIR / "data" / "panel.json")


def input_device() -> int | None:
    return voice.resolve_device(CONFIG.get("input_device"), "input")


def output_device() -> int | None:
    return voice.resolve_device(CONFIG.get("output_device"), "output")


def start_transcriber() -> voice.Transcriber:
    return voice.Transcriber(CONFIG["whisper_model"], CONFIG["whisper_device"])


def voice_of(person: str) -> str:
    return PANEL["interviewers"][person]["voice"]


def voice_notice(engine: str) -> dict:
    """Solo se menciona la voz de respaldo, que es lo único que hay que contarle al candidato."""
    return {"tts_engine": engine} if engine == "windows" else {}


def speak_lines(lines: list[tuple[str, str]], session: Session | None = None) -> str:
    """Hace hablar al panel. Con `session`, guarda cada frase para el audio completo de la ronda."""
    log = os.environ.get("INTERVIEW_SPEECH_LOG")  # para revisar en pruebas lo que dijo el panel
    if log:
        with open(log, "a", encoding="utf-8") as file:
            file.writelines(f"{person}: {text}\n" for person, text in lines if text.strip())
    speech = voice.speak(
        [(text, voice_of(person)) for person, text in lines],
        CONFIG["speech_rate"],
        TTS_CACHE,
        output_device(),
    )
    if session is not None:
        speakers = [person for person, text in lines if text.strip()]
        for person, (audio, rate) in zip(speakers, speech.clips):
            name = f"audio/panel-{session.recording_count():03d}.wav"
            voice.save_wav(session.directory / name, audio, rate)
            session.add_recording(name, person)
    return speech.engine


def recording_session() -> Session | None:
    """La ronda por voz en curso, si la hay: lo que diga el panel entra en su audio completo."""
    session = Session.latest_open(DATA_ROOT)
    if session and session.data["status"] == "in_progress" and session.data["input"] == "voice":
        return session
    return None


def join_round_audio(session: Session) -> dict:
    """Une en un MP3 lo que dijeron el panel y el candidato en la ronda que se cierra. Si falla, la
    ronda queda cerrada igual: el informe ya está guardado y el audio es un complemento."""
    round_number = session.data["round"]
    parts = session.recording_of_round(round_number)
    if not parts:
        return {}
    path = session.directory / f"entrevista-ronda-{round_number}.mp3"
    try:
        voice.join_recordings([(session.directory / file, speaker) for file, speaker in parts], path)
    except Exception as error:  # cualquier fallo del audio no debe ocultar que la ronda se cerró
        return {"audio_error": f"No se pudo crear el audio de la entrevista: {error}"}
    return {"audio_path": str(path)}


def listen_settings(quick: bool = False) -> voice.ListenSettings:
    settings = voice.ListenSettings(
        end_silence_s=CONFIG["end_silence_s"],
        start_timeout_s=CONFIG["start_timeout_s"],
        max_answer_s=CONFIG["max_answer_s"],
    )
    return replace(settings, end_silence_s=QUICK_END_SILENCE_S) if quick else settings


def hear(transcriber: voice.Transcriber, wav_path: Path, quick: bool = False) -> dict:
    """Abre el micrófono, graba y transcribe. Devuelve el resultado de la captura y del texto."""
    speaker = output_device()
    captured = voice.capture(listen_settings(quick), input_device(),
                             cue=lambda: voice.beep(MIC_OPEN_HZ, speaker), turn=wav_path.stem)
    if captured.status != "ok":
        return {"status": "no_speech"}
    voice.beep(MIC_CLOSED_HZ, speaker)
    voice.save_wav(wav_path, captured.audio, captured.sample_rate)
    started = time.perf_counter()
    transcript = transcriber.transcribe(wav_path)
    transcribe_s = round(time.perf_counter() - started, 1)
    if not transcript.text:
        wav_path.unlink(missing_ok=True)  # solo era ruido
        return {"status": "no_speech"}
    return {
        "status": "ok",
        "captured": captured,
        "transcript": transcript,
        "transcribe_s": transcribe_s,
    }


def open_session() -> Session:
    session = Session.latest_open(DATA_ROOT)
    if session is None:
        raise InterviewError("no_session", "No hay ninguna entrevista abierta. Usa `start`.")
    return session


def interviewer_of(session: Session, n: int) -> str:
    return interviewer_at(PANEL, session.position_of(n))


def question_info(session: Session, n: int) -> dict:
    return {
        "n": n,
        "text": PANEL["questions"][n - 1]["text"],
        "interviewer": PANEL["interviewers"][interviewer_of(session, n)]["name"],
    }


def report_file(session: Session) -> Path:
    return session.directory / f"informe-ronda-{session.data['round']}.md"


def after_answer(session: Session) -> str:
    return NEXT_LAST if session.progress()["remaining_in_round"] == 0 else NEXT_ANSWERED


def converse(session: Session, n: int, kind: str, lines: list[tuple[str, str]]) -> dict:
    """Un turno completo: el entrevistador habla y, por voz, se escucha y guarda la respuesta."""
    base = {"question": question_info(session, n), "progress": session.progress()}

    if session.data["input"] == "text":
        speak_lines(lines)
        return {"status": "awaiting_text", **base, "next": NEXT_AWAIT_TEXT}

    # El modelo carga mientras habla el entrevistador, para no hacer esperar al terminar.
    transcriber = start_transcriber()
    engine = speak_lines(lines, session)
    turn_index = len(session.data["questions"].get(str(n), {}).get("turns", []))
    wav_name = f"q{n:02d}-{kind}-{turn_index}.wav"
    heard = hear(transcriber, session.directory / "audio" / wav_name)

    if heard["status"] != "ok":
        return {"status": "no_speech", **base, **voice_notice(engine), "next": NEXT_NO_SPEECH}

    captured, transcript = heard["captured"], heard["transcript"]
    measures = {
        **speech_metrics.word_metrics(transcript.words),
        **speech_metrics.voice_metrics(captured.audio, captured.sample_rate),
        "seconds_to_speech": captured.seconds_to_speech,
    }
    session.add_turn(n, kind, {
        "input": "voice",
        "transcript": transcript.text,
        "audio": f"audio/{wav_name}",
        "truncated": captured.truncated,
        "metrics": measures,
    })
    session.add_recording(f"audio/{wav_name}", "candidate")
    # Las medidas quedan en disco; solo hacen falta al evaluar, no para decidir el siguiente turno.
    return {
        "status": "ok",
        "question": question_info(session, n),
        "answer": {
            "transcript": transcript.text,
            "words": measures["word_count"],
            "truncated": captured.truncated,
        },
        "progress": session.progress(),
        **voice_notice(engine),
        "transcribe_seconds": heard["transcribe_s"],
        "next": after_answer(session),
    }


# ---------- comandos ----------


def cmd_doctor(_args) -> dict:
    report: dict = {"python": sys.version.split()[0]}
    issues: list[str] = []

    try:
        import edge_tts  # noqa: F401
        import faster_whisper  # noqa: F401
        import parselmouth  # noqa: F401
        import sounddevice as sd
        import soundfile  # noqa: F401
    except ImportError as error:
        return {"status": "error", "code": "missing_dependency", "message": str(error),
                "next": "Ejecuta scripts/setup.py e inténtalo de nuevo."}

    try:
        report["microphone"] = voice.measure_microphone(input_device())
        if not report["microphone"]["receiving_signal"]:
            issues.append("microphone_silent")
    except Exception as error:
        report["microphone"] = {"error": str(error)}
        issues.append("microphone_unavailable")

    try:
        device = output_device()
        report["speaker"] = sd.query_devices(device if device is not None else sd.default.device[1])["name"]
    except Exception as error:
        report["speaker"] = {"error": str(error)}
        issues.append("speaker_unavailable")

    import tempfile

    voices: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as folder:  # sin caché: prueba de verdad el servicio
        for person, data in PANEL["interviewers"].items():
            try:
                *_, engine = voice.synthesize(f"Hello, this is {data['name']}.", data["voice"],
                                              CONFIG["speech_rate"], Path(folder))
                voices[person] = engine
            except Exception as error:
                voices[person] = f"error: {error}"
    report["voices"] = voices
    if any(engine != "edge" for engine in voices.values()):
        issues.append("online_voices_unavailable")

    started = time.perf_counter()
    transcriber = start_transcriber()
    transcriber._thread.join()
    report["recognizer"] = {
        "model": CONFIG["whisper_model"],
        "device": transcriber.device,
        "load_seconds": round(time.perf_counter() - started, 1),
        "ok": transcriber._error is None,
    }
    if transcriber._error is not None:
        report["recognizer"]["error"] = str(transcriber._error)
        issues.append("recognizer_unavailable")

    voice_ok = not {"microphone_silent", "microphone_unavailable", "speaker_unavailable",
                    "recognizer_unavailable"} & set(issues)
    report.update(
        status="ready" if voice_ok else "voice_unavailable",
        issues=issues,
        next="Sigue por voz." if voice_ok else "Explica el problema y ofrece el modo texto.",
    )
    return report


def cmd_devices(_args) -> dict:
    import sounddevice as sd

    default_in, default_out = sd.default.device
    devices = sd.query_devices()
    host_apis = sd.query_hostapis()
    return {
        "default_input": devices[default_in]["name"] if default_in >= 0 else None,
        "default_output": devices[default_out]["name"] if default_out >= 0 else None,
        "input_devices": sorted({d["name"] for d in devices if d["max_input_channels"] > 0}),
        "output_devices": sorted({d["name"] for d in devices if d["max_output_channels"] > 0}),
        "host_apis": [api["name"] for api in host_apis],
        "next": "Para cambiarlos, pon parte del nombre en input_device u output_device de data/config.json.",
    }


def cmd_status(_args) -> dict:
    session = Session.latest_open(DATA_ROOT)
    if session is None:
        return {"open_session": None, "next": "Pregunta al candidato si quiere práctica o examen."}
    return {
        "open_session": {
            "id": session.data["id"],
            "mode": session.data["mode"],
            "input": session.data["input"],
            "status": session.data["status"],
            "next_question": session.next_question_number(),
            "progress": session.progress(),
        },
        "next": "Pregunta si quiere continuarla (`start` con ese modo) o empezar otra (`start --new`).",
    }


def cmd_start(args) -> dict:
    existing = None if args.new else Session.latest_open(DATA_ROOT, args.mode)
    input_mode = "text" if args.text_mode else "voice"
    if existing is not None:
        existing.resume_next_round()
        session, resumed = existing, True
    else:
        forced = os.environ.get("INTERVIEW_QUESTION_ORDER")  # guion fijo en las pruebas
        order = [int(n) for n in forced.split(",")] if forced else None
        session, resumed = Session.create(DATA_ROOT, args.mode, input_mode, args.round_size, order), False
    return {
        "status": "ready",
        "session": session.data["id"],
        "mode": session.data["mode"],
        "input": session.data["input"],
        "resumed": resumed,
        "progress": session.progress(),
        "panel": [
            {"id": key, "name": person["name"], "role": person["role"]}
            for key, person in PANEL["interviewers"].items()
        ],
        "next": "Si es sesión nueva, presenta al panel con `intro`. Después llama a `ask`.",
    }


def cmd_intro(_args) -> dict:
    lines = [(key, person["intro"]) for key, person in PANEL["interviewers"].items()]
    engine = speak_lines(lines, recording_session())
    return {"status": "ok", **voice_notice(engine), "next": "Llama a `ask` con una transición breve."}


def cmd_say(args) -> dict:
    for person, _ in args.line:
        if person not in PANEL["interviewers"]:
            raise InterviewError("unknown_interviewer", f"No existe el entrevistador '{person}'.")
    notice = voice_notice(speak_lines([tuple(line) for line in args.line], recording_session()))
    return {"status": "ok", **notice, "next": NEXT_SPOKEN}


def cmd_listen(args) -> dict:
    """Escucha fuera de la entrevista, por ejemplo para elegir práctica o examen."""
    transcriber = start_transcriber()
    if args.line:
        speak_lines([tuple(line) for line in args.line])
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    wav = DATA_ROOT / ".ultima-escucha.wav"
    heard = hear(transcriber, wav, quick=True)
    if heard["status"] != "ok":
        return {"status": "no_speech", "next": "No termines el turno. Vuelve a preguntar con `listen`."}
    wav.unlink(missing_ok=True)
    return {"status": "ok", "transcript": heard["transcript"].text, "next": NEXT_HEARD}


def cmd_ask(args) -> dict:
    session = open_session()
    if args.repeat:
        session.discard_last_turn()
    try:
        n = session.advance()
    except RoundComplete:
        return {"status": "round_complete", "progress": session.progress(), "next": NEXT_ROUND_DONE}
    question = PANEL["questions"][n - 1]
    person = interviewer_of(session, n)
    lines = [(person, args.lead_in or ""), (person, question.get("spoken", question["text"]))]
    return converse(session, n, "main", lines)


def cmd_follow_up(args) -> dict:
    session = open_session()
    if args.repeat:
        session.discard_last_turn()
        session.release_follow_up()
    n = session.claim_follow_up()
    result = converse(session, n, "follow_up", [(interviewer_of(session, n), args.text)])
    if result["status"] == "no_speech":
        session.release_follow_up()
    return result


def cmd_answer(_args) -> dict:
    """Registra una respuesta escrita, recibida por la entrada estándar."""
    session = open_session()
    n = session.current_number()
    if n is None:
        raise InterviewError("no_question", "Todavía no se ha hecho ninguna pregunta.")
    text = sys.stdin.read().strip()
    if not text:
        raise InterviewError("empty_answer", "La respuesta está vacía.")
    kind = "follow_up" if session.is_answered(n) else "main"
    session.add_turn(n, kind, {"input": "text", "transcript": text, "metrics": None})
    return {"status": "ok", "question": question_info(session, n), "progress": session.progress(),
            "next": after_answer(session)}


def cmd_summary(_args) -> dict:
    session = open_session()
    start, end = session.data["round_start"], session.data["round_end"]
    questions, measured = [], []
    for position in range(start, end + 1):
        n = session.number_at(position)
        turns = session.valid_turns(n)
        if not turns:
            continue
        questions.append({
            **question_info(session, n),
            "turns": [
                {"kind": t["kind"], "input": t.get("input", "voice"), "transcript": t["transcript"],
                 "truncated": t.get("truncated", False), "metrics": t.get("metrics")}
                for t in turns
            ],
        })
        measured.extend(t.get("metrics") for t in turns)
    overall = speech_metrics.aggregate(measured)
    return {
        "status": "ok",
        "session": session.data["id"],
        "mode": session.data["mode"],
        "round": session.data["round"],
        "voice_evaluable": overall is not None,
        "progress": session.progress(),
        "questions": questions,
        "overall_metrics": overall,
        "next": "Lee references/evaluation.md y guarda el informe con `report`.",
    }


def cmd_report(_args) -> dict:
    """Guarda el informe de la ronda, recibido por la entrada estándar.

    Lo escribe el script para no necesitar otro permiso: un aviso al terminar la entrevista
    interrumpiría al candidato, y en cualquier caso `allowed-tools` solo cubre este script.
    """
    session = open_session()
    text = sys.stdin.read().strip()
    if not text:
        raise InterviewError("empty_report", "El informe está vacío.")
    path = report_file(session)
    path.write_text(text + "\n", encoding="utf-8")
    return {"status": "ok", "report_path": str(path),
            "next": "Da el comentario hablado del panel con `say` y llama a `close`."}


def cmd_close(_args) -> dict:
    session = open_session()
    if not report_file(session).exists():
        raise InterviewError("report_missing", "Guarda antes el informe de la ronda con `report`.")
    session.close_round()
    audio = join_round_audio(session)
    next_step = (
        "Entrevista completa." if session.data["status"] == "completed"
        else "Ronda cerrada. La siguiente ronda continúa donde quedó con `start` y el mismo modo."
    )
    if "audio_path" in audio:
        next_step += " Al mostrar el informe, di dónde quedó el audio completo de la ronda."
    return {"status": session.data["status"], "progress": session.progress(), **audio, "next": next_step}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor").set_defaults(run=cmd_doctor)
    commands.add_parser("devices").set_defaults(run=cmd_devices)
    commands.add_parser("status").set_defaults(run=cmd_status)
    commands.add_parser("intro").set_defaults(run=cmd_intro)
    commands.add_parser("answer").set_defaults(run=cmd_answer)
    commands.add_parser("summary").set_defaults(run=cmd_summary)
    commands.add_parser("report").set_defaults(run=cmd_report)
    commands.add_parser("close").set_defaults(run=cmd_close)

    start = commands.add_parser("start")
    start.add_argument("--mode", choices=["practice", "exam"], required=True)
    start.add_argument("--round-size", type=int)
    start.add_argument("--text-mode", action="store_true")
    start.add_argument("--new", action="store_true")
    start.set_defaults(run=cmd_start)

    say = commands.add_parser("say")
    say.add_argument("--line", nargs=2, action="append", required=True, metavar=("ID", "TEXT"))
    say.set_defaults(run=cmd_say)

    listen = commands.add_parser("listen")
    listen.add_argument("--line", nargs=2, action="append", metavar=("ID", "TEXT"))
    listen.set_defaults(run=cmd_listen)

    ask = commands.add_parser("ask")
    ask.add_argument("--lead-in", default="")
    ask.add_argument("--repeat", action="store_true")
    ask.set_defaults(run=cmd_ask)

    follow_up = commands.add_parser("follow-up")
    follow_up.add_argument("--text", required=True)
    follow_up.add_argument("--repeat", action="store_true")
    follow_up.set_defaults(run=cmd_follow_up)

    return parser


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    try:
        result, code = args.run(args), 0
    except InterviewError as error:
        result, code = {"status": "error", "code": error.code, "message": str(error)}, 1
    except voice.VoiceError as error:
        result, code = {
            "status": "error", "code": error.code, "message": str(error),
            "next": "No se perdió nada: el estado está guardado. Explica el problema en el chat.",
        }, 1
    print(json.dumps(result, ensure_ascii=False))
    return code


def exit_cleanly(code: int) -> None:
    """Sale sin descargar bibliotecas.

    Tras usar la gráfica, CUDA termina el proceso con el código 127 al descargarse, también con
    `os._exit`, y Claude Code mostraría como fallido un turno que fue bien.
    """
    sys.stdout.flush()
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.TerminateProcess.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        kernel32.TerminateProcess(kernel32.GetCurrentProcess(), code)
    os._exit(code)


if __name__ == "__main__":
    exit_cleanly(main())
