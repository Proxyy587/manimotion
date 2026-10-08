import asyncio
import hashlib
import os
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from schema.chat import (
    ChatRequest,
    JobCreateResponse,
    JobStatusResponse,
    VideoRequest,
)
from services.api_key_auth import is_user_api_key, validate_user_api_key
from services.quota import (
    check_and_consume_api_key_daily,
    plan_max_height,
    plan_wants_watermark,
)
from services.llm import DEFAULT_MODEL
from services.public_api import engine_for_style, public_error, public_style
from services.quality_tiers import estimate_job, status_payload
from services.storage_resolver import ResolvedStorage, resolve_job_storage
from services.user_storage import UserStorageConfig
from worker import process_topic_async

load_dotenv()

_is_prod = os.getenv("CLARITY_ENV", "").lower() in {"vps", "prod", "production"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        from services.latex_warmup import warmup_latex

        await asyncio.to_thread(warmup_latex)
    except Exception as exc:
        print(f"  ⚠️ Startup warmup skipped: {exc}", flush=True)
    yield


app = FastAPI(
    title="manimotion Video API",
    version="1.0.0",
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
    lifespan=lifespan,
)

_allowed = os.getenv("ALLOWED_ORIGINS", "*")
_origins = [o.strip() for o in _allowed.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: dict[str, dict] = {}
CACHE: dict[str, dict] = {}
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", str(6 * 60 * 60)))
RATE_LIMIT_COUNT = int(os.getenv("RATE_LIMIT_COUNT", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", str(10 * 60)))
REQUEST_LOG: dict[str, deque] = defaultdict(deque)
API_KEY = os.getenv("CLARITY_API_KEY", "").strip()


def _extract_api_key(request: Request) -> str:
    return (
        request.headers.get("x-api-key")
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )


def _require_api_key(request: Request) -> dict | None:
    """
    Authenticate request.

    Returns:
      - {"type": "user", user_id, api_key_id, plan} for chalk_* keys
      - {"type": "master"} when key equals CLARITY_API_KEY (owner / platform storage)
      - None only when CLARITY_API_KEY is unset (dev open mode — treated as master for storage)
    """
    provided = _extract_api_key(request)
    client_ip = request.client.host if request.client else None

    if provided and is_user_api_key(provided):
        ctx = validate_user_api_key(provided, client_ip=client_ip)
        if not ctx:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key.")
        auth = {
            "type": "user",
            "user_id": ctx.user_id,
            "api_key_id": ctx.api_key_id,
            "plan": ctx.plan,
        }
        request.state.auth = auth
        return auth

    # Owner master key → platform .env R2
    if API_KEY:
        if provided != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key.")
        auth = {"type": "master"}
        request.state.auth = auth
        return auth

    # Dev mode: no CLARITY_API_KEY configured — allow and use platform storage
    return {"type": "master"}


def _is_master_auth(auth: dict | None) -> bool:
    return not auth or auth.get("type") == "master"


def _resolve_storage_or_400(
    storage_req,
    auth: dict | None,
) -> ResolvedStorage:
    user_id = auth.get("user_id") if auth else None
    try:
        return resolve_job_storage(
            storage_req,
            user_id,
            is_master=_is_master_auth(auth),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _extract_topic(messages) -> str:
    user_msgs = [m.content for m in messages if m.role.lower() == "user" and m.content.strip()]
    if not user_msgs:
        raise HTTPException(status_code=400, detail="At least one user message is required.")
    return user_msgs[-1].strip()


def _cache_key(topic: str, model: str, engine: str, duration: int | None) -> str:
    raw = f"{topic}::{model}::{engine}::{duration if duration is not None else 'auto'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _rate_limit_or_raise(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    q = REQUEST_LOG[client_ip]
    while q and now - q[0] > RATE_LIMIT_WINDOW_SECONDS:
        q.popleft()
    if len(q) >= RATE_LIMIT_COUNT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please retry later.")
    q.append(now)


def _run_job(
    job_id: str,
    topic: str,
    model: str,
    engine: str,
    duration: int | None,
    user_id: str | None = None,
    job_storage: UserStorageConfig | None = None,
    use_platform_storage: bool = False,
    watermark: bool = False,
    max_height: int = 1080,
    tier: str | None = None,
):
    def status_cb(status: str, extra: dict):
        JOBS[job_id]["status"] = status
        if extra:
            JOBS[job_id].update(extra)

    try:
        JOBS[job_id]["status"] = "processing"
        JOBS[job_id].update(status_payload("processing", tier))
        result = asyncio.run(
            process_topic_async(
                topic=topic,
                model=model,
                engine=engine,
                duration=duration,
                job_id=job_id,
                user_id=user_id,
                storage_override=job_storage,
                use_platform_storage=use_platform_storage,
                status_cb=status_cb,
                watermark=watermark,
                max_height=max_height,
                tier=tier,
            )
        )
        if not result or not result.get("ok") or not result.get("video_url"):
            _fail_job(job_id, (result or {}).get("error"))
            return

        JOBS[job_id].update(status_payload("completed", tier))
        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["video_url"] = result["video_url"]
        JOBS[job_id]["engine"] = result.get("engine")
        JOBS[job_id]["duration"] = result.get("duration")
        JOBS[job_id]["error"] = None
        if result.get("warning"):
            JOBS[job_id]["warning"] = result["warning"]
        key = _cache_key(topic, model, engine, duration)
        CACHE[key] = {
            "video_url": result["video_url"],
            "engine": result.get("engine"),
            "duration": result.get("duration"),
            "created_at": time.time(),
        }
    except Exception as exc:
        _fail_job(job_id, str(exc))


def _fail_job(job_id: str, detail: str | None) -> None:
    """Keep the full failure in logs; API callers get a short, actionable message."""
    print(f"  ❌ Job {job_id} failed: {detail or 'unknown error'}", flush=True)
    JOBS[job_id]["status"] = "failed"
    JOBS[job_id].update(status_payload("failed", JOBS[job_id].get("tier")))
    JOBS[job_id]["error"] = public_error(detail)


def _enqueue(
    topic: str,
    model: str,
    engine: str,
    duration: int | None,
    user_id: str | None = None,
    resolved: ResolvedStorage | None = None,
    auth: dict | None = None,
    watermark_override: bool | None = None,
    max_height_override: int | None = None,
    tier: str | None = None,
) -> JobCreateResponse:
    model = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    resolved = resolved or ResolvedStorage("platform", None)
    job_storage = resolved.config
    use_platform_storage = resolved.use_platform
    est = estimate_job(tier)

    plan = str(auth.get("plan") or "FREE") if auth and auth.get("type") == "user" else "PRO"
    if auth and auth.get("type") == "user":
        watermark = plan_wants_watermark(plan)
        max_height = plan_max_height(plan)
    elif _is_master_auth(auth):
        # Trusted Next proxy may pin free-tier quality for session/guest demos.
        watermark = bool(watermark_override) if watermark_override is not None else False
        max_height = int(max_height_override) if max_height_override else 1080
    else:
        watermark = False
        max_height = 1080

    api_key_id = auth.get("api_key_id") if auth else None

    key = _cache_key(topic, model, engine, duration)
    hit = CACHE.get(key)
    if hit and time.time() - hit["created_at"] <= CACHE_TTL_SECONDS:
        job_id = str(uuid.uuid4())
        JOBS[job_id] = {
            "status": "completed",
            "video_url": hit["video_url"],
            "engine": hit.get("engine"),
            "duration": hit.get("duration"),
            "error": None,
            "cached": True,
            "created_at": time.time(),
            "user_id": user_id,
            "api_key_id": api_key_id,
            "auth_type": (auth or {}).get("type", "master"),
            "message": "Done!",
            "eta_seconds": 0,
            "eta_display": est["eta_display"],
            "tier": est["tier"],
        }
        return JobCreateResponse(
            job_id=job_id,
            status="completed",
            cached=True,
            video_url=hit["video_url"],
            style=public_style(hit.get("engine")),
            eta_seconds=0,
            eta_display=est["eta_display"],
            message="Done!",
            tier=est["tier"],
        )

    job_id = str(uuid.uuid4())
    queued_meta = status_payload("queued", tier)
    JOBS[job_id] = {
        "status": "queued",
        "video_url": None,
        "error": None,
        "cached": False,
        "created_at": time.time(),
        "topic": topic,
        "model": model,
        "engine": engine,
        "duration": duration,
        "user_id": user_id,
        "api_key_id": api_key_id,
        "auth_type": (auth or {}).get("type", "master"),
        **queued_meta,
    }
    asyncio.create_task(
        asyncio.to_thread(
            _run_job,
            job_id,
            topic,
            model,
            engine,
            duration,
            user_id,
            job_storage,
            use_platform_storage,
            watermark,
            max_height,
            tier,
        )
    )
    return JobCreateResponse(
        job_id=job_id,
        status="queued",
        cached=False,
        video_url=None,
        style=None,
        eta_seconds=est["eta_seconds"],
        eta_display=est["eta_display"],
        message=queued_meta["message"],
        tier=est["tier"],
    )


def _authorize_job_access(job: dict, auth: dict | None):
    """Master may read any job; user keys only their own."""
    if _is_master_auth(auth):
        return
    if not auth or auth.get("type") != "user":
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    job_key = job.get("api_key_id")
    job_user = job.get("user_id")
    if job_key and job_key == auth.get("api_key_id"):
        return
    if job_user and job_user == auth.get("user_id"):
        return
    # Legacy jobs without ownership metadata — deny for user keys
    if job_key is None and job_user is None and job.get("auth_type") is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    raise HTTPException(status_code=404, detail="Job not found.")


def _enforce_user_key_quota(auth: dict | None):
    """FREE: 3/day. Hobby(STUDENT): 40/mo. Pro: 80/mo. Owner: unlimited."""
    if not auth or auth.get("type") != "user":
        return
    ok, err = check_and_consume_api_key_daily(
        str(auth["api_key_id"]),
        str(auth.get("plan") or "FREE"),
    )
    if not ok:
        raise HTTPException(status_code=429, detail=err)


@app.get("/")
async def root():
    return {
        "service": "manimotion Video API",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "POST /video/request": "Create a video job (recommended)",
            "GET /video/status/{job_id}": "Poll job status",
            "POST /generate-lecture": "Legacy chalkboard endpoint",
            "GET /jobs/{job_id}": "Legacy job status",
        },
    }


@app.get("/health")
async def health():
    """Public liveness — no config / credential leakage."""
    from services.storage import r2_config_status

    r2 = r2_config_status()
    return {
        "status": "ok",
        "service": "manimotion",
        "storage_ready": bool(r2.get("ready")),
    }


@app.post("/video/request", response_model=JobCreateResponse)
async def request_video(req: VideoRequest, http_request: Request):
    auth = _require_api_key(http_request)
    _rate_limit_or_raise(http_request)
    _enforce_user_key_quota(auth)
    user_id = auth.get("user_id") if auth else None
    resolved = _resolve_storage_or_400(req.storage, auth)
    return _enqueue(
        topic=req.prompt.strip(),
        model=req.model or DEFAULT_MODEL,
        engine=engine_for_style(req.style, req.engine),
        duration=req.duration,
        user_id=user_id,
        resolved=resolved,
        auth=auth,
        watermark_override=req.watermark,
        max_height_override=req.max_height,
        tier=req.tier,
    )


@app.get("/video/status/{job_id}", response_model=JobStatusResponse)
async def video_status(job_id: str, http_request: Request):
    auth = _require_api_key(http_request)
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    _authorize_job_access(job, auth)
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        video_url=job.get("video_url"),
        error=job.get("error"),
        cached=job.get("cached", False),
        style=public_style(job.get("engine")),
        duration=job.get("duration"),
        phase=job.get("phase"),
        message=job.get("message"),
        eta_seconds=job.get("eta_seconds"),
        eta_display=job.get("eta_display"),
        tier=job.get("tier"),
    )


@app.post("/generate-lecture", response_model=JobCreateResponse)
async def generate_chalks(request: ChatRequest, http_request: Request):
    """Backward-compatible chalkboard endpoint (platform storage for master key)."""
    auth = _require_api_key(http_request)
    _rate_limit_or_raise(http_request)
    _enforce_user_key_quota(auth)
    topic = _extract_topic(request.messages)
    user_id = auth.get("user_id") if auth else None
    # Chalkboard demo: same storage rules (master → .env, else require saved/inline)
    resolved = _resolve_storage_or_400(None, auth)
    return _enqueue(
        topic=topic,
        model=request.model or DEFAULT_MODEL,
        engine=engine_for_style(request.style, request.engine),
        duration=request.duration,
        user_id=user_id,
        resolved=resolved,
        auth=auth,
    )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, http_request: Request):
    return await video_status(job_id, http_request)
