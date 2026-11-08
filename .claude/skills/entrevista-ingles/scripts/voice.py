"""Boca y oído del panel: síntesis, reproducción, captura y transcripción.

Dos variables de entorno permiten probar todo sin hardware:
  INTERVIEW_MUTE=1                no reproduce ni sintetiza audio
  INTERVIEW_FAKE_MIC=<wav|carpeta>  usa ese archivo en lugar del micrófono; con una carpeta,
                                  cada turno toma el WAV con su nombre (un candidato con guion)
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

# Evita avisos en la salida y consultas de red al cargar un modelo ya descargado.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

FRAME_S = 0.03
TTS_TIMEOUT_S = 15
TTS_ATTEMPTS = 2

# Las disfluencias de este texto animan a Whisper a transcribir lo que se dice de verdad,
# en lugar de devolver una versión limpia que ocultaría errores al evaluador.
VERBATIM_PROMPT = "Um, well, I, I think that, uh, I has worked, you know, like, in a company. Hmm, let me think."


class VoiceError(Exception):
    """Fallo de audio con un código legible por máquina."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def muted() -> bool:
    return os.environ.get("INTERVIEW_MUTE") == "1"


# ---------------------------------------------------------------------------
# Detección de inicio y fin de habla
# ---------------------------------------------------------------------------


@dataclass
class ListenSettings:
    end_silence_s: float = 3.5
    start_timeout_s: float = 60.0
    max_answer_s: float = 240.0


class Endpointer:
    """Decide cuándo empieza y acaba de hablar el candidato según la energía por trama.

    No toca el audio, así que se prueba con niveles sintéticos. Sigue el ruido de fondo por
    mínimos para que hablar justo tras el pitido no se confunda con ruido ambiente.
    """

    START_RATIO = 3.0  # sobre el ruido para considerar que empezó a hablar
    KEEP_RATIO = 2.0  # sobre el ruido para seguir considerándolo voz
    MIN_LEVEL = 10 ** (-60 / 20)  # por debajo de -60 dBFS no hay voz utilizable
    MIN_START_S = 0.25  # voz acumulada para descartar golpes y clics
    MIN_RESUME_S = 0.09  # voz seguida para reiniciar el contador de silencio
    NOISE_RISE_PER_FRAME = 1.001

    def __init__(self, settings: ListenSettings):
        self.settings = settings
        self.noise: float | None = None
        self.started = False
        self.elapsed = 0.0
        self.voiced = 0.0
        self.silence = 0.0
        self.speech_started_at: float | None = None

    def calibrate(self, levels: list[float]) -> None:
        """Mide el ruido de fondo con lo captado mientras sonaba el aviso.

        El cuartil inferior ignora el pitido y a quien ya había empezado a contestar.
        """
        heard = [level for level in levels if level > 0]
        if heard:
            self.noise = float(np.percentile(heard, 25))

    def _track_noise(self, level: float) -> float:
        # Una trama a cero es el micrófono arrancando; no dice nada del ruido de la sala.
        if level > 0:
            if self.noise is None or level < self.noise:
                self.noise = level
            else:
                self.noise *= self.NOISE_RISE_PER_FRAME
        return max(self.noise or 0.0, self.MIN_LEVEL)

    def push(self, level: float) -> str:
        """Procesa una trama y devuelve waiting, speaking, finished, no_speech o max_length."""
        self.elapsed += FRAME_S
        floor = self._track_noise(level)

        if not self.started:
            if level > floor * self.START_RATIO:
                self.voiced += FRAME_S
            else:
                self.voiced = max(0.0, self.voiced - FRAME_S / 2)
            if self.voiced >= self.MIN_START_S:
                self.started = True
                self.speech_started_at = self.elapsed - self.voiced
                self.voiced = 0.0
                return "speaking"
            return "no_speech" if self.elapsed >= self.settings.start_timeout_s else "waiting"

        if self.elapsed - self.speech_started_at >= self.settings.max_answer_s:
            return "max_length"
        self.voiced = self.voiced + FRAME_S if level > floor * self.KEEP_RATIO else 0.0
        self.silence = 0.0 if self.voiced >= self.MIN_RESUME_S else self.silence + FRAME_S
        return "finished" if self.silence >= self.settings.end_silence_s else "speaking"


