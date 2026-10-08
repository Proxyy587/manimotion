import asyncio
import os
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from prompts.manim_prompt import MANIM_ERROR_HINTS
from router import route_prompt
from services.audio import generate_audio_with_captions
from services.beat_timing import apply_measured_timings_to_plan
from services.config import (
    cleanup_job_dir,
    job_work_dir,
    keep_local_outputs,
    storage_policy,
)
from services.llm import (
    DEFAULT_MODEL,
    NARRATION_MODEL,
    beat_sheet_target_duration,
    format_beat_sheet_for_prompt,
    generate_manim_code,
    generate_narration_script,
    generate_remotion_code,
    generate_visual_plan,
)
from services.merger import merge_video_audio_captions
from services.remotion_renderer import render_remotion
from services.renderer import get_media_duration, render_video
from services.storage import upload_to_r2
from services.user_storage import UserStorageConfig


def _default_max_attempts() -> int:
    raw = (os.getenv("MANIM_MAX_ATTEMPTS") or "3").strip()
    try:
        return max(1, min(int(raw), 5))
    except ValueError:
        return 3


def log(msg: str):
    print(msg, flush=True)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _apply_plan_quality(
    video_path: str,
    output_dir: str,
    *,
    watermark: bool,
    max_height: int,
    log_fn=log,
) -> str:
    """
    Free-tier polish: downscale to 720p and burn a light watermark.
    Paid / master: return path unchanged.
    """
    if not watermark and max_height >= 1080:
        return video_path
    if not video_path or not os.path.isfile(video_path):
        return video_path

    out = os.path.join(output_dir, "final_tier.mp4")
    filters: list[str] = []
    if max_height < 1080:
        filters.append(f"scale=-2:{max_height}")
    if watermark:
        # Escaped drawtext for ffmpeg
        filters.append(
            "drawtext=text='manimotion':fontsize=28:fontcolor=white@0.45:"
            "x=w-tw-40:y=h-th-36"
        )
    vf = ",".join(filters) if filters else None
    cmd = ["ffmpeg", "-y", "-i", video_path]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-c:a", "copy", "-movflags", "+faststart", out]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        log_fn(f"  🏷️ Plan quality applied (h≤{max_height}, watermark={watermark})")
        return out
    except Exception as exc:
        log_fn(f"  ⚠️ Plan quality step skipped: {exc}")
        return video_path


def _r2_object_key(job_id: str, suffix: str = "final") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_job = (job_id or uuid.uuid4().hex).replace("/", "-")
    return f"videos/{safe_job}/{stamp}_{suffix}.mp4"


