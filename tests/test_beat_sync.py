"""Beat-locked sync: instrumentation, segment planning, retime math, spoken cues."""

import ast

from services.beat_sync import (
    build_filter_graph,
    compute_retime,
    instrument_beat_marks,
    plan_segments,
)
from services.beat_timing import build_beat_map, build_spoken_cues

CODE = """from manim import *

class Scene(Scene):
    def construct(self):
        # BEAT 1 @ 0.0s (4.0s)
        t = Text("Hi")
        self.play(Write(t))
        if True:
            # BEAT 2 @ 4.0s (3.0s)
            self.wait(1)
        # BEAT 3
        self.wait(1)
"""


def test_instrument_keeps_line_numbers_and_parses():
    out, n = instrument_beat_marks(CODE)
    assert n == 3
    ast.parse(out)
    original = CODE.splitlines()
    new = out.splitlines()
    for i, line in enumerate(original):
        if "# BEAT" in line:
            assert new[i].lstrip().startswith("_clarity_mark(")
            assert "# BEAT" in new[i]
        else:
            assert new[i] == line
    assert '_clarity_mark("2")' in new[8]
    assert new[8].startswith("            _clarity_mark")


def test_instrument_skips_when_no_beats_or_unsafe():
    assert instrument_beat_marks("x = 1\n") == ("x = 1\n", 0)
    tricky = "def f():\n    if a:\n        pass\n    # BEAT 1\n    else:\n        pass\n"
    out, n = instrument_beat_marks(tricky)
    assert n == 0 and out == tricky


def test_plan_segments_pairs_video_and_audio_beats():
    marks = {"1": 0.0, "2": 3.0, "3": 6.0}
    beat_map = {
        "1": {"start_s": 0.0},
        "2": {"start_s": 5.0},
        "3": {"start_s": 9.5},
    }
    segs = plan_segments(marks, 8.0, beat_map, 14.0)
    assert segs == [(0.0, 3.0, 0.0, 5.0), (3.0, 6.0, 5.0, 9.5), (6.0, 8.0, 9.5, 14.0)]


def test_plan_segments_without_marks_is_single_segment():
    assert plan_segments({}, 10.0, {}, 12.0) == [(0.0, 10.0, 0.0, 12.0)]


def test_compute_retime_tracks_audio_boundaries():
    segs = [(0.0, 3.0, 0.0, 5.0), (3.0, 6.0, 5.0, 9.5), (6.0, 8.0, 9.5, 14.0)]
    plan = compute_retime(segs, max_slowdown=1.3, max_speedup=1.6)
    cumulative = 0.0
    for seg, (_, _, a0, a1) in zip(plan, segs):
        cumulative += seg["out"]
        assert abs(cumulative - a1) < 1e-6
        assert 1 / 1.6 - 1e-9 <= seg["factor"] <= 1.3 + 1e-9


def test_compute_retime_carries_overflow():
    # Video beat 1 is far too long for its narration window → overflow carried.
    segs = [(0.0, 10.0, 0.0, 4.0), (10.0, 12.0, 4.0, 12.0)]
    plan = compute_retime(segs, max_slowdown=1.3, max_speedup=1.6)
    assert abs(plan[0]["factor"] - 1 / 1.6) < 1e-9
    total = plan[0]["out"] + plan[1]["out"]
    assert abs(total - 12.0) < 1e-6


def test_filter_graph_shape():
    plan = compute_retime([(0.0, 2.0, 0.0, 4.0)], max_slowdown=1.3, max_speedup=1.6)
    graph = build_filter_graph(plan, 30)
    assert "tpad=stop_mode=clone" in graph
    assert graph.endswith("concat=n=1:v=1:a=0[out]")


def test_spoken_cues_split_on_pauses():
    words = [
        {"word": "The", "start_s": 1.0, "end_s": 1.1, "char_offset": 0},
        {"word": "slope", "start_s": 1.2, "end_s": 1.5, "char_offset": 4, "pause_after": True},
        {"word": "rises", "start_s": 2.0, "end_s": 2.4, "char_offset": 11},
        {"word": "fast", "start_s": 2.5, "end_s": 2.8, "char_offset": 17},
    ]
    cues = build_spoken_cues(words, 1.0, 3.0)
    assert cues == [{"t": 0.0, "text": "The slope"}, {"t": 1.0, "text": "rises fast"}]
    beat_map = build_beat_map(words, {"1": 0, "2": 11}, audio_duration=3.0)
    assert beat_map["2"]["cues"][0]["text"] == "rises fast"