# ---------------------------------------------------------------------------
# Captura
# ---------------------------------------------------------------------------


@dataclass
class Capture:
    status: str  # ok | no_speech
    audio: np.ndarray
    sample_rate: int
    seconds_to_speech: float | None = None
    truncated: bool = False


def resolve_device(name: str | None, kind: str) -> int | None:
    """Convierte parte del nombre de un dispositivo en su índice. None es el predeterminado."""
    if not name:
        return None
    import sounddevice as sd

    channels = "max_input_channels" if kind == "input" else "max_output_channels"
    for index, device in enumerate(sd.query_devices()):
        if name.lower() in device["name"].lower() and device[channels] > 0:
            return index
    raise VoiceError("device_not_found", f"No hay ningún dispositivo de {kind} que contenga '{name}'.")


def _microphone(device: int | None, rate: int, block: int) -> Iterator[np.ndarray]:
    import sounddevice as sd

    frames: queue.Queue[np.ndarray] = queue.Queue()

    def on_audio(indata, _frames, _time, _status) -> None:
        frames.put(indata[:, 0].copy())

    try:
        stream = sd.InputStream(
            device=device, samplerate=rate, channels=1, dtype="float32", blocksize=block, callback=on_audio
        )
    except Exception as error:
        raise VoiceError("mic_open_failed", f"No se pudo abrir el micrófono: {error}") from error
    with stream:
        while True:
            try:
                yield frames.get(timeout=3)
            except queue.Empty:
                raise VoiceError("mic_stalled", "El micrófono dejó de enviar audio.") from None


def _fake_microphone(path: str, block: int) -> Iterator[np.ndarray]:
    import soundfile as sf

    audio, _ = sf.read(path, dtype="float32", always_2d=True)
    audio = audio[:, 0]
    for start in range(0, len(audio) - block + 1, block):
        yield audio[start : start + block]
    while True:
        yield np.zeros(block, dtype="float32")


def _fake_recording(source: str, turn: str) -> str:
    """Con una carpeta, toma la grabación de ese turno: así el candidato contesta a lo que se le
    pregunta aunque el panel añada una repregunta. `otro.wav` cubre los turnos sin grabación."""
    folder = Path(source)
    if not folder.is_dir():
        return source
    recording = folder / f"{turn}.wav"
    return str(recording if recording.exists() else folder / "otro.wav")


def _level(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(block**2)))


def capture(settings: ListenSettings, device: int | None = None, *, cue, turn: str = "") -> Capture:
    """Graba desde que el candidato empieza a hablar hasta que termina.

    `cue` es el aviso de que puede hablar. Suena con el micrófono ya abierto, porque abrirlo
    tarda unas décimas y quien contesta al oír el pitido perdería sus primeras palabras.
    `turn` solo sirve al micrófono simulado, para elegir la grabación.
    """
    fake = os.environ.get("INTERVIEW_FAKE_MIC")
    if fake:
        import soundfile as sf

        fake = _fake_recording(fake, turn)
        rate = sf.info(fake).samplerate
        blocks = _fake_microphone(fake, int(rate * FRAME_S))
    else:
        import sounddevice as sd

        info = sd.query_devices(device if device is not None else sd.default.device[0])
        # La frecuencia nativa evita errores de dispositivos que no aceptan 16 kHz.
        rate = int(info["default_samplerate"])
        blocks = _microphone(device, rate, int(rate * FRAME_S))

    endpointer = Endpointer(settings)
    preroll: deque[np.ndarray] = deque(maxlen=int(0.75 / FRAME_S))
    kept: list[np.ndarray] = []

    early = [next(blocks)]  # no sigue hasta que el micrófono entregue audio de verdad
    started = time.perf_counter()
    cue()
    # Lo captado durante el aviso no se analiza, para que el pitido no cuente como voz, pero se
    # conserva por si el candidato ya había empezado a hablar.
    early.extend(next(blocks) for _ in range(int((time.perf_counter() - started) / FRAME_S)))
    preroll.extend(early)
    endpointer.calibrate([_level(block) for block in early])

    for block in blocks:
        state = endpointer.push(_level(block))
        if state == "waiting":
            preroll.append(block)
        elif state == "no_speech":
            return Capture("no_speech", np.zeros(0, dtype="float32"), rate)
        else:
            if not kept:
                kept.extend(preroll)  # conserva el inicio de la primera palabra
            kept.append(block)
            if state in ("finished", "max_length"):
                break

    # Quita el silencio final, que solo sirvió para decidir que había terminado.
    excess = max(0, int((endpointer.silence - 0.4) / FRAME_S))
    if excess:
        kept = kept[:-excess]
    return Capture(
        "ok",
        np.concatenate(kept),
        rate,
        seconds_to_speech=round(endpointer.speech_started_at, 2),
        truncated=state == "max_length",
    )