async def _run_manim_pipeline(
    topic: str,
    model: str,
    visual_plan: dict[str, Any],
    duration: Optional[int],
    complexity: str,
    output_dir: str,
    max_attempts: int = 3,
    audio_duration: Optional[float] = None,
    manim_quality: Optional[str] = None,
    tier: Optional[str] = None,
    beat_map: Optional[dict[str, Any]] = None,
) -> tuple[Optional[str], Optional[str]]:
    from services.beat_sync import (
        beat_windows,
        compute_beat_scales,
        format_pacing_feedback,
        instrument_beat_marks,
        read_beat_marks,
        read_beat_stats,
        retime_to_beats,
    )
    from services.example_store import save_successful_example
    from services.manim_attempt_models import get_model_for_manim_attempt
    from services.manim_error_parser import build_retry_prompt, parse_manim_error
    from services.manim_sanitizer import sanitize_manim_code
    from services.manim_templates import build_guaranteed_manim_code
    from services.manim_validator import format_validation_errors, validate_manim_code

    timed = bool(audio_duration and audio_duration > 0)
    max_static = _env_float("MANIM_MAX_STATIC_RATIO", 0.3)
    pacing_retries = int(_env_float("MANIM_PACING_RETRIES", 1))
    max_play_stretch = _env_float("MANIM_MAX_PLAY_STRETCH", 1.8)

    def _marks_path() -> str:
        return os.path.join(output_dir, f"beat_marks_{uuid.uuid4().hex[:8]}.json")

    def _measure(
        src: str,
    ) -> tuple[str, dict[str, Any], Optional[dict[str, Any]], Optional[str]]:
        """
        Fast pass with animations skipped: catches crashes without a full render
        and measures how long each beat animates vs. how long it is narrated.
        Returns (instrumented_code, scales, pacing_report, error).
        """
        instrumented, _ = instrument_beat_marks(src)
        if instrumented == src or not timed:
            return instrumented, {}, None, None
        path = _marks_path()
        _, err = render_video(
            instrumented,
            output_dir=output_dir,
            log=log,
            measure_only=True,
            marks_path=path,
        )
        if err:
            return instrumented, {}, None, err
        stats = read_beat_stats(path)
        if stats["end"] <= 0:
            return instrumented, {}, None, None
        scales, report = compute_beat_scales(
            beat_windows(stats, beat_map or {}, float(audio_duration)),
            max_play_stretch=max_play_stretch,
        )
        log(
            f"  ⏱️ Pacing: {stats['end']:.1f}s of animation for "
            f"{float(audio_duration):.1f}s of narration → "
            f"{round(report['static_ratio'] * 100)}% frozen screen after stretching motion"
        )
        return instrumented, scales, report, None

    def _beat_lock(video_path: str, marks_path: str) -> str:
        if not timed:
            return video_path
        try:
            vd = get_media_duration(video_path)
        except Exception:
            return video_path
        return retime_to_beats(
            video_path,
            video_marks=read_beat_marks(marks_path),
            video_duration=vd,
            beat_map=beat_map or {},
            audio_duration=float(audio_duration),
            log=log,
        )

    def _render_final(
        instrumented: str, scales: dict[str, Any]
    ) -> tuple[Optional[str], Optional[str]]:
        path = _marks_path()
        video, err = render_video(
            instrumented,
            output_dir=output_dir,
            log=log,
            quality=manim_quality,
            marks_path=path,
            scales=scales or None,
        )
        if not video:
            return None, err
        return _beat_lock(video, path), None

    last_error = None
    previous_code = None
    force_safe_tmt = False
    pacing_retry = False
    best: Optional[dict[str, Any]] = None
    plan_text = format_beat_sheet_for_prompt(visual_plan)
    for attempt in range(1, max_attempts + 1):
        attempt_complexity = complexity
        attempt_plan: dict[str, Any] | str = visual_plan
        # After a crash, go simpler — but keep every beat and its timing so the
        # picture still follows the narration.
        if attempt >= 2 and not pacing_retry:
            attempt_complexity = "simple"
            attempt_plan = (
                "Keep it simple and crash-proof, but keep EVERY beat, its # BEAT N "
                "comment, and its timing:\n"
                "- Only Text, MathTex, Axes + plot, Dot, Arrow, Line, Rectangle, "
                "SurroundingRectangle\n"
                "- Only FadeIn, FadeOut, Write, Create, ReplacementTransform, Indicate\n"
                "- 2–3 reveals per beat, placed on the SPOKEN CUES\n"
                "- NO get_part_by_tex, NO TransformMatchingTex, NO wait(0), NO run_time=0\n\n"
                f"{plan_text[:5000]}"
            )
        pacing_retry = False
        attempt_model = get_model_for_manim_attempt(attempt, model)
        log(
            f"\n🧠 Manim attempt {attempt}/{max_attempts} "
            f"(complexity={attempt_complexity}, model={attempt_model})"
        )
        try:
            code = generate_manim_code(
                topic=topic,
                model=attempt_model,
                visual_plan=attempt_plan,
                duration=duration,
                complexity=attempt_complexity,
                error=last_error,
                previous_code=previous_code,
                log=log,
                force_safe_tmt=force_safe_tmt,
                tier=tier,
            )
        except Exception as e:
            last_error = str(e)
            log(f"  ❌ Code generation failed: {last_error}")
            continue

        # Re-sanitize with nuclear TMT fix if a prior crash demanded it
        if force_safe_tmt:
            code, fixes = sanitize_manim_code(code, force_safe_tmt=True)
            if fixes:
                log(f"  🔧 Re-sanitize: {', '.join(fixes)}")

        issues = validate_manim_code(code)
        errors = [i for i in issues if i.severity == "error"]
        for w in issues:
            if w.severity == "warning":
                log(f"  ⚠️ {w.message}")
        if errors:
            # Auto-fix remaining TMT issues, then re-validate once
            if any("TransformMatchingTex" in (e.message or "") for e in errors):
                code, fixes = sanitize_manim_code(code, force_safe_tmt=True)
                force_safe_tmt = True
                if fixes:
                    log(f"  🔧 Validator auto-fix: {', '.join(fixes)}")
                issues = validate_manim_code(code)
                errors = [i for i in issues if i.severity == "error"]
            if errors:
                last_error = (
                    "ValidationError\n"
                    + format_validation_errors(errors)
                    + "\n"
                    + MANIM_ERROR_HINTS
                )
                previous_code = code
                log("  ❌ Validation errors — skipping render, regenerating...")
                for e in errors[:5]:
                    log(f"     • {e.message}")
                continue

        previous_code = code
        instrumented, scales, report, err = _measure(code)
        if err:
            info = parse_manim_error(err)
            if info.get("force_safe_tmt"):
                force_safe_tmt = True
                # Deterministic repair + re-measure without another LLM call
                repaired, fixes = sanitize_manim_code(code, force_safe_tmt=True)
                if fixes:
                    log(f"  🔧 Crash repair: {', '.join(fixes)}")
                if repaired != code:
                    code = previous_code = repaired
                    instrumented, scales, report, err = _measure(repaired)
        video = None
        if not err:
            ratio = float(report["static_ratio"]) if report else 0.0
            if best is None or ratio < best["ratio"]:
                best = {
                    "code": code,
                    "instrumented": instrumented,
                    "scales": scales,
                    "ratio": ratio,
                    "attempt": attempt,
                }
            if (
                report
                and ratio > max_static
                and pacing_retries > 0
                and attempt < max_attempts
            ):
                pacing_retries -= 1
                pacing_retry = True
                last_error = format_pacing_feedback(report, visual_plan)
                log(
                    f"  🐢 Picture would be static {round(ratio * 100)}% of the time — "
                    f"regenerating with more on-screen action"
                )
                continue
            chosen = best
            if chosen["code"] is not code:
                log(
                    f"  ↩️ Keeping attempt {chosen['attempt']} "
                    f"({round(chosen['ratio'] * 100)}% static) — it moves more"
                )
            video, err = _render_final(chosen["instrumented"], chosen["scales"])
            if video:
                save_successful_example(topic, chosen["code"], attempt=chosen["attempt"])
                return video, None
            best = None

        info = parse_manim_error(err or "")
        if info.get("force_safe_tmt"):
            force_safe_tmt = True
        last_error = build_retry_prompt(
            attempt=attempt,
            max_attempts=max_attempts,
            broken_code=previous_code or code,
            stderr=err or "",
            topic=topic,
        )
        log(f"🔁 Manim render failed ({info.get('type')}): {info.get('message')}")
        if info.get("fix_hint"):
            log(f"   💡 {info['fix_hint'][:200]}")

    if best is not None:
        log("\n🎞️ Rendering the best working attempt")
        video, err = _render_final(best["instrumented"], best["scales"])
        if video:
            save_successful_example(topic, best["code"], attempt=best["attempt"])
            return video, None

    log("\n🛟 All Manim attempts failed — rendering guaranteed fallback template")
    fallback_code = build_guaranteed_manim_code(topic, visual_plan)
    instrumented, scales, _, err = _measure(fallback_code)
    video, err = (None, err) if err else _render_final(instrumented, scales)
    if video:
        return video, None
    log(f"  ❌ Fallback template failed: {(err or '')[:300]}")
    return None, last_error or "Manim failed after all attempts"


