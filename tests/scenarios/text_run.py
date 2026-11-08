"""Examen por escrito: cada respuesta del candidato es un mensaje nuevo en la misma sesión.

El candidato contesta al turno que marca la sesión, con el mismo guion que el de voz, así que
una repregunta del panel no lo desfasa.

Una persona vería dos avisos de permiso que aquí nadie puede contestar, así que `--allowedTools`
hace de su aprobación: uno al activarse la skill sin escribir `/entrevista-ingles`, porque declara
`allowed-tools`, y otro desde el segundo mensaje, porque `allowed-tools` solo dura el primer turno.

Uso: python tests/scenarios/text_run.py <dir_salida> [args de claude...]
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import generate

HERE = Path(__file__).resolve().parent
SKILL_RULE = "Skill(entrevista-ingles)"
SCRIPT_RULE = "Bash(.venv/Scripts/python.exe .claude/skills/entrevista-ingles/scripts/interview.py *)"
PROMPT = "Quiero practicar mi entrevista de trabajo en inglés por escrito, sin micrófono, modo examen de 6 preguntas"
MAX_MESSAGES = 16


def run(out: Path, prompt: str, *extra: str) -> dict:
    command = [sys.executable, str(HERE / "run.py"), str(out), "-", prompt, *extra]
    subprocess.run(command, check=True, capture_output=True, encoding="utf-8", errors="replace")
    return json.loads((out / "resumen.json").read_text(encoding="utf-8"))


def latest_session(out: Path) -> dict | None:
    sessions = sorted((out / "outputs" / "entrevistas").glob("*/session.json"))
    return json.loads(sessions[-1].read_text(encoding="utf-8")) if sessions else None


def waiting_for_answer(session: dict | None) -> bool:
    return bool(session) and session["status"] == "in_progress" and session["current"] is not None


def next_turn(session: dict, sent: Counter) -> str:
    """Nombre del turno pendiente en el guion. A diferencia de la voz, por escrito pedir que repitan
    no queda en la sesión: lo que distingue los intentos son los mensajes ya enviados."""
    n = session["order"][session["current"] - 1]
    turns = session["questions"].get(str(n), {}).get("turns", [])
    answered = any(not turn.get("discarded") for turn in turns)
    name = f"q{n:02d}-{'follow_up' if answered else 'main'}-{sent[n]}"
    sent[n] += 1
    return name


def main() -> None:
    out, *extra = sys.argv[1:]
    out = Path(out)
    script = generate.turns()
    sent = Counter()
    summary = run(out, PROMPT, "--allowedTools", SKILL_RULE, *extra)
    for _ in range(MAX_MESSAGES):
        session = latest_session(out)
        if not waiting_for_answer(session):
            break
        answer = script.get(next_turn(session, sent), generate.OTHER)
        summary = run(out, answer, "--resume", summary["session_id"], "--allowedTools", SCRIPT_RULE, *extra)
    session = latest_session(out)
    print("estado:", session and session["status"], "| coste:", summary.get("total_cost_usd"))


if __name__ == "__main__":
    main()
