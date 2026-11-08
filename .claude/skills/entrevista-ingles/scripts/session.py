"""Estado de la entrevista. No depende del audio, así que se prueba sin micrófono.

Este módulo es el dueño del orden: decide qué pregunta toca, quién la hace y cuándo acaba
la ronda. Claude solo aporta transiciones y repreguntas, nunca el texto de las preguntas.

Dos conceptos que conviene no mezclar:
  número    identifica la pregunta en panel.json (1 a 15).
  posición  es el turno dentro del orden sorteado de esa entrevista (1 a 15).

Las rondas y la rotación de entrevistadores van por posición. Así cualquier ronda incluye
a los cuatro, sea cual sea el sorteo.
"""
from __future__ import annotations

import json
import os
import random
from datetime import datetime
from pathlib import Path

TOTAL_QUESTIONS = 15
FIRST_QUESTION = 1
MIN_ROUND = 6
MAX_ROUND = 8
DEFAULT_EXAM_ROUND = 8
OPEN_STATES = ("in_progress", "round_closed")


class InterviewError(Exception):
    """Operación no válida para el estado actual. Lleva un código legible por máquina."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class RoundComplete(InterviewError):
    def __init__(self) -> None:
        super().__init__("round_complete", "No quedan preguntas en esta ronda.")


def load_panel(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def draw_order() -> list[int]:
    """La pregunta 1 abre siempre la entrevista; las demás se sortean cada vez."""
    rest = [n for n in range(1, TOTAL_QUESTIONS + 1) if n != FIRST_QUESTION]
    return [FIRST_QUESTION, *random.sample(rest, len(rest))]


def interviewer_at(panel: dict, position: int) -> str:
    rotation = panel["rotation"]
    return rotation[(position - 1) % len(rotation)]


def round_end_for(start: int, size: int) -> int:
    """Última posición de una ronda que empieza en la posición `start`.

    Si lo que quedaría después no alcanza para otra ronda válida y cabe en esta sin pasar
    del máximo, se absorbe aquí (con 7: 1-7 y 8-15). Si no cabe, la última ronda sale más
    corta (con 6: 1-6, 7-12 y 13-15), porque no hay otra forma de cubrir las 15.
    """
    end = min(start + size - 1, TOTAL_QUESTIONS)
    left = TOTAL_QUESTIONS - end
    if 0 < left < MIN_ROUND and end + left - start + 1 <= MAX_ROUND:
        return TOTAL_QUESTIONS
    return end


class Session:
    def __init__(self, directory: Path, data: dict):
        self.directory = directory
        self.data = data

    # ---------- ciclo de vida ----------

    @classmethod
    def create(
        cls, root: Path, mode: str, input_mode: str, round_size: int | None, order: list[int] | None = None
    ) -> "Session":
        if mode == "practice":
            size = TOTAL_QUESTIONS
        else:
            size = round_size if round_size is not None else DEFAULT_EXAM_ROUND
            if not MIN_ROUND <= size <= MAX_ROUND:
                raise InterviewError(
                    "bad_round_size", f"Una ronda de examen debe tener de {MIN_ROUND} a {MAX_ROUND} preguntas."
                )
        session_id = cls._new_id(root)
        session = cls(root / session_id, {
            "id": session_id,
            "created": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "input": input_mode,
            "order": order or draw_order(),
            "round_size": size,
            "round": 1,
            "round_start": 1,
            "round_end": round_end_for(1, size),
            "current": None,
            "status": "in_progress",
            "questions": {},
        })
        session.save()
        return session

    @staticmethod
    def _new_id(root: Path) -> str:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        candidate, suffix = stamp, 1
        while (root / candidate).exists():
            suffix += 1
            candidate = f"{stamp}-{suffix}"
        return candidate

    @classmethod
    def load(cls, directory: Path) -> "Session":
        data = json.loads((directory / "session.json").read_text(encoding="utf-8"))
        return cls(directory, data)

    @classmethod
    def latest_open(cls, root: Path, mode: str | None = None) -> "Session | None":
        if not root.exists():
            return None
        for directory in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
            if not (directory / "session.json").exists():
                continue
            session = cls.load(directory)
            if session.data["status"] in OPEN_STATES and mode in (None, session.data["mode"]):
                return session
        return None

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "session.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        # Reemplazo atómico: un corte a mitad de entrevista no puede dejar el archivo a medias.
        os.replace(temporary, path)

    def resume_next_round(self) -> None:
        """Pasa a la siguiente ronda de un examen cuya ronda anterior ya se cerró."""
        if self.data["status"] != "round_closed":
            return
        start = self.data["round_end"] + 1
        self.data.update(
            round=self.data["round"] + 1,
            round_start=start,
            round_end=round_end_for(start, self.data["round_size"]),
            status="in_progress",
        )
        self.save()

    def close_round(self) -> None:
        if self.data["status"] != "in_progress":
            raise InterviewError("not_in_progress", "No hay una ronda en curso.")
        last = self.last_answered_position()
        self.data["status"] = "completed" if last >= TOTAL_QUESTIONS else "round_closed"
        if self.data["status"] == "round_closed" and last < self.data["round_end"]:
            # Ronda interrumpida: la siguiente sigue justo tras la última posición respondida.
            self.data["round_end"] = last
        self.save()

    # ---------- orden ----------

    def number_at(self, position: int) -> int:
        return self.data["order"][position - 1]

    def position_of(self, number: int) -> int:
        return self.data["order"].index(number) + 1

    # ---------- avance por las preguntas ----------

    def _record(self, n: int) -> dict:
        return self.data["questions"].setdefault(str(n), {"turns": [], "follow_up_used": False})

    def valid_turns(self, n: int) -> list[dict]:
        record = self.data["questions"].get(str(n))
        return [t for t in record["turns"] if not t.get("discarded")] if record else []

    def is_answered(self, n: int) -> bool:
        return bool(self.valid_turns(n))

    def current_number(self) -> int | None:
        position = self.data["current"]
        return None if position is None else self.number_at(position)

    def last_answered_position(self) -> int:
        answered = [p for p in range(1, TOTAL_QUESTIONS + 1) if self.is_answered(self.number_at(p))]
        return max(answered, default=0)

    def next_position(self) -> int:
        """Posición que toca, sin modificar el estado.

        Solo se avanza si la actual tiene una respuesta válida. Si falló el micrófono o el
        candidato no contestó, toca repetir la misma: así ninguna se salta.
        """
        position = self.data["current"]
        if position is None:
            return self.data["round_start"]
        return position + 1 if self.is_answered(self.number_at(position)) else position

    def next_question_number(self) -> int | None:
        position = self.next_position()
        return self.number_at(position) if position <= TOTAL_QUESTIONS else None

    def advance(self) -> int:
        """Pasa a la pregunta que toca y devuelve su número."""
        if self.data["status"] != "in_progress":
            raise InterviewError("not_in_progress", "No hay una ronda en curso.")
        position = self.next_position()
        if position > self.data["round_end"]:
            raise RoundComplete()
        self.data["current"] = position
        self.save()
        return self.number_at(position)

    def discard_last_turn(self) -> None:
        """Descarta lo último dicho si no era una respuesta, por ejemplo «¿puede repetir?»."""
        current = self.current_number()
        if current is None:
            raise InterviewError("no_question", "Todavía no se ha hecho ninguna pregunta.")
        for turn in reversed(self._record(current)["turns"]):
            if not turn.get("discarded"):
                turn["discarded"] = True
                self.save()
                return

    def add_turn(self, n: int, kind: str, turn: dict) -> None:
        self._record(n)["turns"].append({"kind": kind, **turn})
        self.save()

    def claim_follow_up(self) -> int:
        """Reserva la única repregunta permitida para la pregunta actual."""
        current = self.current_number()
        if current is None or not self.is_answered(current):
            raise InterviewError("no_answer_yet", "La repregunta va después de una respuesta.")
        record = self._record(current)
        if record["follow_up_used"]:
            raise InterviewError("follow_up_used", "Esta pregunta ya tuvo su repregunta. Pasa a la siguiente.")
        record["follow_up_used"] = True
        self.save()
        return current

    def release_follow_up(self) -> None:
        """Devuelve la repregunta si no llegó a tener respuesta."""
        self._record(self.current_number())["follow_up_used"] = False
        self.save()

    # ---------- audio de la entrevista ----------

    def add_recording(self, file: str, speaker: str) -> None:
        """Anota un tramo de audio de la ronda en curso, en el orden en que sonó."""
        self.data.setdefault("recording", []).append({"round": self.data["round"], "file": file, "speaker": speaker})
        self.save()

    def recording_count(self) -> int:
        return len(self.data.get("recording", []))

    def recording_of_round(self, round_number: int) -> list[tuple[str, str]]:
        """Tramos (archivo, quién habla) de una ronda, en orden."""
        return [(part["file"], part["speaker"]) for part in self.data.get("recording", [])
                if part["round"] == round_number]

    def progress(self) -> dict:
        start, end = self.data["round_start"], self.data["round_end"]
        answered = sum(1 for p in range(start, end + 1) if self.is_answered(self.number_at(p)))
        return {
            "round": self.data["round"],
            "round_positions": [start, end],
            "answered_in_round": answered,
            "remaining_in_round": end - start + 1 - answered,
            "total_answered": sum(1 for n in range(1, TOTAL_QUESTIONS + 1) if self.is_answered(n)),
        }