def save_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, rate, subtype="PCM_16")


# ---------------------------------------------------------------------------
# Transcripción
# ---------------------------------------------------------------------------


@dataclass
class Transcript:
    text: str
    words: list[dict]


def _gpu_libraries() -> list[Path]:
    """Carpetas de las DLL de CUDA, que `setup.py` instala solo si encuentra una gráfica NVIDIA."""
    nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    folders = [nvidia / "cublas" / "bin", nvidia / "cudnn" / "bin"]
    return folders if all(folder.is_dir() for folder in folders) else []


class Transcriber:
    """Whisper local. Carga el modelo en segundo plano para que esté listo al terminar de grabar.

    Usa la gráfica si puede (0,3 s por turno frente a unos 2 s) y, si falla, sigue con el
    procesador: la entrevista no debe caerse por eso. `preference` es "auto" o "cpu".
    """

    def __init__(self, model_name: str, preference: str = "auto"):
        self.model_name = model_name
        self.preference = preference
        self.device: str | None = None
        self._model = None
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._load, daemon=True)
        self._thread.start()

    def _open(self, **options):
        from faster_whisper import WhisperModel

        try:
            return WhisperModel(self.model_name, local_files_only=True, **options)
        except FileNotFoundError:  # aún no está descargado
            return WhisperModel(self.model_name, **options)

    def _load(self) -> None:
        try:
            if self.preference == "cpu" or not self._load_gpu():
                self._load_cpu()
        except Exception as error:
            self._error = error

    def _load_gpu(self) -> bool:
        folders = _gpu_libraries()
        if not folders:
            return False
        os.environ["PATH"] = os.pathsep.join([*map(str, folders), os.environ.get("PATH", "")])
        try:
            model = self._open(device="cuda", compute_type="int8_float16")
            # Abrir el modelo no toca las DLL de CUDA: solo se cargan al usarlo por primera vez.
            segments, _ = model.transcribe(
                np.zeros(16000, dtype="float32"), language="en", beam_size=1, temperature=0.0
            )
            list(segments)
        except Exception:
            return False
        self._model, self.device = model, "cuda"
        return True

    def _load_cpu(self) -> None:
        threads = max(4, (os.cpu_count() or 8) * 3 // 4)
        self._model = self._open(device="cpu", compute_type="int8", cpu_threads=threads)
        self.device = "cpu"

    def transcribe(self, path: Path) -> Transcript:
        self._thread.join()
        if self._error is not None:
            raise VoiceError("stt_failed", f"No se pudo cargar Whisper: {self._error}")
        try:
            return self._decode(path)
        except Exception as error:
            if self.device != "cuda":
                raise VoiceError("stt_failed", f"Whisper falló: {error}") from error
        try:  # p. ej. otro programa agotó la memoria de la gráfica a mitad de entrevista
            self._load_cpu()
            return self._decode(path)
        except Exception as error:
            raise VoiceError("stt_failed", f"Whisper falló: {error}") from error

    def _decode(self, path: Path) -> Transcript:
        segments, _ = self._model.transcribe(
            str(path),
            language="en",
            beam_size=1,  # mismos errores conservados que con 5, algo más rápido
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=VERBATIM_PROMPT,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 1500, "speech_pad_ms": 300},
        )
        text_parts: list[str] = []
        words: list[dict] = []
        for segment in segments:
            text_parts.append(segment.text.strip())
            for word in segment.words or []:
                words.append(
                    {
                        "w": word.word.strip(),
                        "start": round(float(word.start), 2),
                        "end": round(float(word.end), 2),
                        "p": round(float(word.probability), 3),
                    }
                )
        return Transcript(" ".join(text_parts).strip(), words)


