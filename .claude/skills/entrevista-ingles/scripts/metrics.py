"""Medidas de la forma de hablar.

Claude recibe texto, no audio. Estas cifras son lo único que permite hablar de ritmo, pausas
o entonación sin inventarlo. Una medida que no se puede calcular vale None, nunca un valor
aproximado, para que el informe pueda decir que no hay dato.
"""
from __future__ import annotations

import re
from collections import Counter

import numpy as np

PAUSE_S = 0.5
LONG_PAUSE_S = 1.5
LOW_CONFIDENCE = 0.5
MAX_LISTED_WORDS = 15
MIN_VOICED_FRAMES = 20

FILLER_WORDS = {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "eh", "hmm", "hm", "mm", "mmm"}
FILLER_PHRASES = ("you know", "i mean", "sort of", "kind of")


def normalize(word: str) -> str:
    return re.sub(r"[^\w'’-]", "", word).lower()


def _count_fillers(words: list[dict], tokens: list[str]) -> Counter:
    fillers = Counter(token for token in tokens if token in FILLER_WORDS)
    joined = f" {' '.join(tokens)} "
    for phrase in FILLER_PHRASES:
        found = joined.count(f" {phrase} ")
        if found:
            fillers[phrase] = found
    # «like» como muletilla suele ir entre comas; «I like my job» no se debe contar.
    for index, token in enumerate(tokens):
        if token != "like":
            continue
        after_comma = index > 0 and words[index - 1]["w"].endswith(",")
        if words[index]["w"].endswith(",") or after_comma:
            fillers["like"] += 1
    return fillers


def _find_repetitions(tokens: list[str]) -> list[str]:
    repeated: list[str] = []
    for index in range(1, len(tokens)):
        if tokens[index] == tokens[index - 1] and tokens[index] not in FILLER_WORDS:
            repeated.append(f"{tokens[index]} {tokens[index]}")
    for index in range(len(tokens) - 3):
        if tokens[index : index + 2] == tokens[index + 2 : index + 4] and tokens[index] != tokens[index + 1]:
            repeated.append(" ".join(tokens[index : index + 4]))
    return repeated[:MAX_LISTED_WORDS]


def word_metrics(words: list[dict]) -> dict:
    """Ritmo, pausas, muletillas y confianza, a partir de las palabras con sus tiempos."""
    words = [word for word in words if normalize(word["w"])]
    tokens = [normalize(word["w"]) for word in words]
    if len(tokens) < 2:
        return {
            "word_count": len(tokens), "speaking_seconds": None, "words_per_minute": None,
            "articulation_wpm": None, "pause_count": None, "long_pause_count": None,
            "longest_pause_s": None, "total_pause_s": None, "fillers": {}, "filler_total": 0,
            "repetitions": [], "recognition_confidence": None, "unclear_words": [],
        }

    span = words[-1]["end"] - words[0]["start"]
    gaps = [after["start"] - before["end"] for before, after in zip(words, words[1:])]
    pauses = [gap for gap in gaps if gap >= PAUSE_S]
    paused = sum(pauses)
    fillers = _count_fillers(words, tokens)
    unclear = sorted((w for w in words if w["p"] < LOW_CONFIDENCE), key=lambda w: w["p"])

    return {
        "word_count": len(tokens),
        "speaking_seconds": round(span, 1),
        "words_per_minute": round(len(tokens) / span * 60) if span > 0 else None,
        "articulation_wpm": round(len(tokens) / (span - paused) * 60) if span > paused else None,
        "pause_count": len(pauses),
        "long_pause_count": sum(1 for pause in pauses if pause >= LONG_PAUSE_S),
        "longest_pause_s": round(max(pauses), 1) if pauses else 0.0,
        "total_pause_s": round(paused, 1),
        "fillers": dict(fillers),
        "filler_total": sum(fillers.values()),
        "repetitions": _find_repetitions(tokens),
        "recognition_confidence": round(float(np.mean([w["p"] for w in words])), 3),
        "unclear_words": [{"word": normalize(w["w"]), "confidence": w["p"]} for w in unclear[:MAX_LISTED_WORDS]],
    }


