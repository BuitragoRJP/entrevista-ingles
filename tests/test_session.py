from pathlib import Path

import pytest

from conftest import SKILL
from session import (
    InterviewError,
    RoundComplete,
    Session,
    draw_order,
    interviewer_at,
    load_panel,
    round_end_for,
)

PANEL = load_panel(SKILL / "data" / "panel.json")
ALL_QUESTIONS = list(range(1, 16))

# Copiadas de la especificación del usuario; no deben cambiar nunca.
SPEC_QUESTIONS = [
    "Can you tell me a little about yourself?",
    "What is your greatest weakness?",
    "What is your greatest strength?",
    "Where do you see yourself in 3–5 years from now?",
    "Why should we hire you?",
    "Let’s talk about salary. What are you looking for?",
    "Are you a team player?",
    "What is the biggest mistake you have ever made?",
    "Tell me about a problem you have solved.",
    "What has been your greatest achievement?",
    "Would you rather work for money or job satisfaction?",
    "How are you when you are working under pressure?",
    "What is your biggest failure?",
    "How would your boss, supervisors, or co-workers describe you?",
    "What sort of people do you not like to work with?",
]


def answer(session: Session, n: int, text: str = "An answer.") -> None:
    session.add_turn(n, "main", {"transcript": text})


def run_round(session: Session) -> list[int]:
    asked = []
    while True:
        try:
            n = session.advance()
        except RoundComplete:
            return asked
        asked.append(n)
        answer(session, n)


def test_question_texts_match_the_specification_exactly():
    assert [q["text"] for q in PANEL["questions"]] == SPEC_QUESTIONS
    assert [q["n"] for q in PANEL["questions"]] == ALL_QUESTIONS


def test_every_interview_opens_with_question_one_and_shuffles_the_rest():
    orders = [tuple(draw_order()) for _ in range(30)]
    assert all(order[0] == 1 for order in orders)
    assert all(sorted(order) == ALL_QUESTIONS for order in orders)
    assert len(set(orders)) > 1


def test_all_positions_after_the_first_can_vary():
    orders = [draw_order() for _ in range(300)]
    for position in range(1, 15):
        assert len({order[position] for order in orders}) > 5


def test_each_new_session_gets_its_own_order(tmp_path: Path):
    orders = {tuple(Session.create(tmp_path, "practice", "voice", None).data["order"]) for _ in range(5)}
    assert len(orders) > 1


def test_four_interviewers_take_turns():
    owners = [interviewer_at(PANEL, position) for position in range(1, 16)]
    assert len(PANEL["interviewers"]) == 4
    assert owners[:5] == ["emma", "olivia", "liam", "james", "emma"]
    assert {owners.count(name) for name in PANEL["interviewers"]} == {3, 4}


@pytest.mark.parametrize("size", [6, 7, 8])
def test_every_exam_round_includes_all_four_interviewers(size):
    start = 1
    while start <= 15:
        end = round_end_for(start, size)
        owners = {interviewer_at(PANEL, position) for position in range(start, end + 1)}
        if end - start + 1 >= 4:
            assert owners == set(PANEL["interviewers"])
        start = end + 1


def test_all_voices_are_different():
    voices = [person["voice"] for person in PANEL["interviewers"].values()]
    assert len(set(voices)) == 4


@pytest.mark.parametrize(
    "size, rounds",
    [(8, [(1, 8), (9, 15)]), (7, [(1, 7), (8, 15)]), (6, [(1, 6), (7, 12), (13, 15)])],
)
def test_exam_rounds_cover_all_questions(size, rounds):
    found, start = [], 1
    while start <= 15:
        end = round_end_for(start, size)
        found.append((start, end))
        start = end + 1
    assert found == rounds