# ---------------------------------------------------------------------------
# Síntesis y reproducción
# ---------------------------------------------------------------------------


async def _edge_tts_bytes(text: str, voice: str, rate: str) -> bytes:
    import edge_tts

    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    if not audio:
        raise VoiceError("tts_empty", "El servicio de voz no devolvió audio.")
    return bytes(audio)


def _synthesize_edge(text: str, voice: str, rate: str, cache_dir: Path) -> bytes:
    cached = cache_dir / (hashlib.sha1(f"{voice}|{rate}|{text}".encode()).hexdigest() + ".mp3")
    if cached.exists():
        return cached.read_bytes()
    last_error: Exception | None = None
    for _ in range(TTS_ATTEMPTS):
        try:
            audio = asyncio.run(asyncio.wait_for(_edge_tts_bytes(text, voice, rate), TTS_TIMEOUT_S))
        except Exception as error:
            last_error = error
            continue
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(audio)
        return audio
    raise VoiceError("tts_failed", f"Falló la voz en línea: {last_error}")


def _synthesize_windows(text: str) -> bytes:
    """Respaldo sin internet con la voz en inglés de Windows."""
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$s.SelectVoice('Microsoft Zira Desktop');"
        "$s.SetOutputToWaveFile($env:IV_WAV);"
        "$s.Speak($env:IV_TEXT);"
        "$s.Dispose()"
    )
    with tempfile.TemporaryDirectory() as folder:
        wav = Path(folder) / "speech.wav"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "IV_WAV": str(wav), "IV_TEXT": text},
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0 or not wav.exists():
            raise VoiceError("tts_failed", "Tampoco funcionó la voz de Windows.")
        return wav.read_bytes()


def synthesize(text: str, voice: str, rate: str, cache_dir: Path) -> tuple[np.ndarray, int, str]:
    """Devuelve audio, frecuencia y motor usado: edge, o windows si falló la voz en línea."""
    import soundfile as sf

    try:
        encoded, engine = _synthesize_edge(text, voice, rate, cache_dir), "edge"
    except VoiceError:
        encoded, engine = _synthesize_windows(text), "windows"
    audio, sample_rate = sf.read(io.BytesIO(encoded), dtype="float32", always_2d=True)
    return audio[:, 0], sample_rate, engine


def play(audio: np.ndarray, rate: int, device: int | None = None) -> None:
    if muted():
        return
    import sounddevice as sd

    # El relleno evita que algunos auriculares se coman el inicio y el final de la frase.
    padding = np.zeros(int(rate * 0.12), dtype="float32")
    try:
        sd.play(np.concatenate([padding, audio, padding]), rate, device=device, blocking=True)
    except Exception as error:
        raise VoiceError("playback_failed", f"No se pudo reproducir el audio: {error}") from error


@dataclass
class Speech:
    """Lo que dijo el panel en una llamada: el motor de voz usado y el audio de cada frase."""

    engine: str  # edge | windows | muted
    clips: list[tuple[np.ndarray, int]]


def speak(lines: list[tuple[str, str]], rate: str, cache_dir: Path, device: int | None = None) -> Speech:
    """Pronuncia pares (texto, voz) seguidos. Sintetiza todo antes para que no haya huecos.

    Sin sonido, cada frase es un silencio breve, para que las pruebas recorran también el guardado
    del audio de la entrevista.
    """
    spoken = [line for line in lines if line[0].strip()]
    if muted():
        return Speech("muted", [(np.zeros(2400, dtype="float32"), 24000) for _ in spoken])
    with ThreadPoolExecutor(max_workers=max(1, len(spoken))) as pool:  # cada frase tarda 1 s de red
        clips = list(pool.map(lambda line: synthesize(line[0], line[1], rate, cache_dir), spoken))
    for audio, sample_rate, _ in clips:
        play(audio, sample_rate, device)
    engine = "windows" if any(engine == "windows" for *_, engine in clips) else "edge"
    return Speech(engine, [(audio, sample_rate) for audio, sample_rate, _ in clips])


