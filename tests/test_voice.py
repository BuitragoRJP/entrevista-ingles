"""Prueba el detector de fin de habla con niveles de energía construidos a mano.

El candidato no debe ser interrumpido (regla 5 de la especificación), así que lo importante es
que una pausa para pensar no cierre la grabación.
"""
import time

import numpy as np
import pytest
import soundfile as sf

import voice
from voice import FRAME_S, Endpointer, ListenSettings

NOISE = 0.002
SPEECH = 0.05


def frames(level: float, seconds: float) -> list[float]:
    return [level] * round(seconds / FRAME_S)


def run(levels: list[float], settings: ListenSettings | None = None) -> tuple[str, Endpointer]:
    endpointer = Endpointer(settings or ListenSettings())
    state = "waiting"
    for level in levels:
        state = endpointer.push(level)
        if state in ("finished", "no_speech", "max_length"):
            break
    return state, endpointer


def test_finishes_after_the_configured_silence():
    state, endpointer = run(frames(NOISE, 1) + frames(SPEECH, 3) + frames(NOISE, 4))
    assert state == "finished"
    assert endpointer.silence == pytest.approx(3.5, abs=0.1)


def test_thinking_pause_shorter_than_the_limit_does_not_cut_the_answer():
    levels = frames(NOISE, 1) + frames(SPEECH, 3) + frames(NOISE, 3.2) + frames(SPEECH, 2)
    state, _ = run(levels)
    assert state == "speaking"


def test_several_pauses_in_a_row_do_not_add_up():
    levels = frames(NOISE, 1)
    for _ in range(5):
        levels += frames(SPEECH, 1) + frames(NOISE, 2.5)
    assert run(levels)[0] == "speaking"


def test_gives_up_when_nobody_speaks():
    state, _ = run(frames(NOISE, 61))
    assert state == "no_speech"


def test_candidate_may_think_for_a_long_time_before_starting():
    state, endpointer = run(frames(NOISE, 45) + frames(SPEECH, 2))
    assert state == "speaking"
    assert endpointer.speech_started_at == pytest.approx(45, abs=0.3)


def test_speaking_right_after_the_beep_is_not_taken_for_background_noise():
    # El ruido real aparece en cuanto hay una pausa entre palabras, y ahí baja el umbral.
    levels = frames(SPEECH, 0.6) + frames(NOISE, 0.1) + frames(SPEECH, 2)
    assert run(levels)[0] == "speaking"


def test_a_short_click_does_not_count_as_speech():
    levels = frames(NOISE, 1) + frames(SPEECH, 0.06) + frames(NOISE, 2)
    state, endpointer = run(levels)
    assert not endpointer.started
    assert state == "waiting"


def test_a_short_click_during_the_final_silence_does_not_extend_the_answer():
    levels = frames(NOISE, 1) + frames(SPEECH, 2) + frames(NOISE, 2) + frames(SPEECH, 0.06) + frames(NOISE, 1.6)
    assert run(levels)[0] == "finished"


def test_works_with_a_noisy_background():
    loud_noise = 0.02
    levels = frames(loud_noise, 1) + frames(0.1, 3) + frames(loud_noise, 4)
    assert run(levels)[0] == "finished"


def test_long_answers_have_a_safety_limit():
    settings = ListenSettings(max_answer_s=5)
    state, _ = run(frames(NOISE, 1) + frames(SPEECH, 10), settings)
    assert state == "max_length"


# ---------- el micrófono y el pitido ----------


def recording(path, *sections):
    """Escribe un WAV a partir de pares (nivel, segundos)."""
    rate = 16000
    parts = [
        level * np.sqrt(2) * np.sin(2 * np.pi * 200 * np.arange(int(rate * seconds)) / rate)
        for level, seconds in sections
    ]
    sf.write(path, np.concatenate(parts).astype("float32"), rate)
    return path


def test_the_microphone_is_listening_before_the_beep_sounds(monkeypatch, tmp_path):
    """Si se abriera después, quien contesta al oír el pitido perdería sus primeras palabras."""
    events = []
    real_microphone = voice._fake_microphone

    def microphone(path, block):
        events.append("micrófono abierto")
        yield from real_microphone(path, block)

    monkeypatch.setattr(voice, "_fake_microphone", microphone)
    wav = recording(tmp_path / "a.wav", (NOISE, 0.5), (SPEECH, 1), (NOISE, 4))
    monkeypatch.setenv("INTERVIEW_FAKE_MIC", str(wav))
    voice.capture(ListenSettings(), cue=lambda: events.append("pitido"))
    assert events == ["micrófono abierto", "pitido"]


