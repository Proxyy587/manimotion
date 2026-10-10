from services.slides.assemble import FPS, caption_cues, slide_length
from services.slides.build import normalize_body, static_check, wrap_slide
from services.slides.storyboard import _salvage, validate_storyboard


def _beat(text="The derivative measures how fast a function changes at a point.", **kw):
    return {"text": text, "on_screen": "f'(x)", "action": "Show the curve", **kw}


def _storyboard(n_slides=3, n_beats=3):
    return {
        "title": "Derivatives",
        "slides": [
            {"id": i + 1, "title": f"Slide {i + 1}", "kind": "bullets", "beats": [_beat() for _ in range(n_beats)]}
            for i in range(n_slides)
        ],
    }


def test_valid_storyboard_has_no_problems():
    assert validate_storyboard(_storyboard()) == []


def test_storyboard_rejects_math_in_speech_and_bad_counts():
    sb = _storyboard(n_slides=2, n_beats=2)
    sb["slides"][0]["beats"][0]["text"] = "We compute x^2 using the power rule right here today."
    problems = validate_storyboard(sb)
    assert any("3–20 slides" in p for p in problems)
    assert any("3–6 beats" in p for p in problems)
    assert any("math symbols" in p for p in problems)


def test_salvage_splits_long_slides_and_strips_symbols():
    sb = _storyboard(n_slides=1, n_beats=8)
    sb["slides"][0]["beats"][0]["text"] = "Say x^2 out loud in plain words for everyone."
    fixed = _salvage(sb)
    assert [len(s["beats"]) for s in fixed["slides"]] == [6, 2]
    assert "^" not in fixed["slides"][0]["beats"][0]["text"]
    assert [s["id"] for s in fixed["slides"]] == [1, 2]


GOOD_BODY = """
pts = self.bullets(["one", "two"], zone="full")
self.beat(0, FadeIn(pts[0]))
self.beat(1, FadeIn(pts[1]))
self.beat(2)
"""


def test_static_check_accepts_good_body():
    assert static_check(GOOD_BODY, 3) == []


def test_static_check_flags_play_unknown_names_and_beat_order():
    body = GOOD_BODY + "\nself.play(Create(Checkmark()))\n"
    problems = " ".join(static_check(body, 4))
    assert "self.play()" in problems
    assert "Checkmark" in problems
    assert "need each of 0..3" in problems


def test_static_check_flags_words_and_percent_in_mathtex():
    body = (
        'a = MathTex(r"Tangent Line")\n'
        'b = MathTex(r"P(\\text{Disease} \\mid \\text{Positive}) = 0.99")\n'
        'c = MathTex(r"99% accurate")\n'
        "self.beat(0, FadeIn(a), FadeIn(b))\nself.beat(1, FadeIn(c))\n"
    )
    problems = static_check(body, 2)
    assert any("'Tangent'" in p for p in problems)
    assert any("Escape %" in p for p in problems)
    assert not any("Disease" in p for p in problems)


def test_static_check_flags_latex_in_plain_text():
    body = (
        'rows = self.bullets(["Positive test $\\\\Rightarrow$ sick?", "Plain words"], "full")\n'
        "self.beat(0, FadeIn(rows[0]))\nself.beat(1, FadeIn(rows[1]))\n"
    )
    assert any("contains LaTeX" in p for p in static_check(body, 2))


def test_static_check_reports_syntax_error():
    assert any("SyntaxError" in p for p in static_check("self.beat(0, FadeIn(", 1))


def test_normalize_body_strips_fences_and_def():
    raw = "```python\ndef build(self):\n    self.beat(0)\n```"
    assert normalize_body(raw) == "self.beat(0)"


def test_wrap_slide_injects_header_and_indents():
    src = wrap_slide("self.beat(0)", "Title's", [{"text": "Hi there", "dur": 2.0, "audio": "x"}])
    compile(src, "slide.py", "exec")
    assert "class Scene(SlideScene):" in src
    assert "        self.beat(0)" in src
    assert "'audio'" not in src


def test_slide_length_is_frame_exact():
    slide = {"beats": [{"dur": 2.351}, {"dur": 3.0}]}
    t, frames = slide_length(slide)
    assert abs(t - (0.5 + 5.351 + 1.2 + 0.4)) < 1e-9
    assert frames == round(t * FPS)


def test_caption_cues_follow_spoken_time():
    slide = {
        "beats": [
            {"text": "Short sentence here.", "dur": 2.35, "audio_dur": 2.0},
            {"text": "word " * 25, "dur": 5.35, "audio_dur": 5.0},
        ]
    }
    cues = caption_cues(slide, offset=10.0)
    assert cues[0][0] == 10.5 and abs(cues[0][1] - 12.5) < 1e-9
    second = [c for c in cues if c[0] >= 12.85 - 1e-9]
    assert abs(second[0][0] - 12.85) < 1e-9
    assert abs(second[-1][1] - (12.85 + 5.0)) < 1e-6
    assert all(len(line) <= 46 for c in cues for line in c[2].split("\n"))
    assert all(c[2].count("\n") <= 1 for c in cues)