def voice_metrics(audio: np.ndarray, rate: int) -> dict:
    """Tono y volumen medidos sobre el audio de la respuesta."""
    empty = {
        "pitch_median_hz": None, "pitch_variation_st": None, "pitch_range_st": None,
        "volume_dbfs": None, "volume_variation_db": None, "clipped_percent": None,
    }
    if audio.size == 0:
        return empty
    result = {**empty, **_volume(audio, rate)}
    try:
        result.update(_pitch(audio, rate))
    except Exception:  # sin tono medible se informa None; no debe tumbar la entrevista
        pass
    return result


def _volume(audio: np.ndarray, rate: int) -> dict:
    block = int(rate * 0.03)
    usable = audio[: audio.size - audio.size % block].reshape(-1, block)
    levels = 20 * np.log10(np.sqrt(np.mean(usable**2, axis=1)) + 1e-10)
    speech = levels[levels > levels.max() - 30]  # descarta las pausas
    return {
        "volume_dbfs": round(float(np.mean(speech)), 1),
        "volume_variation_db": round(float(np.std(speech)), 1),
        "clipped_percent": round(float(np.mean(np.abs(audio) >= 0.99) * 100), 2),
    }


def _pitch(audio: np.ndarray, rate: int) -> dict:
    import parselmouth

    sound = parselmouth.Sound(audio.astype(np.float64), sampling_frequency=rate)
    frequency = sound.to_pitch(time_step=0.01, pitch_floor=75, pitch_ceiling=500).selected_array["frequency"]
    voiced = frequency[frequency > 0]
    if voiced.size < MIN_VOICED_FRAMES:
        return {}
    median = float(np.median(voiced))
    semitones = 12 * np.log2(voiced / median)
    low, high = np.percentile(semitones, [5, 95])
    return {
        "pitch_median_hz": round(median),
        "pitch_variation_st": round(float(np.std(semitones)), 1),
        "pitch_range_st": round(float(high - low), 1),
    }


def _mean(values: list[float | None], digits: int = 1) -> float | None:
    known = [value for value in values if value is not None]
    return round(float(np.mean(known)), digits) if known else None


def aggregate(turns: list[dict]) -> dict | None:
    """Resume las medidas de varios turnos. None si ninguno tiene medidas, como en modo texto."""
    turns = [turn for turn in turns if turn]
    if not turns:
        return None
    seconds = sum(turn.get("speaking_seconds") or 0 for turn in turns)
    words = sum(turn.get("word_count") or 0 for turn in turns)
    pauses = sum(turn.get("pause_count") or 0 for turn in turns)
    fillers: Counter = Counter()
    unclear: dict[str, list[float]] = {}
    for turn in turns:
        fillers.update(turn.get("fillers") or {})
        for item in turn.get("unclear_words") or []:
            unclear.setdefault(item["word"], []).append(item["confidence"])
    ranked = sorted(unclear.items(), key=lambda pair: (-len(pair[1]), min(pair[1])))
    return {
        "answers_measured": len(turns),
        "total_words": words,
        "speaking_seconds": round(seconds, 1),
        "words_per_minute": round(words / seconds * 60) if seconds else None,
        "pauses_per_minute": round(pauses / seconds * 60, 1) if seconds else None,
        "longest_pause_s": max((turn.get("longest_pause_s") or 0 for turn in turns), default=0),
        "fillers": dict(fillers),
        "fillers_per_100_words": round(sum(fillers.values()) / words * 100, 1) if words else None,
        "repetitions": [r for turn in turns for r in turn.get("repetitions") or []][:MAX_LISTED_WORDS],
        "recognition_confidence": _mean([turn.get("recognition_confidence") for turn in turns], digits=3),
        "unclear_words": [
            {"word": word, "times": len(scores), "lowest_confidence": min(scores)}
            for word, scores in ranked[:MAX_LISTED_WORDS]
        ],
        "pitch_variation_st": _mean([turn.get("pitch_variation_st") for turn in turns]),
        "pitch_range_st": _mean([turn.get("pitch_range_st") for turn in turns]),
        "volume_dbfs": _mean([turn.get("volume_dbfs") for turn in turns]),
        "volume_variation_db": _mean([turn.get("volume_variation_db") for turn in turns]),
        "seconds_to_speech_avg": _mean([turn.get("seconds_to_speech") for turn in turns]),
    }