def test_the_beep_is_not_mistaken_for_speech(monkeypatch, tmp_path):
    beep_s = 0.4
    wav = recording(tmp_path / "a.wav", (SPEECH, beep_s), (NOISE, 1), (SPEECH, 1), (NOISE, 4))
    monkeypatch.setenv("INTERVIEW_FAKE_MIC", str(wav))
    captured = voice.capture(ListenSettings(), cue=lambda: time.sleep(beep_s))
    assert captured.seconds_to_speech == pytest.approx(1.0, abs=0.1)


def test_an_answer_that_starts_during_the_beep_keeps_its_first_words(monkeypatch, tmp_path):
    wav = recording(tmp_path / "a.wav", (NOISE, 0.2), (SPEECH, 3), (NOISE, 4))
    monkeypatch.setenv("INTERVIEW_FAKE_MIC", str(wav))
    captured = voice.capture(ListenSettings(), cue=lambda: time.sleep(0.4))
    assert len(captured.audio) / captured.sample_rate >= 3.4


def test_a_scripted_candidate_answers_the_turn_it_is_asked(monkeypatch, tmp_path):
    """Una repregunta imprevista no debe desfasar el guion: cada turno busca su grabación."""
    recording(tmp_path / "q05-main-0.wav", (NOISE, 0.5), (SPEECH, 1), (NOISE, 4))
    recording(tmp_path / "q05-follow_up-1.wav", (NOISE, 0.5), (SPEECH, 3), (NOISE, 4))
    recording(tmp_path / "otro.wav", (NOISE, 0.5), (SPEECH, 5), (NOISE, 4))
    monkeypatch.setenv("INTERVIEW_FAKE_MIC", str(tmp_path))

    def seconds_kept(turn: str) -> float:
        captured = voice.capture(ListenSettings(), cue=lambda: None, turn=turn)
        return len(captured.audio) / captured.sample_rate

    assert seconds_kept("q05-main-0") < seconds_kept("q05-follow_up-1") < seconds_kept("q09-main-0")


def test_digital_silence_when_the_microphone_opens_does_not_ruin_the_noise_floor():
    """Muchos micrófonos USB arrancan con ceros. Tomarlos por el ruido de la sala haría que el
    ruido real pareciera voz y la grabación no terminara nunca."""
    room = 0.02
    state, _ = run([0.0] * 10 + frames(room, 1) + frames(room * 10, 2) + frames(room, 4))
    assert state == "finished"


def test_the_noise_floor_is_measured_while_the_beep_sounds():
    endpointer = Endpointer(ListenSettings())
    beep = 0.1
    endpointer.calibrate([0.0] * 3 + [NOISE] * 15 + [beep] * 4 + [NOISE] * 3)
    assert endpointer.noise == pytest.approx(NOISE)


def test_the_joined_interview_keeps_the_order_and_evens_the_volume(tmp_path):
    """El micrófono suele captar al candidato mucho más bajo que la voz del panel; en el audio
    completo deben oírse con un volumen parecido, cada uno en su turno."""

    def tone(name: str, rate: int, seconds: float, level: float):
        moment = np.arange(int(rate * seconds)) / rate
        path = tmp_path / name
        sf.write(path, (level * np.sqrt(2) * np.sin(2 * np.pi * 220 * moment)).astype("float32"), rate)
        return path

    parts = [(tone("pregunta.wav", 24000, 1.0, 0.2), "emma"), (tone("respuesta.wav", 44100, 2.0, 0.02), "candidate")]
    seconds = voice.join_recordings(parts, tmp_path / "entrevista.mp3")
    audio, rate = sf.read(tmp_path / "entrevista.mp3", dtype="float32")

    def level(start: float, end: float) -> float:
        return float(np.sqrt(np.mean(audio[int(start * rate) : int(end * rate)] ** 2)))

    assert seconds == pytest.approx(1.0 + 0.7 + 2.0, abs=0.05)
    assert len(audio) / rate == pytest.approx(seconds, abs=0.15)  # el MP3 añade un relleno mínimo
    assert 0.7 < level(2.0, 3.4) / level(0.2, 0.8) < 1.4
    assert level(1.15, 1.6) < 0.01 * level(0.2, 0.8)  # la pausa entre turnos es silencio
