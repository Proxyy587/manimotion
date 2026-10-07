from services.manim_error_parser import parse_manim_error
from services.manim_sanitizer import sanitize_manim_code
from services.manim_validator import validate_manim_code

OLD_CODE = """from manim import *

class Scene(Scene):
    def construct(self):
        axes = Axes(x_range=[-3, 3, 1], y_range=[-1, 9, 1], x_length=6, y_length=4)
        labels = axes.get_axis_labels(x_label="x", y_label="y")
        parabola = axes.get_graph(lambda x: x**2, color=TEAL)
        deriv = axes.get_derivative_graph(parabola, color=YELLOW)
        title = TextMobject("Parabola")
        eq = TexMobject(r"y = x^2")
        self.play(ShowCreation(axes), FadeInFrom(title, UP), FadeInFromDown(eq))
        self.play(ShowCreation(parabola), ShowCreationThenDestruction(deriv))
        self.play(FadeOutAndShift(eq, DOWN))
        self.wait(1)
"""


def test_sanitizer_rewrites_old_manimgl_api():
    code, fixes = sanitize_manim_code(OLD_CODE)
    assert "axes.plot(lambda x: x**2, color=TEAL)" in code
    assert "axes.plot_derivative_graph(parabola" in code
    assert "get_axis_labels" in code
    assert 'Tex("Parabola")' in code
    assert 'MathTex(r"y = x^2")' in code
    assert "Create(axes)" in code
    assert "FadeIn(title, shift=UP)" in code
    assert "FadeIn(eq, shift=UP)" in code
    assert "ShowPassingFlash(deriv)" in code
    assert "FadeOut(eq, shift=DOWN)" in code
    assert any("deprecated API" in f for f in fixes)
    errors = [i for i in validate_manim_code(code) if i.severity == "error"]
    assert errors == []


def test_validator_flags_graphscene():
    code = "from manim import *\nclass Scene(GraphScene):\n    def construct(self):\n        self.setup_axes()\n"
    errors = [i for i in validate_manim_code(code) if i.severity == "error"]
    assert any("GraphScene" in e.message for e in errors)


def test_parser_detects_getter_keyword_error():
    stderr = (
        '30 │ labels = axes.get_axis_labels(x_label="x", y_label="y")\n'
        "❱ 32 │ parabola = axes.get_graph(lambda x: x**2, color=TEAL)\n"
        "TypeError: Mobject.__getattr__.<locals>.getter() got an unexpected keyword argument 'color'"
    )
    info = parse_manim_error(stderr)
    assert info["type"] == "DeprecatedAPI"
    assert "get_graph" in info["message"]
    assert "axes.plot" in info["fix_hint"]


def test_parser_nameerror_old_class():
    info = parse_manim_error("NameError: name 'ShowCreation' is not defined")
    assert "Create" in info["fix_hint"]
