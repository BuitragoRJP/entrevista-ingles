"""Califica una ejecución de la skill a partir de lo que realmente ocurrió.

Uso: python tests/scenarios/grade.py <dir_ejecución> <voz|texto> <n_preguntas>
Escribe grading.json con el formato que espera el visor de skill-creator.
"""
import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "entrevista-ingles"
SECTIONS = ["1. Strengths", "2. Mistakes", "3. Better vocabulary", "4. Areas for improvement", "5. Performance score"]
CRITERIA = [
    "Content and relevance", "Grammar", "Vocabulary", "Coherence", "Fluency",
    "Pronunciation and intonation", "Professional communication",
]
EVALUATIVE = re.compile(
    r"\b(great|excellent|perfect|well done|good (answer|point|job)|good[.,!]|nice answer|"
    r"helpful answer|wonderful|impressive|you should|try to say|correct form)(\W|$)", re.I,
)


def norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w' ]", " ", text.lower().replace("’", "'")).split())


def add(results: list, text: str, passed, evidence) -> None:
    results.append({"text": text, "passed": bool(passed), "evidence": str(evidence)[:400]})


def save(run: Path, results: list) -> None:
    passed = sum(r["passed"] for r in results)
    grading = {
        "summary": {"passed": passed, "failed": len(results) - passed, "total": len(results),
                    "pass_rate": round(passed / max(len(results), 1), 2)},
        "expectations": results,
    }
    (run / "grading.json").write_text(json.dumps(grading, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{passed}/{len(results)}")
    for item in results:
        if not item["passed"]:
            print("FALLA:", item["text"], "->", item["evidence"])


def failed_calls(run: Path) -> list[str]:
    """Llamadas al script que fallaron o quedaron sin permiso. Las exploraciones del modelo no cuentan."""
    commands, failures = {}, []
    for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        message = event.get("message")  # algunos avisos del sistema lo traen como texto
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_use":
                commands[block["id"]] = block["input"].get("command", "")
            elif block.get("type") == "tool_result" and block.get("is_error"):
                if "interview.py" in commands.get(block["tool_use_id"], ""):
                    failures.append(str(block.get("content"))[:160])
    return failures


def final_message(run: Path) -> str:
    """Lo último que escribió el modelo en el chat."""
    text = ""
    for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") == "result":
            text = str(event.get("result", ""))
    return text


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    run, mode, count = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
    results: list = []
    data_root = run / "outputs" / "entrevistas"
    sessions = sorted(p for p in data_root.iterdir() if (p / "session.json").exists()) if data_root.exists() else []
    if not sessions:
        add(results, "Se creó una sesión de entrevista", False, f"Sin sesión en {data_root}")
        save(run, results)
        return

    session = json.loads((sessions[-1] / "session.json").read_text(encoding="utf-8"))
    panel = json.loads((SKILL / "data" / "panel.json").read_text(encoding="utf-8"))
    log_path = run / "outputs" / "habla.log"
    speech = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    questions = session["questions"]
    valid = {n: [t for t in q["turns"] if not t.get("discarded")] for n, q in questions.items()}

    answered = sorted(int(n) for n, turns in valid.items() if turns)
    add(results, f"Respondidas exactamente las preguntas 1 a {count}", answered == list(range(1, count + 1)), answered)

    spoken = norm(" ".join(speech))
    said = {q["n"]: norm(q.get("spoken", q["text"])) for q in panel["questions"]}
    missing = [n for n in range(1, count + 1) if said[n] not in spoken]
    add(results, "Cada pregunta se pronunció con su texto exacto", not missing, f"faltan: {missing}")

    order = session["order"][:count]
    moments = [spoken.find(said[n]) for n in order]
    add(results, "Abrió con la pregunta 1 y siguió el orden guardado en la sesión",
        order[0] == 1 and -1 not in moments and moments == sorted(moments), order)

    people = {line.split(":", 1)[0] for line in speech if ":" in line}
    add(results, "Hablaron los 4 entrevistadores", people >= set(panel["interviewers"]), sorted(people))

    follow_ups = {n: sum(1 for t in turns if t["kind"] == "follow_up") for n, turns in valid.items()}
    add(results, "Máximo una repregunta por pregunta", all(v <= 1 for v in follow_ups.values()), follow_ups)

    turns = [t for group in valid.values() for t in group]
    if mode == "voz":
        add(results, "La respuesta demasiado corta (P2) tuvo repregunta", follow_ups.get("2", 0) == 1, follow_ups)
        q3 = questions.get("3", {}).get("turns", [])
        add(results, "«¿Puede repetir?» no contó como respuesta",
            any(t.get("discarded") and "repeat" in t["transcript"].lower() for t in q3),
            [(t.get("discarded"), t["transcript"][:50]) for t in q3])
        q4 = questions.get("4", {}).get("turns", [])
        add(results, "La petición de pista no contó como respuesta",
            any(t.get("discarded") and "example" in t["transcript"].lower() for t in q4),
            [(t.get("discarded"), t["transcript"][:50]) for t in q4])
        measured = sum(1 for t in turns if t.get("metrics"))
        add(results, "Todas las respuestas tienen medidas de voz", measured == len(turns), f"{measured}/{len(turns)}")
    else:
        add(results, "Las respuestas escritas no tienen medidas de voz",
            all(not t.get("metrics") for t in turns), f"{len(turns)} turnos")

    # El tramo final es la despedida y el comentario del panel: ahí sí se valora.
    lines = [line.split(":", 1)[1].strip() for line in speech if ":" in line]
    during = lines[:-6] if len(lines) > 6 else lines
    evaluative = [line for line in during if EVALUATIVE.search(line)]
    add(results, "Sin elogios ni correcciones durante la entrevista", not evaluative, evaluative[:5])

    reports = sorted(sessions[-1].glob("informe-ronda-*.md"))
    report = reports[-1].read_text(encoding="utf-8") if reports else ""
    add(results, "Existe el informe de la ronda", report, [p.name for p in reports])
    absent = [s for s in SECTIONS if s not in report]
    add(results, "El informe tiene los 5 apartados pedidos", not absent, f"faltan: {absent}")
    absent = [c for c in CRITERIA if c not in report]
    add(results, "El informe evalúa los 7 criterios", not absent, f"faltan: {absent}")
    add(results, "Da una nota de 1 a 10", re.search(r"Performance score:\s*\d+(\.\d+)?/10", report),
        re.findall(r"Performance score:[^\n]*", report))
    add(results, "Estima el nivel CEFR", re.search(r"\b(A1|A2|B1|B2|C1|C2)\b", report),
        re.findall(r"Estimated English level:[^\n]*", report))

    transcripts = norm(" ".join(t["transcript"] for q in questions.values() for t in q["turns"]))
    mistakes = report.split("## 2. Mistakes")[-1].split("## 3.")[0] if report else ""
    quotes = re.findall(r'^\|\s*"([^"]+)"\s*\|', mistakes, re.M)
    invented = [q for q in quotes if norm(q) not in transcripts]
    add(results, "Las frases citadas como errores son literales", quotes and not invented,
        f"{len(quotes)} citas; no literales: {invented[:4]}")

    if mode == "voz":
        add(results, "Avisa de que la voz se estimó con mediciones",
            "nobody" in report.lower() and "listened" in report.lower(),
            re.findall(r"[^\n]*listened[^\n]*", report)[:2])
    else:
        row = re.findall(r"\|\s*Pronunciation and intonation[^\n]*", report)
        add(results, "No evalúa la voz en modo texto", row and "Not assessed" in row[0], row)

    add(results, "La ronda quedó cerrada", session["status"] in ("round_closed", "completed"), session["status"])

    if mode == "voz":
        audio = sessions[-1] / f"entrevista-ronda-{session['round']}.mp3"
        parts = [part["speaker"] for part in session.get("recording", []) if part["round"] == session["round"]]
        heard = sum(len(q["turns"]) for q in questions.values())
        add(results, "El audio de la ronda une al panel y todas las respuestas",
            audio.exists() and parts.count("candidate") == heard and len(parts) > heard,
            f"{audio.name}: {audio.exists()}; {len(parts)} tramos, {parts.count('candidate')} de {heard} respuestas")
        add(results, "Al terminar dice dónde quedó el audio", audio.name in final_message(run),
            final_message(run)[-300:])

    failures = failed_calls(run)
    add(results, "Ninguna llamada falló ni quedó sin permiso", not failures, failures[:3])
    save(run, results)


if __name__ == "__main__":
    main()
