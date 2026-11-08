"""Ejecuta la skill en una sesión nueva de Claude Code con un candidato simulado.

No usa ningún indicador que salte permisos: si `allowed-tools` no funcionara, la sesión no
podría ejecutar el script y la prueba fallaría. Guarda cada evento con su hora de llegada
para medir cuánto tarda el modelo entre turnos.

Uso: python tests/scenarios/run.py <dir_salida> <carpeta_guion|-> "<prompt>" [--sorteo] [args de claude...]

Sin --sorteo se fija el orden 1..15, para que un examen incluya los turnos difíciles del guion
(preguntas 2, 3 y 4). Con --sorteo la entrevista usa el orden sorteado de verdad.

Desde Git Bash, exporta MSYS_NO_PATHCONV=1 y pasa las rutas como C:/...; si no, convierte el
prompt `/entrevista-ingles` en una ruta de Windows.
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]


def main() -> int:
    out, script_dir, prompt, *extra = sys.argv[1:]
    out = Path(out).resolve()  # la entrevista corre en la raíz del proyecto, no en la carpeta actual
    if script_dir != "-" and not Path(script_dir).is_dir():
        # Sin el guion la entrevista fallaría en la primera escucha, después de gastar uso de Claude.
        print(f"No existe la carpeta del guion {script_dir}. Créala antes con generate.py.", file=sys.stderr)
        return 2
    (out / "outputs").mkdir(parents=True, exist_ok=True)

    env = {
        **os.environ,
        "INTERVIEW_MUTE": "1",
        "INTERVIEW_DATA_DIR": str(out / "outputs" / "entrevistas"),
        "INTERVIEW_SPEECH_LOG": str(out / "outputs" / "habla.log"),
    }
    if "--sorteo" in extra:
        extra.remove("--sorteo")
    else:
        env["INTERVIEW_QUESTION_ORDER"] = ",".join(str(n) for n in range(1, 16))
    if script_dir != "-":
        env["INTERVIEW_FAKE_MIC"] = str(Path(script_dir).resolve())

    claude = shutil.which("claude") or "claude"
    command = [claude, "-p", prompt, "--output-format", "stream-json", "--verbose", *extra]
    started = time.perf_counter()
    events = []
    with open(out / "events.jsonl", "a", encoding="utf-8") as log:
        process = subprocess.Popen(
            command, cwd=PROJECT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace",
        )
        for line in process.stdout:
            moment = round(time.perf_counter() - started, 2)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"type": "raw", "text": line.rstrip()[:500]}
            event["_t"] = moment
            events.append(event)
            log.write(json.dumps(event, ensure_ascii=False) + "\n")
            log.flush()
        process.wait(timeout=30)

    # Latencia del modelo: desde que llega un resultado hasta la siguiente acción del modelo.
    gaps, waiting_since = [], None
    for event in events:
        if event.get("type") == "user":
            waiting_since = event["_t"]
        elif event.get("type") == "assistant" and waiting_since is not None:
            content = event.get("message", {}).get("content", [])
            if any(block.get("type") == "tool_use" for block in content):
                gaps.append(round(event["_t"] - waiting_since, 1))
                waiting_since = None

    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    summary = {
        "exit_code": process.returncode,
        "total_seconds": round(time.perf_counter() - started, 1),
        "tool_calls_followed": len(gaps),
        "model_gap_median_s": statistics.median(gaps) if gaps else None,
        "model_gap_max_s": max(gaps) if gaps else None,
        "model_gaps_s": gaps,
        "num_turns": result.get("num_turns"),
        "is_error": result.get("is_error"),
        "total_cost_usd": result.get("total_cost_usd"),
        "session_id": result.get("session_id"),
        "final_text": (result.get("result") or "")[:6000],
    }
    (out / "resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "final_text"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
