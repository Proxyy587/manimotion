# Clarity API
Generate videos from a text prompt.

- **Manim** for math / physics / LaTeX
- **Remotion** for charts / timelines / modern explainers
- Auto engine routing
- Cloudflare R2 upload
- FastAPI job + polling API for any frontend

## Quick start (local API)

```bash
uv sync
uv run uvicorn main:app --reload --port 8000
```

Open docs: http://127.0.0.1:8000/docs

## Docker

```bash
docker compose up --build
```

## Repo layout

```
client/          # Next.js — UI, docs, settings, Better Auth, Prisma (Vercel root)
main.py          # FastAPI video API (VPS)
worker.py        # generation pipeline
services/        # planning, narration, rendering, sync, storage
prompts/         # live LLM prompts — most quality changes land here
remotion-src/    # Remotion project used for the "graphics" style
schema/          # Pydantic request/response models
tests/           # uv run --with pytest python -m pytest -q tests
```

The public API never names the engines: callers pick a `style`
(`auto` | `math` | `graphics`), which maps to Manim / Remotion internally
(`services/public_api.py`).

## Full cloud + Next.js integration guide

See **[DEPLOY.md](./DEPLOY.md)** — beginner-friendly end-to-end instructions.