async def _run_remotion_pipeline(
    topic: str,
    model: str,
    visual_plan: dict[str, Any],
    duration: int,
    complexity: str,
    job_id: str,
    output_dir: str,
    max_attempts: int = 3,
) -> tuple[Optional[str], Optional[str]]:
    from services.example_store import save_successful_example
    from services.llm import judge_generated_code, quality_judge_enabled
    from services.manim_attempt_models import get_model_for_remotion_attempt
    from services.remotion_error_parser import (
        build_remotion_retry_prompt,
        parse_remotion_error,
    )
    from services.remotion_templates import build_guaranteed_remotion_code
    from services.remotion_validator import (
        typecheck_remotion_code,
        validate_remotion_code,
    )

    last_error = None
    previous_code = None
    plan_text = format_beat_sheet_for_prompt(visual_plan)
    for attempt in range(1, max_attempts + 1):
        attempt_complexity = complexity
        attempt_plan: dict[str, Any] | str = visual_plan
        if attempt >= 2:
            attempt_complexity = "simple"
            attempt_plan = (
                "Keep it VERY simple and compile-proof:\n"
                "1) AbsoluteFill dark bg #0B1020\n"
                "2) One title Sequence, then 2–4 Series.Sequence content slides\n"
                "3) Text + simple SVG or bars only — no complex filters\n"
                "4) interpolate with clamp + Easing.out(Easing.cubic)\n"
                "5) No emoji, no external assets\n"
                "Honor BEAT start_s / duration_sec from the sheet.\n"
                f"Original plan intent (simplify heavily):\n{plan_text[:1200]}"
            )
        attempt_model = get_model_for_remotion_attempt(attempt, model)
        log(
            f"\n🧠 Remotion attempt {attempt}/{max_attempts} "
            f"(complexity={attempt_complexity}, model={attempt_model})"
        )
        try:
            code = generate_remotion_code(
                topic=topic,
                model=attempt_model,
                visual_plan=attempt_plan,
                duration=duration,
                complexity=attempt_complexity,
                error=last_error,
                previous_code=previous_code,
                log=log,
            )
        except Exception as e:
            last_error = str(e)
            log(f"  ❌ Code generation failed: {last_error}")
            continue

        if quality_judge_enabled() and attempt == 1:
            judgment = judge_generated_code(
                topic=topic,
                engine="remotion",
                code=code,
                visual_plan=visual_plan,
                log=log,
            )
            verdict = str(judgment.get("verdict", "approve")).lower()
            score = int(judgment.get("score") or 0)
            if verdict == "regenerate" or score < 50:
                last_error = "Quality judge rejected code: " + "; ".join(
                    str(i.get("description", ""))
                    for i in (judgment.get("issues") or [])[:3]
                )
                previous_code = code
                log("  ⚠️ Judge requested regenerate — retrying...")
                continue

        previous_code = code
        problems = validate_remotion_code(code) or typecheck_remotion_code(code)
        if problems:
            for p in problems[:5]:
                log(f"     • {p}")
            log("  ❌ Remotion pre-check failed — skipping render, regenerating...")
            last_error = build_remotion_retry_prompt(
                attempt=attempt,
                max_attempts=max_attempts,
                broken_code=code,
                stderr="Pre-render check failed:\n" + "\n".join(problems),
                topic=topic,
            )
            continue

        video, err = render_remotion(
            tsx_code=code,
            job_id=f"{job_id}_{attempt}",
            duration=duration,
            output_dir=output_dir,
            log=log,
        )
        if video:
            save_successful_example(topic, code, attempt=attempt, engine="remotion")
            return video, None
        info = parse_remotion_error(err or "")
        last_error = build_remotion_retry_prompt(
            attempt=attempt,
            max_attempts=max_attempts,
            broken_code=code,
            stderr=err or "",
            topic=topic,
        )
        log(f"🔁 Remotion render failed ({info.get('type')}): {info.get('message')}")
        if info.get("fix_hint"):
            log(f"   💡 {info['fix_hint'][:200]}")

    log("\n🛟 All Remotion attempts failed — rendering guaranteed fallback template")
    video, err = render_remotion(
        tsx_code=build_guaranteed_remotion_code(topic, visual_plan),
        job_id=f"{job_id}_fallback",
        duration=duration,
        output_dir=output_dir,
        log=log,
    )
    if video:
        return video, None
    log(f"  ❌ Fallback template failed: {(err or '')[:300]}")
    return None, last_error or "Remotion failed after all attempts"


