"""La gráfica acelera la transcripción, pero un fallo suyo no debe tumbar la entrevista.

Los modelos son falsos: aquí importa a qué dispositivo se recurre, no qué se transcribe.
"""
from pathlib import Path

import pytest

import voice
from voice import Transcriber, VoiceError


class FakeModel:
    """`failing` imita una DLL de CUDA ausente o la memoria de la gráfica agotada."""

    def __init__(self, device: str, failing: bool):
        self.device = device
        self.failing = failing

    def transcribe(self, *_args, **_kwargs):
        if self.failing:
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
        return iter([]), None


@pytest.fixture
def machine(monkeypatch):
    """Simula el equipo: qué bibliotecas hay y qué dispositivos fallan."""
    state = {"libraries": True, "broken": set(), "opened": []}

    def open_model(_self, **options):
        device = options["device"]
        state["opened"].append(device)
        return FakeModel(device, device in state["broken"])

    monkeypatch.setattr(voice, "_gpu_libraries", lambda: [Path("gpu")] if state["libraries"] else [])
    monkeypatch.setattr(Transcriber, "_open", open_model)
    return state


def loaded(preference: str = "auto") -> Transcriber:
    transcriber = Transcriber("small.en", preference)
    transcriber._thread.join()
    return transcriber


def test_uses_the_graphics_card_when_it_works(machine):
    assert loaded().device == "cuda"


def test_without_gpu_libraries_it_never_tries_the_graphics_card(machine):
    machine["libraries"] = False
    assert loaded().device == "cpu"
    assert machine["opened"] == ["cpu"]


def test_the_gpu_is_tested_before_trusting_it_because_libraries_load_on_first_use(machine):
    machine["broken"] = {"cuda"}
    transcriber = loaded()
    assert transcriber.device == "cpu"
    assert machine["opened"] == ["cuda", "cpu"]
    assert transcriber.transcribe(Path("respuesta.wav")).text == ""


def test_a_gpu_failure_during_the_interview_repeats_the_turn_on_the_processor(machine):
    transcriber = loaded()
    transcriber._model.failing = True
    assert transcriber.transcribe(Path("respuesta.wav")).text == ""
    assert transcriber.device == "cpu"


def test_the_configuration_can_force_the_processor(machine):
    assert loaded("cpu").device == "cpu"
    assert machine["opened"] == ["cpu"]


def test_a_failure_on_the_processor_is_reported_as_a_voice_error(machine):
    machine["libraries"] = False
    machine["broken"] = {"cpu"}
    with pytest.raises(VoiceError) as error:
        loaded().transcribe(Path("respuesta.wav"))
    assert error.value.code == "stt_failed"
