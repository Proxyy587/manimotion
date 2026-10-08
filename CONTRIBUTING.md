# Contributing

## Before you start

- Open or claim an issue before large changes.
- One problem per PR. Small diffs get merged faster.
- Never commit `.env` or real API keys.

## Repo layout

```
manim-vid/
  client/          # Next.js — UI, docs, settings, Better Auth, Prisma
  main.py          # FastAPI video worker (VPS)
  worker.py        # generation pipeline
  prompts/         # live LLM prompts
  remotion-src/    # Remotion compositions
  schema/          # Pydantic models (VideoRequest, etc.)
  services/        # TTS, timing, rendering, storage
  tests/           # pytest
```

Web and worker are separate deploys. Vercel Root Directory = `client`. Python
runs on a box that can render.

## Web app (`client/`)

```bash
cd client
bun install
cp .env.example .env
bunx prisma generate && bunx prisma db push
bun run dev
```

## Video worker

```bash
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000
# client/.env → NEXT_PUBLIC_CHALKBOARD_API_URL=http://127.0.0.1:8000
uv run --with pytest python -m pytest -q tests
```

Quality changes usually live in `prompts/`. Rendering engines are an internal
detail — user-facing copy, docs and API responses talk about *styles*
(`math`, `graphics`), never engine names.

## Pull requests

- Say what broke and how you tested (UI path or curl).
- Match existing style — no drive-by renames.
- Prisma changes → run `db push` and mention it in the PR.