def beep(frequency: int, device: int | None = None) -> None:
    """Pitido suave: avisa al candidato de que el micrófono se abrió o se cerró."""
    rate = 24000
    moment = np.arange(int(rate * 0.12)) / rate
    fade = np.minimum(1.0, np.minimum(moment, moment[::-1]) / 0.015)
    play((0.15 * np.sin(2 * np.pi * frequency * moment) * fade).astype("float32"), rate, device)


# ---------------------------------------------------------------------------
# Audio completo de la entrevista
# ---------------------------------------------------------------------------

JOINED_RATE = 44100
JOINED_LEVEL = 0.1  # -20 dBFS mientras alguien habla
MAX_GAIN = 10.0  # +20 dB como mucho, para no subir el ruido de fondo de un micrófono muy bajo


def _resample(audio: np.ndarray, rate: int, target: int) -> np.ndarray:
    """Interpolación lineal: basta para escuchar una conversación."""
    if rate == target or len(audio) == 0:
        return audio
    length = int(round(len(audio) * target / rate))
    return np.interp(np.arange(length) * rate / target, np.arange(len(audio)), audio).astype("float32")


def _even_loudness(audio: np.ndarray, rate: int) -> np.ndarray:
    """Lleva cada tramo al mismo volumen. El micrófono suele captar al candidato mucho más bajo que
    la voz sintética del panel, y sin esto costaría oírse a uno mismo."""
    frame = int(rate * 0.05)
    if len(audio) < frame:
        return audio
    frames = audio[: len(audio) // frame * frame].reshape(-1, frame)
    speech = float(np.percentile(np.sqrt(np.mean(frames**2, axis=1)), 90))
    peak = float(np.max(np.abs(audio)))
    if speech < 1e-4:
        return audio  # silencio: no hay nada que igualar
    return audio * min(JOINED_LEVEL / speech, 0.9 / peak, MAX_GAIN)


def join_recordings(parts: list[tuple[Path, str]], destination: Path) -> float:
    """Une los tramos (archivo, quién habla) en un MP3, en orden y con una pausa breve entre ellos,
    más corta si sigue hablando la misma persona. Devuelve la duración en segundos."""
    import soundfile as sf

    destination.parent.mkdir(parents=True, exist_ok=True)
    samples, previous = 0, None
    with sf.SoundFile(destination, "w", samplerate=JOINED_RATE, channels=1, format="MP3") as joined:
        for path, speaker in parts:
            audio, rate = sf.read(path, dtype="float32", always_2d=True)
            audio = _even_loudness(_resample(audio[:, 0], rate, JOINED_RATE), JOINED_RATE)
            if previous is not None:
                pause = np.zeros(int(JOINED_RATE * (0.3 if speaker == previous else 0.7)), dtype="float32")
                joined.write(pause)
                samples += len(pause)
            joined.write(audio.astype("float32"))
            samples += len(audio)
            previous = speaker
    return samples / JOINED_RATE


def measure_microphone(device: int | None = None, seconds: float = 1.0) -> dict:
    """Mide la señal real del micrófono para distinguir ruido ambiente de silencio digital."""
    import sounddevice as sd

    info = sd.query_devices(device if device is not None else sd.default.device[0])
    rate = int(info["default_samplerate"])
    started = time.perf_counter()
    audio = sd.rec(int(rate * seconds), samplerate=rate, channels=1, dtype="float32", device=device, blocking=True)
    level = float(np.sqrt(np.mean(audio**2)))
    return {
        "name": info["name"],
        "sample_rate": rate,
        "level_dbfs": round(20 * np.log10(level), 1) if level > 0 else None,
        "open_seconds": round(time.perf_counter() - started - seconds, 2),
        "receiving_signal": level > 1e-6,
    }
