"""Beat-locked sync: instrumentation, segment planning, retime math, spoken cues."""

import ast

from services.beat_sync import (
    beat_windows,
    build_filter_graph,
    compute_beat_scales,
    compute_retime,
    format_pacing_feedback,
    instrument_beat_marks,
    plan_segments,
)
from services.beat_timing import build_beat_map, build_spoken_cues
from services.manim_templates import build_guaranteed_manim_code

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


def test_instrument_skips_non_manim_and_unsafe_spots():
    assert instrument_beat_marks("x = 1\n") == ("x = 1\n", 0)
    tricky = (
        "from manim import *\n"
        "def f():\n    if a:\n        pass\n    # BEAT 1\n    else:\n        pass\n"
    )
    out, n = instrument_beat_marks(tricky)
    assert n == 0
    assert out.startswith(tricky.rstrip("\n"))  # comment untouched, harness appended
    assert "_clarity_play" in out


def test_instrument_without_beats_still_adds_harness():
    code = "from manim import *\n\nclass Scene(Scene):\n    def construct(self):\n        self.wait(1)\n"
    out, n = instrument_beat_marks(code)
    assert n == 0 and "_clarity_play" in out
    ast.parse(out)


def _stats(marks, waits, end, wait_list=None):
    return {"marks": marks, "waits": waits, "end": end, "wait_list": wait_list or {}}


def test_beat_windows_merges_close_beats():
    stats = _stats({"1": 0.0, "2": 2.0, "3": 2.05}, {"1": 0.5}, 6.0)
    beat_map = {"1": {"start_s": 0.0}, "2": {"start_s": 5.0}, "3": {"start_s": 9.0}}
    wins = beat_windows(stats, beat_map, 14.0)
    assert [w["members"] for w in wins] == [["_pre", "1"], ["2", "3"]]
    assert wins[0]["id"] == "1"
    assert (wins[1]["v0"], wins[1]["a0"], wins[1]["a1"]) == (2.0, 5.0, 14.0)


def test_compute_beat_scales_stretches_motion_first():
    # 2s of motion, no waits, 4s narration → animations slow 1.8x, rest uncovered
    wins = [{"id": "1", "members": ["1"], "v0": 0, "v1": 2, "a0": 0, "a1": 4, "wait": 0, "wait_list": []}]
    scales, report = compute_beat_scales(wins, max_play_stretch=1.8)
    assert scales["1"]["play"] == 1.8
    assert abs(report["beats"][0]["static"] - 0.4) < 1e-6


def test_short_pauses_are_not_dead_air():
    wins = [
        {
            "id": "1", "members": ["1"], "v0": 0, "v1": 9, "a0": 0, "a1": 9,
            "wait": 6.0, "wait_list": [2.0, 2.0, 2.0],
        }
    ]
    _, report = compute_beat_scales(wins)
    assert report["static_ratio"] == 0.0
    wins[0]["wait_list"] = [6.0]
    _, report = compute_beat_scales(wins)
    assert report["static_ratio"] > 0.3


def test_compute_beat_scales_compresses_long_beats():
    wins = [{"id": "1", "members": ["1"], "v0": 0, "v1": 10, "a0": 0, "a1": 6, "wait": 4, "wait_list": [4]}]
    scales, _ = compute_beat_scales(wins)
    assert scales["1"]["wait"] == 0.3
    assert 0.7 <= scales["1"]["play"] < 1.0


def test_pacing_feedback_flags_static_beats_with_cues():
    report = {
        "static_ratio": 0.5,
        "beats": [{"id": "2", "motion": 1.0, "wait": 0.0, "narration": 8.0, "static": 6.2}],
    }
    plan = {"beats": [{"id": 2, "cues": [{"t": 1.5, "text": "the slope is one"}]}]}
    text = format_pacing_feedback(report, plan)
    assert text.startswith("PACING PROBLEM")
    assert "BEAT 2" in text and "too static" in text and "the slope is one" in text


def test_fallback_template_reveals_each_cue():
    plan = {
        "title": "Slopes",
        "beats": [
            {"id": 1, "duration_sec": 8, "cues": [
                {"t": 0.0, "text": "First point"},
                {"t": 3.0, "text": "Second point"},
            ]},
            {"id": 2, "duration_sec": 6, "narration": "One sentence. Another sentence."},
        ],
    }
    code = build_guaranteed_manim_code("slopes", plan)
    ast.parse(code)
    assert "• First point" in code and "• Second point" in code
    assert "• Another sentence." in code
    assert code.count("# BEAT") == 2
    assert "self.wait(0.00)" not in code


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
