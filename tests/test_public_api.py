from services.public_api import (
    GENERIC_FAILURE,
    STORAGE_FAILURE,
    engine_for_style,
    public_error,
    public_style,
)


def test_style_maps_to_engine():
    assert engine_for_style("math") == "manim"
    assert engine_for_style("graphics") == "remotion"
    assert engine_for_style("auto") == "auto"
    assert engine_for_style(None) == "auto"
    assert engine_for_style("nonsense") == "auto"


def test_legacy_engine_values_still_work():
    assert engine_for_style(None, "manim") == "manim"
    assert engine_for_style("", "remotion") == "remotion"
    assert engine_for_style("Graphics", "manim") == "remotion"


def test_public_style_hides_engine_names():
    assert public_style("manim") == "math"
    assert public_style("remotion") == "graphics"
    assert public_style("auto") is None
    assert public_style(None) is None


def test_public_error_never_leaks_internals():
    trace = "manim exited 1: Traceback ... LaTeX Error: File `standalone.cls' not found"
    assert public_error(trace) == GENERIC_FAILURE
    assert "manim" not in public_error(trace).lower()
    assert public_error("Remotion render timed out after 900s") == GENERIC_FAILURE
    assert public_error("Upload failed: bucket not found") == STORAGE_FAILURE
    assert public_error(None) == GENERIC_FAILURE
