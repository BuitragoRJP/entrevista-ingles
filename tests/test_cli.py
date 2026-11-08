"""Entrevistas completas por la interfaz real, con un WAV en lugar del micrófono."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PROJECT, SKILL
from session import interviewer_at, load_panel

SCRIPT = SKILL / "scripts" / "interview.py"
FIXTURES = PROJECT / "tests" / "fixtures"
PANEL = load_panel(SKILL / "data" / "panel.json")
REPORT = '# Interview Feedback: Round 1\n\nYou said "I has worked" — ¡casi!\n'


class Cli:
    def __init__(self, data_dir: Path):
        self.env = {
            **os.environ,
            "INTERVIEW_DATA_DIR": str(data_dir),
            "INTERVIEW_MUTE": "1",
            "INTERVIEW_FAKE_MIC": str(FIXTURES / "answer.wav"),
        }

    def __call__(self, *args: str, stdin: str | None = None, mic: str = "answer.wav") -> dict:
        env = {**self.env, "INTERVIEW_FAKE_MIC": str(FIXTURES / mic)}
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=stdin, capture_output=True, encoding="utf-8", env=env, timeout=120,
        )
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 1, f"La salida debe ser un único JSON. stdout={result.stdout!r} stderr={result.stderr!r}"
        data = json.loads(lines[0])
        # Claude Code muestra como fallido cualquier código distinto de 0, aunque el JSON diga ok.
        expected = 1 if data.get("status") == "error" else 0
        assert result.returncode == expected, f"código {result.returncode} con {lines[0][:200]}"
        return data


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(tmp_path)


def test_full_practice_interview(cli: Cli):
    assert cli("start", "--mode", "practice")["status"] == "ready"
    assert cli("intro")["status"] == "ok"

    asked = []
    for position in range(1, 16):
        turn = cli("ask", "--lead-in", "Thank you.")
        assert turn["status"] == "ok"
        number = turn["question"]["n"]
        asked.append(number)
        assert turn["question"]["text"] == PANEL["questions"][number - 1]["text"]
        person = interviewer_at(PANEL, position)
        assert turn["question"]["interviewer"] == PANEL["interviewers"][person]["name"]
        assert "responsible" in turn["answer"]["transcript"].lower()
        assert turn["next"]

    assert asked[0] == 1
    assert sorted(asked) == list(range(1, 16))
    assert cli("ask")["status"] == "round_complete"

    summary = cli("summary")
    assert [question["n"] for question in summary["questions"]] == asked
    assert summary["voice_evaluable"] is True
    assert summary["overall_metrics"]["total_words"] > 100
    assert summary["overall_metrics"]["words_per_minute"] > 0
    assert summary["questions"][0]["turns"][0]["metrics"]["pitch_variation_st"] is not None

    cli("say", "--line", "emma", "Thank you for your time.")
    cli("report", stdin=REPORT)
    closed = cli("close")
    assert closed["status"] == "completed"
    assert cli("status")["open_session"] is None

    # El audio de la ronda une, en el orden en que sonaron, al panel y al candidato.
    audio = Path(closed["audio_path"])
    assert audio.name == "entrevista-ronda-1.mp3" and audio.stat().st_size > 0
    recording = json.loads((audio.parent / "session.json").read_text(encoding="utf-8"))["recording"]
    speakers = [part["speaker"] for part in recording]
    assert speakers[:4] == ["emma", "olivia", "liam", "james"]
    assert speakers.count("candidate") == 15
    assert all(before != "candidate" for before, now in zip(speakers, speakers[1:]) if now == "candidate")
    assert speakers[-1] == "emma"


def test_exam_gives_no_more_than_the_round_and_continues_later(cli: Cli):
    cli("start", "--mode", "exam", "--round-size", "8")
    first = [cli("ask")["question"]["n"] for _ in range(8)]
    assert first[0] == 1
    assert cli("ask")["status"] == "round_complete"
    assert len(cli("summary")["questions"]) == 8
    cli("report", stdin=REPORT)
    assert cli("close")["status"] == "round_closed"

    second = cli("start", "--mode", "exam")
    assert second["resumed"] is True
    assert second["progress"]["round"] == 2
    assert second["progress"]["round_positions"] == [9, 15]
    assert cli("ask")["question"]["n"] not in first


def test_a_new_interview_starts_again_with_question_one(cli: Cli):
    cli("start", "--mode", "practice")
    cli("ask")
    fresh = cli("start", "--mode", "practice", "--new")
    assert fresh["resumed"] is False
    assert cli("ask")["question"]["n"] == 1


def test_silence_does_not_consume_the_question(cli: Cli):
    cli("start", "--mode", "practice")
    assert cli("ask", mic="silence.wav")["status"] == "no_speech"
    retry = cli("ask")
    assert retry["status"] == "ok"
    assert retry["question"]["n"] == 1


def test_repeat_asks_the_same_question_and_discards_the_turn(cli: Cli):
    cli("start", "--mode", "practice")
    cli("ask")
    assert cli("ask", "--repeat")["question"]["n"] == 1
    assert len(cli("summary")["questions"][0]["turns"]) == 1


def test_one_follow_up_only(cli: Cli):
    cli("start", "--mode", "practice")
    cli("ask")
    first = cli("follow-up", "--text", "Could you give me an example?")
    assert first["status"] == "ok"
    second = cli("follow-up", "--text", "And another one?")
    assert second["status"] == "error"
    assert second["code"] == "follow_up_used"
    kinds = [turn["kind"] for turn in cli("summary")["questions"][0]["turns"]]
    assert kinds == ["main", "follow_up"]
    assert cli("ask")["question"]["n"] != 1


def test_text_mode_records_answers_without_voice_measures(cli: Cli):
    cli("start", "--mode", "exam", "--round-size", "6", "--text-mode")
    asked = cli("ask")
    assert asked["status"] == "awaiting_text"
    assert asked["question"]["n"] == 1
    recorded = cli("answer", stdin='I\'m Ana, and I said "hello" — ¡sí!')
    assert recorded["status"] == "ok"
    summary = cli("summary")
    assert summary["voice_evaluable"] is False
    assert summary["overall_metrics"] is None
    assert summary["questions"][0]["turns"][0]["transcript"] == 'I\'m Ana, and I said "hello" — ¡sí!'
    assert cli("ask")["question"]["n"] != 1


def test_errors_are_reported_as_json(cli: Cli):
    result = cli("ask")
    assert result["status"] == "error"
    assert result["code"] == "no_session"


def test_listen_outside_the_interview_records_nothing(cli: Cli):
    heard = cli("listen", "--line", "emma", "Practice or examination?")
    assert heard["status"] == "ok"
    assert "responsible" in heard["transcript"].lower()
    assert cli("status")["open_session"] is None


def test_a_round_cannot_close_without_its_report(cli: Cli):
    """Si no, un informe que no se pudo guardar se perdería sin que nadie lo notara."""
    cli("start", "--mode", "exam", "--round-size", "6", "--text-mode")
    cli("ask")
    cli("answer", stdin="I am Ana.")
    assert cli("close")["code"] == "report_missing"
    assert cli("status")["open_session"] is not None

    assert cli("report", stdin="   ")["code"] == "empty_report"
    saved = cli("report", stdin=REPORT)
    assert saved["status"] == "ok"
    assert Path(saved["report_path"]).read_text(encoding="utf-8") == REPORT
    closed = cli("close")
    assert closed["status"] == "round_closed"
    assert "audio_path" not in closed  # por escrito no hay entrevista que escuchar


def test_each_exam_round_needs_its_own_report(cli: Cli):
    cli("start", "--mode", "exam", "--round-size", "6", "--text-mode")
    cli("ask")
    cli("answer", stdin="I am Ana.")
    cli("report", stdin=REPORT)
    cli("close")
    assert cli("start", "--mode", "exam")["progress"]["round"] == 2
    assert cli("close")["code"] == "report_missing"


def test_the_normal_voice_is_not_mentioned(cli: Cli):
    """Solo interesa saberlo si habla la voz de respaldo, y entonces hay que contárselo al candidato."""
    cli("start", "--mode", "practice")
    for result in (cli("intro"), cli("say", "--line", "emma", "Hello."), cli("ask")):
        assert "tts_engine" not in result


def test_speaking_and_listening_also_say_what_comes_next(cli: Cli):
    """Si el modelo terminara el turno tras una de estas llamadas, nada lo reactivaría."""
    assert cli("listen", "--line", "emma", "Hello?")["next"]
    assert cli("say", "--line", "emma", "Thank you.")["next"]
