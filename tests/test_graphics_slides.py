import shutil
import subprocess

import pytest

from services.llm import normalize_model
from services.slides.assemble import FPS, LEAD_IN, assemble_continuous, slide_length, stream_durations
from services.slides.graphics import (
    fallback_spec,
    lecture_props,
    normalize_spec,
    repair_spec,
    validate_spec,
)
from services.slides.pipeline import engine_for, style_for
from services.slides.storyboard import _normalize


def _slide(sid=1, n=3, dur=2.0):
    return {
        "id": sid,
        "title": f"Slide {sid}",
        "kind": "timeline",
        "beats": [
            {"text": f"Sentence {i} about the early network.", "on_screen": f"Point {i}", "dur": dur, "audio_dur": dur - 0.3}
            for i in range(n)
        ],
    }


def _timeline(n=3):
    return {
        "layout": "timeline",
        "items": [{"label": str(1969 + 10 * i), "text": f"Milestone {i}"} for i in range(n)],
        "beats": [{"show": [i], "focus": i} for i in range(n)],
    }


def test_valid_timeline_spec_passes():
    assert validate_spec(normalize_spec(_timeline()), 3) == []


def test_spec_validation_catches_common_llm_mistakes():
    spec = normalize_spec({
        "layout": "timeline",
        "items": [{"text": "x" * 80}, {"label": "1991", "text": "Use \\frac{a}{b}"}],
        "beats": [{"show": [1]}, {"show": [0]}, {"show": []}],
    })
    problems = " | ".join(validate_spec(spec, 3))
    assert "max 48" in problems
    assert "LaTeX" in problems
    assert "short label" in problems
    assert "in order" in problems


def test_mechanical_beat_mistakes_are_fixed_without_a_retry():
    spec = normalize_spec({
        "layout": "bullets",
        "items": [{"text": "One"}, {"text": "Two"}, {"text": "Three"}],
        "beats": [{"show": []}, {"show": [0], "focus": 1}, {"show": [1, 2]}, {"show": []}],
    })
    assert validate_spec(spec, 4) == []
    assert spec["beats"][0]["show"] == [0]
    assert spec["beats"][1]["show"] == [1]
    assert spec["beats"][3]["focus"] == 2


def test_currency_is_not_mistaken_for_latex():
    spec = normalize_spec({
        "layout": "stats",
        "items": [{"display": "$4.2B", "text": "Revenue in 2024"}],
        "beats": [{"show": [0], "focus": 0}],
    })
    assert validate_spec(spec, 1) == []


def test_repair_rebuilds_reveal_plan_and_shortens_text():
    spec = normalize_spec(_timeline(4))
    spec["items"][0]["text"] = "A very long milestone description that goes well past the limit"
    spec["beats"] = [{"show": [], "focus": None}] * 2
    fixed = repair_spec(spec, 3)
    assert validate_spec(fixed, 3) == []
    assert len(fixed["items"][0]["text"]) <= 48


def test_fallback_spec_reveals_one_point_per_sentence():
    slide = _slide(n=4)
    slide["beats"][1]["on_screen"] = r"\frac{1}{2}"
    spec = fallback_spec(slide)
    assert validate_spec(spec, 4) == []
    assert "\\" not in spec["items"][1]["text"]


def test_lecture_props_follow_spoken_time():
    slides = [_slide(1, 3, 2.0), _slide(2, 2, 3.0)]
    props = lecture_props({"title": "Internet", "slides": slides}, [_timeline(3), normalize_spec({
        "layout": "bullets",
        "items": [{"text": "One"}, {"text": "Two"}],
        "beats": [{"show": [0, 1], "focus": None}, {"show": [], "focus": 1}],
    })])
    first, second = props["slides"]
    assert first["frames"] == slide_length(slides[0])[1]
    assert first["beatStarts"] == [round(LEAD_IN * FPS), round(2.5 * FPS), round(4.5 * FPS)]
    assert second["reveal"] == [0, 0]
    assert second["focus"] == [-1, 1]
    assert (first["index"], first["total"]) == (1, 2)


def test_model_aliases_map_retired_ids():
    assert normalize_model("anthropic/claude-3.5-sonnet") == "anthropic/claude-sonnet-4.5"
    assert normalize_model(" anthropic/claude-opus-4 ") == "anthropic/claude-opus-4.1"
    assert normalize_model("openai/gpt-4o") == "openai/gpt-4o"
    assert normalize_model("") and normalize_model(None)


def test_style_engine_mapping():
    assert style_for("manim") == "math"
    assert style_for("remotion") == "graphics"
    assert style_for("auto") == style_for(None) == "auto"
    assert engine_for("graphics") == "remotion" and engine_for("math") == "manim"


def test_storyboard_style_is_inferred_when_missing():
    beats = [{"text": "One sentence that is long enough to count here.", "on_screen": "x"}] * 3
    graphics = _normalize({"title": "t", "slides": [{"title": "a", "kind": "timeline", "beats": beats}]})
    math = _normalize({"title": "t", "slides": [{"title": "a", "kind": "graph", "beats": beats}]})
    assert graphics["style"] == "graphics" and math["style"] == "math"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_assemble_continuous_is_frame_exact(tmp_path, monkeypatch):
    monkeypatch.setattr("services.slides.assemble.BURN_CAPTIONS", False)
    slides = [_slide(1, 2, 1.5), _slide(2, 3, 1.2)]
    for slide in slides:
        for i, beat in enumerate(slide["beats"]):
            wav = tmp_path / f"s{slide['id']}_{i}.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                 "-ar", "24000", str(wav)],
                check=True,
            )
            beat["audio"] = str(wav)
    video = tmp_path / "short.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=2",
         "-pix_fmt", "yuv420p", str(video)],
        check=True,
    )
    final, vtt = assemble_continuous(slides, str(video), str(tmp_path), log=lambda *_: None)
    d = stream_durations(final)
    v, a = d["video"], d["audio"]
    expected = sum(slide_length(s)[1] for s in slides) / FPS
    assert abs(v - expected) < 1 / FPS + 1e-6
    assert abs(v - a) <= 0.12
    assert open(vtt, encoding="utf-8").read().startswith("WEBVTT")
