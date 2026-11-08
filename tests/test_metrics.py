import numpy as np
import pytest

from metrics import aggregate, voice_metrics, word_metrics


def make_words(text: str, gap: float = 0.1, duration: float = 0.3, p: float = 0.9) -> list[dict]:
    words, clock = [], 0.0
    for word in text.split():
        words.append({"w": word, "start": round(clock, 2), "end": round(clock + duration, 2), "p": p})
        clock += duration + gap
    return words


def test_words_per_minute_is_computed_from_real_timing():
    # 60 palabras repartidas en exactamente 30 segundos son 120 por minuto.
    words = [{"w": f"word{i}", "start": i * 0.5, "end": i * 0.5 + 0.5, "p": 0.9} for i in range(60)]
    assert word_metrics(words)["words_per_minute"] == 120


def test_pauses_are_counted_and_long_ones_are_flagged():
    words = make_words("one two three")
    words[1]["start"], words[1]["end"] = 1.0, 1.3  # hueco de 0,7 s
    words[2]["start"], words[2]["end"] = 3.3, 3.6  # hueco de 2,0 s
    result = word_metrics(words)
    assert result["pause_count"] == 2
    assert result["long_pause_count"] == 1
    assert result["longest_pause_s"] == 2.0
    assert result["articulation_wpm"] > result["words_per_minute"]


def test_fillers_are_counted():
    result = word_metrics(make_words("Um, I think, uh, you know, it was, um, fine"))
    assert result["fillers"]["um"] == 2
    assert result["fillers"]["uh"] == 1
    assert result["fillers"]["you know"] == 1


def test_like_is_only_a_filler_between_commas():
    assert "like" not in word_metrics(make_words("I like my job a lot"))["fillers"]
    assert word_metrics(make_words("It was, like, really hard"))["fillers"]["like"] == 1


def test_repetitions_are_detected():
    result = word_metrics(make_words("I I think I think the the plan worked"))
    assert "i i" in result["repetitions"]
    assert "the the" in result["repetitions"]
    assert "i think i think" in result["repetitions"]


def test_unclear_words_are_listed_from_worst_to_best():
    words = make_words("my thorough colleague arrived")
    words[1]["p"], words[2]["p"] = 0.2, 0.4
    assert [item["word"] for item in word_metrics(words)["unclear_words"]] == ["thorough", "colleague"]


def test_no_invented_values_without_words():
    result = word_metrics([])
    assert result["word_count"] == 0
    assert result["words_per_minute"] is None
    assert result["recognition_confidence"] is None


def _tone(frequencies: np.ndarray, rate: int = 16000) -> np.ndarray:
    phase = 2 * np.pi * np.cumsum(frequencies) / rate
    return (0.3 * (np.sin(phase) + 0.5 * np.sin(2 * phase))).astype("float32")


def test_flat_and_expressive_voices_are_clearly_different():
    rate = 16000
    moment = np.arange(rate * 3) / rate
    flat = voice_metrics(_tone(np.full(moment.size, 150.0)), rate)
    varied = voice_metrics(_tone(150 * 2 ** (6 * np.sin(2 * np.pi * 1.5 * moment) / 12)), rate)
    assert flat["pitch_variation_st"] < 0.5
    assert varied["pitch_variation_st"] > 3
    assert flat["pitch_median_hz"] == pytest.approx(150, abs=3)


def test_silence_gives_no_pitch_instead_of_an_invented_value():
    result = voice_metrics(np.zeros(16000, dtype="float32"), 16000)
    assert result["pitch_variation_st"] is None


def test_clipping_is_reported():
    audio = np.tile(np.array([1.0, -1.0, 0.1, -0.1], dtype="float32"), 4000)
    assert voice_metrics(audio, 16000)["clipped_percent"] == pytest.approx(50, abs=1)


def test_aggregate_weights_rate_by_time_and_merges_counts():
    first = {**word_metrics(make_words("um one two three four five")), "pitch_variation_st": 2.0}
    second = {**word_metrics(make_words("um six seven")), "pitch_variation_st": 4.0}
    result = aggregate([first, second])
    assert result["answers_measured"] == 2
    assert result["total_words"] == 9
    assert result["fillers"]["um"] == 2
    assert result["pitch_variation_st"] == 3.0


def test_aggregate_without_voice_data_returns_none():
    assert aggregate([]) is None
    assert aggregate([None, None]) is None
