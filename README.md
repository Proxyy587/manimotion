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

## Full cloud + Next.js integration guide

See **[DEPLOY.md](./DEPLOY.md)** — beginner-friendly end-to-end instructions.