def _upload_and_maybe_cleanup(
    local_path: str,
    object_key: str,
    work_dir: str,
    user_id: Optional[str] = None,
    storage_override: Optional[UserStorageConfig] = None,
    use_platform_storage: bool = False,
) -> str:
    """Upload to R2/S3, then wipe the job work dir on VPS."""
    if not local_path or not os.path.isfile(local_path):
        raise FileNotFoundError(f"Nothing to upload: {local_path}")
    try:
        url = upload_to_r2(
            local_path,
            object_key=object_key,
            log=log,
            user_id=user_id,
            storage_override=storage_override,
            use_platform_storage=use_platform_storage,
        )
    except Exception as e:
        # Still free disk on VPS even if upload fails
        cleanup_job_dir(work_dir, log=log)
        raise RuntimeError(f"Storage upload failed: {e}") from e

    cleanup_job_dir(work_dir, log=log)
    if keep_local_outputs():
        log(f"  💾 Keeping local outputs ({storage_policy()['clarity_env']})")
    else:
        log("  🧹 Local job files removed after upload (VPS mode)")
    return url


async def process_topic_async(
    topic: str,
    model: str = DEFAULT_MODEL,
    engine: str = "auto",
    duration: Optional[int] = None,
    job_id: Optional[str] = None,
    user_id: Optional[str] = None,
    storage_override: Optional[UserStorageConfig] = None,
    use_platform_storage: bool = False,
    max_attempts: int = 3,
    status_cb=None,
    watermark: bool = False,
    max_height: int = 1080,
    tier: Optional[str] = None,
) -> dict:
    """
    Full Clarity video pipeline.
    Always returns a dict:
      success → {ok: True, video_url, engine, duration, ...}
      failure → {ok: False, error: "...", engine?: ...}
    """
    from services.quality_tiers import get_tier_config, normalize_tier, status_payload

    job_id = job_id or uuid.uuid4().hex
    work_dir = job_work_dir(job_id)
    policy = storage_policy()
    tier_name = normalize_tier(tier)
    tier_cfg = get_tier_config(tier_name)
    log(
        f"Storage policy: env={policy['clarity_env']}, "
        f"keep_local={policy['keep_local_outputs']}, work_dir={work_dir}, "
        f"tier={tier_name} ({tier_cfg['label']})"
    )

    def set_status(status: str, **extra):
        if status_cb:
            payload = status_payload(status, tier_name)
            payload.update(extra)
            status_cb(status, payload)

    video = None
    chosen_engine = None
    try:
        set_status("routing")
        # Tier-1 templates: force short, simple, reliable path
        preferred_duration = duration
        if preferred_duration is None and tier_name == "tier1":
            preferred_duration = int(tier_cfg["max_duration_sec"])
        elif preferred_duration is not None:
            preferred_duration = min(
                int(preferred_duration), int(tier_cfg["max_duration_sec"])
            )

        route = route_prompt(
            topic, forced_engine=engine, preferred_duration=preferred_duration
        )
        chosen_engine = route["engine"]
        router_duration = route.get("duration")
        if router_duration is None and preferred_duration is not None:
            router_duration = preferred_duration
        complexity = route.get("complexity", "medium")
        if tier_name == "tier1":
            complexity = "simple"
        elif tier_cfg.get("complexity"):
            complexity = str(tier_cfg["complexity"])
        subject = route.get("subject", topic)
        log(
            f"Router chose: {chosen_engine} ({route.get('reason')}), "
            f"duration={'auto' if router_duration is None else f'{router_duration}s'}, "
            f"complexity={complexity}, tier={tier_name}"
        )
        set_status(
            "routing",
            engine=chosen_engine,
            duration=router_duration,
            tier=tier_name,
        )

        # 1) Beat-sheet plan (visual + narration + timing)
        set_status("planning", engine=chosen_engine)
        visual_plan = generate_visual_plan(
            subject,
            chosen_engine,
            duration=router_duration,
            log=log,
        )
        # Cap beats for tier reliability
        max_beats = int(tier_cfg.get("max_beats") or 8)
        beats = visual_plan.get("beats") or []
        if len(beats) > max_beats:
            visual_plan["beats"] = beats[:max_beats]
            log(f"  ✂️ Tier {tier_name}: trimmed to {max_beats} beats")
        plan_duration = int(beat_sheet_target_duration(visual_plan))
        log(
            f"Beat sheet ready: {len(visual_plan.get('beats', []))} beats, ~{plan_duration}s"
        )

        # 2) Narration with [BEAT:N] markers → TTS + word timestamps → beat_map
        #    Audio drives the timeline; video is generated to match (no atempo).
        set_status("generating_audio", engine=chosen_engine)
        narration_script = generate_narration_script(
            topic=subject,
            visual_plan=visual_plan,
            target_duration=float(plan_duration),
            output_dir=work_dir,
            model=NARRATION_MODEL,
            log=log,
        )
        (
            audio_path,
            srt_path,
            audio_duration,
            beat_map,
        ) = await generate_audio_with_captions(
            narration_script,
            output_dir=work_dir,
            log=log,
            visual_plan=visual_plan,
        )
        timed_plan = apply_measured_timings_to_plan(
            visual_plan, beat_map, audio_duration
        )
        code_duration = (
            int(round(audio_duration)) if audio_duration > 0 else plan_duration
        )
        log(
            f"Audio {audio_duration:.1f}s → measured {len(beat_map)} beats → "
            f"code target {code_duration}s (voice tempo untouched)"
        )

        # 3) Generate + render video timed to measured beat timestamps
        set_status("generating_code", engine=chosen_engine)
        attempts = max_attempts or _default_max_attempts()
        manim_quality = str(tier_cfg.get("manim_quality") or "medium")
        if chosen_engine == "remotion":
            video, render_err = await _run_remotion_pipeline(
                topic=subject,
                model=model,
                visual_plan=timed_plan,
                duration=code_duration,
                complexity=complexity,
                job_id=job_id,
                output_dir=work_dir,
                max_attempts=min(3, attempts),
            )
        else:
            video, render_err = await _run_manim_pipeline(
                topic=subject,
                model=model,
                visual_plan=timed_plan,
                duration=code_duration,
                complexity=complexity,
                output_dir=work_dir,
                max_attempts=attempts,
                audio_duration=audio_duration,
                manim_quality=manim_quality,
                tier=tier_name,
                beat_map=beat_map,
            )

        if not (video and os.path.exists(video)):
            err = render_err or "Failed to generate base video"
            log(f"❌ {err}")
            cleanup_job_dir(work_dir, log=log)
            return {"ok": False, "error": err[-4000:], "engine": chosen_engine}

        log(f"✅ Base video: {video}")
        video_duration = get_media_duration(video)
        if audio_duration > 0 and video_duration > 0:
            drift = abs(video_duration - audio_duration)
            if drift > 2.0:
                log(
                    f"  ⚠️ Duration drift {drift:.1f}s "
                    f"(video {video_duration:.1f}s vs audio {audio_duration:.1f}s) — "
                    f"merging without speed change"
                )

        set_status("merging", engine=chosen_engine)
        final_video = merge_video_audio_captions(
            video_path=video,
            audio_path=audio_path,
            srt_path=srt_path,
            video_duration=video_duration,
            audio_duration=audio_duration,
            output_dir=work_dir,
            log=log,
        )

        final_video = _apply_plan_quality(
            final_video,
            work_dir,
            watermark=watermark,
            max_height=max_height,
            log_fn=log,
        )

        set_status("uploading", engine=chosen_engine)
        video_url = _upload_and_maybe_cleanup(
            final_video,
            object_key=_r2_object_key(job_id, "final"),
            work_dir=work_dir,
            user_id=user_id,
            storage_override=storage_override,
            use_platform_storage=use_platform_storage,
        )
        log(f"☁️ Uploaded: {video_url}")
        return {
            "ok": True,
            "video_url": video_url,
            "engine": chosen_engine,
            "duration": audio_duration or video_duration,
            "reason": route.get("reason"),
        }
    except Exception as e:
        log(f"⚠️ Pipeline error: {e}")
        # Best-effort: upload whatever base video exists, then clean disk on VPS
        try:
            if video and os.path.exists(video):
                set_status("uploading", engine=chosen_engine)
                try:
                    silent_duration = get_media_duration(video)
                except Exception:
                    silent_duration = None
                video_url = _upload_and_maybe_cleanup(
                    video,
                    object_key=_r2_object_key(job_id, "silent"),
                    work_dir=work_dir,
                    user_id=user_id,
                    storage_override=storage_override,
                    use_platform_storage=use_platform_storage,
                )
                return {
                    "ok": True,
                    "video_url": video_url,
                    "engine": chosen_engine,
                    "duration": silent_duration,
                    "warning": str(e),
                }
        except Exception as upload_err:
            cleanup_job_dir(work_dir, log=log)
            return {
                "ok": False,
                "error": f"{e} | upload also failed: {upload_err}",
                "engine": chosen_engine,
            }
        cleanup_job_dir(work_dir, log=log)
        return {"ok": False, "error": str(e), "engine": chosen_engine}


def process_topic(
    topic: str,
    model: str = DEFAULT_MODEL,
    engine: str = "auto",
    duration: Optional[int] = None,
    job_id: Optional[str] = None,
    max_attempts: int = 3,
) -> Optional[str]:
    """CLI-friendly wrapper — returns video URL string only."""
    result = asyncio.run(
        process_topic_async(
            topic=topic,
            model=model,
            engine=engine,
            duration=duration,
            job_id=job_id or uuid.uuid4().hex,
            max_attempts=max_attempts,
        )
    )
    if not result or not result.get("ok"):
        return None
    return result.get("video_url")
