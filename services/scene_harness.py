"""
Scene timing harness.

Not imported anywhere: `services.beat_sync.instrument_beat_marks` appends this
file's source to every generated scene. It patches manim's Scene so that:

- `_clarity_mark("N")` (inserted at each `# BEAT N`) records the scene clock
  when beat N actually starts on screen;
- per-beat time scales from CLARITY_BEAT_SCALES stretch/compress animations
  ("play"), holds ("wait") and add extra hold time ("pad") so every beat fills
  its narration window;
- any hold longer than a couple of seconds gets gentle emphasis on the newest
  object (Indicate / Circumscribe) so the screen never sits frozen while the
  narrator is talking;
- timing stats are written to CLARITY_BEAT_MARKS as JSON at exit.
"""

import atexit as _clarity_atexit
import json as _clarity_json
import os as _clarity_os

import manim as _clarity_manim

_CLARITY_HOLD_LIMIT = 2.5
_CLARITY_FRAME = 1 / 30

_CLARITY = {
    "beat": "_pre",
    "pending": None,
    "in_wait": False,
    "marks": {},
    "waits": {},
    "wait_list": {},
    "end": 0.0,
    "scales": {},
    "ambient": _clarity_os.environ.get("CLARITY_AMBIENT", "1") != "0",
}
try:
    _CLARITY["scales"] = _clarity_json.loads(
        _clarity_os.environ.get("CLARITY_BEAT_SCALES") or "{}"
    )
except Exception:
    pass

_clarity_orig_play = _clarity_manim.Scene.play
_clarity_orig_wait = _clarity_manim.Scene.wait
_clarity_orig_tear_down = _clarity_manim.Scene.tear_down


def _clarity_mark(beat_id):
    key = str(beat_id)
    if key not in _CLARITY["marks"] and key != _CLARITY["beat"]:
        _CLARITY["pending"] = key


def _clarity_cfg(kind, default):
    try:
        return float(_CLARITY["scales"].get(_CLARITY["beat"], {}).get(kind, default))
    except Exception:
        return default


def _clarity_base_run_time(args, kwargs):
    rt = kwargs.get("run_time")
    if isinstance(rt, (int, float)):
        return float(rt)
    base = 0.0
    for a in args:
        attrs = getattr(a, "__dict__", {})
        if "anim_args" in attrs:  # mob.animate builder
            val = attrs["anim_args"].get("run_time")
        else:
            val = getattr(a, "run_time", None)
        base = max(base, float(val) if isinstance(val, (int, float)) else 1.0)
    return base or 1.0


def _clarity_focus(scene):
    """Newest visible, reasonably sized object on screen (emphasis target)."""
    for mob in reversed(list(scene.mobjects)):
        try:
            if 0.2 < mob.width < 13 and 0.1 < mob.height < 7.5:
                return mob
        except Exception:
            continue
    return None


def _clarity_hold(scene, seconds):
    """Hold for `seconds`; long holds get emphasis instead of a frozen frame."""
    remaining = float(seconds)
    flip = False
    while _CLARITY["ambient"] and remaining > _CLARITY_HOLD_LIMIT:
        target = _clarity_focus(scene)
        if target is None:
            break
        try:
            _clarity_orig_wait(scene, 0.9)
            remaining -= 0.9
            if flip:
                anim = _clarity_manim.Circumscribe(target, fade_out=True, run_time=1.4)
            else:
                anim = _clarity_manim.Indicate(target, scale_factor=1.04, run_time=1.2)
            _clarity_orig_play(scene, anim)
            remaining -= anim.run_time
            flip = not flip
        except Exception:
            break
    if remaining > _CLARITY_FRAME:
        _clarity_orig_wait(scene, remaining)


def _clarity_idle(scene, seconds):
    if seconds <= _CLARITY_FRAME:
        return
    _CLARITY["in_wait"] = True
    try:
        _clarity_hold(scene, seconds)
    finally:
        _CLARITY["in_wait"] = False


def _clarity_advance(scene):
    """Close the current beat (extra hold if scheduled) and start the pending one."""
    nxt = _CLARITY["pending"]
    if nxt is None:
        return
    _CLARITY["pending"] = None
    _clarity_idle(scene, _clarity_cfg("pad", 0.0))
    _CLARITY["beat"] = nxt
    _CLARITY["marks"][nxt] = float(scene.renderer.time)


def _clarity_play(self, *args, **kwargs):
    if _CLARITY["in_wait"]:
        return _clarity_orig_play(self, *args, **kwargs)
    try:
        _clarity_advance(self)
        s = _clarity_cfg("play", 1.0)
        if args and abs(s - 1.0) > 1e-3:
            kwargs["run_time"] = max(
                _CLARITY_FRAME, _clarity_base_run_time(args, kwargs) * s
            )
    except Exception:
        pass
    result = _clarity_orig_play(self, *args, **kwargs)
    _CLARITY["end"] = float(self.renderer.time)
    return result


def _clarity_wait(self, duration=1.0, *args, **kwargs):
    if _CLARITY["in_wait"]:
        return _clarity_orig_wait(self, duration, *args, **kwargs)
    try:
        _clarity_advance(self)
        seconds = max(_CLARITY_FRAME, float(duration) * _clarity_cfg("wait", 1.0))
    except Exception:
        return _clarity_orig_wait(self, duration, *args, **kwargs)
    beat = _CLARITY["beat"]
    _CLARITY["waits"][beat] = _CLARITY["waits"].get(beat, 0.0) + seconds
    _CLARITY["wait_list"].setdefault(beat, []).append(round(seconds, 3))
    _CLARITY["in_wait"] = True
    try:
        if args or kwargs:  # stop_condition / frozen_frame: keep exact semantics
            _clarity_orig_wait(self, seconds, *args, **kwargs)
        else:
            _clarity_hold(self, seconds)
    finally:
        _CLARITY["in_wait"] = False
    _CLARITY["end"] = float(self.renderer.time)


def _clarity_tear_down(self):
    try:
        _clarity_advance(self)
        _clarity_idle(self, _clarity_cfg("pad", 0.0))
        _CLARITY["end"] = float(self.renderer.time)
    except Exception:
        pass
    return _clarity_orig_tear_down(self)


def _clarity_dump():
    path = _clarity_os.environ.get("CLARITY_BEAT_MARKS")
    if not path:
        return
    try:
        with open(path, "w") as fh:
            _clarity_json.dump(
                {
                    "marks": _CLARITY["marks"],
                    "waits": _CLARITY["waits"],
                    "wait_list": _CLARITY["wait_list"],
                    "end": _CLARITY["end"],
                },
                fh,
            )
    except Exception:
        pass


_clarity_manim.Scene.play = _clarity_play
_clarity_manim.Scene.wait = _clarity_wait
_clarity_manim.Scene.tear_down = _clarity_tear_down
_clarity_atexit.register(_clarity_dump)