def test_practice_asks_every_question_once_starting_with_the_first(tmp_path: Path):
    session = Session.create(tmp_path, "practice", "voice", None)
    asked = run_round(session)
    assert asked[0] == 1
    assert sorted(asked) == ALL_QUESTIONS
    assert asked == session.data["order"]
    session.close_round()
    assert session.data["status"] == "completed"
    assert Session.latest_open(tmp_path) is None


def test_exam_stops_at_the_end_of_the_round_and_resumes_without_repeating(tmp_path: Path):
    session = Session.create(tmp_path, "exam", "voice", 8)
    first = run_round(session)
    assert len(first) == 8
    assert first[0] == 1
    session.close_round()
    assert session.data["status"] == "round_closed"

    resumed = Session.latest_open(tmp_path, "exam")
    assert resumed.data["id"] == session.data["id"]
    resumed.resume_next_round()
    second = run_round(resumed)
    assert len(second) == 7
    assert sorted(first + second) == ALL_QUESTIONS
    resumed.close_round()
    assert resumed.data["status"] == "completed"


@pytest.mark.parametrize("size", [0, 5, 9, 15])
def test_invalid_round_size_is_rejected(tmp_path: Path, size):
    with pytest.raises(InterviewError):
        Session.create(tmp_path, "exam", "voice", size)


def test_question_is_not_skipped_until_it_has_an_answer(tmp_path: Path):
    session = Session.create(tmp_path, "practice", "voice", None)
    assert session.advance() == 1
    assert session.advance() == 1  # sin respuesta sigue siendo la misma
    answer(session, 1)
    assert session.advance() == session.data["order"][1]


def test_repeat_request_does_not_consume_the_question(tmp_path: Path):
    session = Session.create(tmp_path, "practice", "voice", None)
    session.advance()
    answer(session, 1, "Sorry, could you repeat that?")
    session.discard_last_turn()
    assert not session.is_answered(1)
    assert session.advance() == 1


def test_only_one_follow_up_per_question(tmp_path: Path):
    session = Session.create(tmp_path, "practice", "voice", None)
    session.advance()
    with pytest.raises(InterviewError) as error:
        session.claim_follow_up()
    assert error.value.code == "no_answer_yet"

    answer(session, 1)
    session.claim_follow_up()
    with pytest.raises(InterviewError) as error:
        session.claim_follow_up()
    assert error.value.code == "follow_up_used"


def test_follow_up_returns_if_the_candidate_did_not_answer_it(tmp_path: Path):
    session = Session.create(tmp_path, "practice", "voice", None)
    session.advance()
    answer(session, 1)
    session.claim_follow_up()
    session.release_follow_up()
    session.claim_follow_up()


def test_interrupted_round_resumes_after_the_last_answered_position(tmp_path: Path):
    session = Session.create(tmp_path, "exam", "voice", 8)
    asked = []
    for _ in range(3):
        n = session.advance()
        asked.append(n)
        answer(session, n)
    session.close_round()
    resumed = Session.latest_open(tmp_path)
    resumed.resume_next_round()
    assert resumed.advance() == resumed.data["order"][3]
    assert asked == resumed.data["order"][:3]


def test_order_and_answers_survive_a_restart(tmp_path: Path):
    session = Session.create(tmp_path, "practice", "voice", None)
    session.advance()
    answer(session, 1, "Hello")
    reloaded = Session.load(session.directory)
    assert reloaded.data["order"] == session.data["order"]
    assert reloaded.valid_turns(1)[0]["transcript"] == "Hello"
    assert reloaded.advance() == session.data["order"][1]


def test_a_forced_order_is_respected(tmp_path: Path):
    session = Session.create(tmp_path, "practice", "voice", None, order=ALL_QUESTIONS)
    assert run_round(session) == ALL_QUESTIONS


def test_cannot_ask_after_the_round_was_closed(tmp_path: Path):
    session = Session.create(tmp_path, "exam", "voice", 8)
    session.close_round()
    with pytest.raises(InterviewError) as error:
        session.advance()
    assert error.value.code == "not_in_progress"
