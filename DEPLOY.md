# Clarity API — Deploy & Integrate Guide

> **Going public with the full product (Vercel web + this worker)?**  
> Start with **[`client/DEPLOY.md`](./client/DEPLOY.md)** — secrets, Neon, encryption, smoke tests.

This file focuses on the **Python video worker** (Docker / VPS).

- **Manim** → math / physics / LaTeX / geometric animation
- **Remotion** → charts / timelines / modern UI-style explainers

It auto-routes the prompt, renders video, adds TTS narration, uploads to Cloudflare R2, and returns a public URL.

---

## 1. What you get (API)

| Method | Path                     | Purpose                               |
| ------ | ------------------------ | ------------------------------------- |
| `GET`  | `/health`                | Health check                          |
| `POST` | `/video/request`         | Create a video job (recommended)      |
| `GET`  | `/video/status/{job_id}` | Poll until complete                   |
| `POST` | `/generate-lecture`      | Legacy chalkboard-compatible endpoint |
| `GET`  | `/jobs/{job_id}`         | Legacy status poll                    |
| `GET`  | `/docs`                  | Interactive Swagger UI                |

### Create job

```bash
curl -X POST https://YOUR_DOMAIN/video/request \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_CLARITY_API_KEY" \
  -d '{
    "prompt": "Explain the product rule with a visual derivation",
    "model": "deepseek/deepseek-v3.2",
    "engine": "auto",
    "duration": 60
  }'
```

Response:

```json
{
  "job_id": "uuid...",
  "status": "queued",
  "cached": false,
  "video_url": null,
  "engine": null
}
```

### Poll status

```bash
curl https://YOUR_DOMAIN/video/status/JOB_ID
```

When done:

```json
{
  "job_id": "...",
  "status": "completed",
  "video_url": "https://pub-xxxx.r2.dev/videos/....mp4",
  "engine": "manim",
  "duration": 52.0,
  "cached": false
}
```

`engine` can be forced: `"manim"` | `"remotion"` | `"auto"`.

`model` defaults to `google/gemini-2.5-flash` if omitted.

---

## 2. Environment variables

Create a `.env` file (never commit secrets):

```env
# LLM
OPENROUTER_API_KEY=sk-or-...
DEFAULT_MODEL=google/gemini-2.5-flash
ROUTER_MODEL=openai/gpt-4o-mini
PLANNER_MODEL=openai/gpt-4o-mini

# Slide lecture pipeline (recommended): lesson plan → one narrated sentence per beat →
# one slide per idea, paced like a teacher. Video length follows the content (no caps).
PIPELINE_V2=1
# Model used for the last code attempt on a slide before the plain fallback slide
SLIDE_STRONG_MODEL=anthropic/claude-sonnet-4.5
# 720 (default, 720p30) or 1080 (1080p30)
SLIDE_RESOLUTION=720
SLIDE_RENDER_TIMEOUT=480
# Slides rendered in parallel (each render uses ~1 CPU core)
SLIDE_RENDER_WORKERS=2
TTS_VOICE=en-US-AriaNeural
TTS_RATE=-8%
SLIDE_FONT=DejaVu Sans
# Burn captions into the strip under the slide (a captions.vtt is always produced)
CAPTIONS_BURN=1

# Manim reliability (optional, used when PIPELINE_V2 is off)
MANIM_MAX_ATTEMPTS=3
# Rotate models per retry (attempt:model, comma-separated; last entry covers later attempts)
MANIM_ATTEMPT_MODELS=1:google/gemini-2.5-flash,2:google/gemini-2.5-flash,3:openai/gpt-4o
# Save first-try successes to data/manim_success_examples.jsonl and reuse them as few-shot examples
MANIM_SAVE_EXAMPLES=1
# MANIM_EXAMPLES_PATH=/data/manim_success_examples.jsonl
# Kill a hung render after N seconds (counts as a failed attempt → retry)
MANIM_RENDER_TIMEOUT=600

# Beat-locked sync: each "# BEAT N" in the Manim code is stretched/held to start
# exactly when its narration starts. Limits keep motion natural.
BEAT_SYNC_MAX_SLOWDOWN=1.3
BEAT_SYNC_MAX_SPEEDUP=1.6
# Pacing: a fast measure pass times every beat before the real render.
# Animations in short beats are slowed up to this factor so motion fills the narration.
MANIM_MAX_PLAY_STRETCH=1.8
# If more than this share of narration would be frozen screen (holds > 2.5s),
# regenerate the code once with per-beat feedback.
MANIM_MAX_STATIC_RATIO=0.3
MANIM_PACING_RETRIES=1
# Low temperature for code generation (fewer invented APIs)
CODE_TEMPERATURE=0.3

# Remotion reliability (optional, same format as the Manim settings)
REMOTION_ATTEMPT_MODELS=1:google/gemini-2.5-flash,2:google/gemini-2.5-flash,3:openai/gpt-4o
REMOTION_SAVE_EXAMPLES=1
# REMOTION_EXAMPLES_PATH=/data/remotion_success_examples.jsonl

# Cloudflare R2 (S3-compatible)
R2_ACCOUNT_ID=your_account_id
R2_BUCKET_NAME=manim-video
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
AWS_ENDPOINT_URL_S3=https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
R2_PUBLIC_BASE_URL=https://pub-xxxx.r2.dev

# API security / CORS
CLARITY_API_KEY=make-a-long-random-string
ALLOWED_ORIGINS=*

# Shared with Next.js (encrypted user storage + chalk_* keys)
DATABASE_URL=postgresql://...
SECRET_ENCRYPTION_KEY=at-least-32-chars-same-as-vercel

# Storage policy
# local  → keep files under ./outputs (dev)
# vps    → render under /tmp/clarity-jobs, upload to R2, then delete
CLARITY_ENV=vps
KEEP_LOCAL_OUTPUTS=false
# Optional override for work directory:
# CLARITY_WORK_DIR=/tmp/clarity-jobs

# Optional tuning
CACHE_TTL_SECONDS=21600
RATE_LIMIT_COUNT=20
RATE_LIMIT_WINDOW_SECONDS=600
MANIM_QUALITY=medium
# low | medium | high | 4k — medium = 720p30, high = 1080p60
```

### Where to get each value

1. **OpenRouter key** → https://openrouter.ai/keys
2. **R2 bucket + tokens** → Cloudflare Dashboard → R2 → Create bucket → Manage R2 API Tokens
3. **Public base URL** → Enable public access / R2.dev subdomain or custom domain on the bucket
4. **CLARITY_API_KEY** → any long random secret you invent for your frontend/backend
5. **CLARITY_ENV** → `local` on your laptop, `vps` on the Azure/cloud box (deletes local videos after R2 upload)

---

## 3. Docker from scratch (local)

### A. Install Docker Desktop

- Install Docker Desktop for Mac/Windows/Linux
- Open it and wait until it says **Engine running**

### B. Verify

```bash
docker version
docker info
```

### C. Build

From the project root (`manim-vid/`):

```bash
docker build -t clarity-video .
```

First build takes **10–20 minutes** (TeX + Node + Chromium).

### D. Run

```bash
docker run --rm -p 8000:8000 --env-file .env clarity-video
```

Or with Compose:

```bash
docker compose up --build
```

### E. Test

```bash
curl http://localhost:8000/health
open http://localhost:8000/docs
```

---

## 4. Host online (VPS beginner path)

### A. Get a VPS

Any Ubuntu 22.04+ VPS works (DigitalOcean, Hetzner, Linode, AWS Lightsail).

Recommended: **4GB RAM / 2 vCPU** minimum (Manim + Remotion are heavy).

### B. SSH in

```bash
ssh root@YOUR_VPS_IP
```

### C. Install Docker on the VPS

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# log out / log in after this
```

### D. Clone & configure

```bash
git clone https://github.com/YOUR_USER/manim-vid.git
cd manim-vid
nano .env   # paste your env vars
```

### E. Build & run

```bash
docker compose up -d --build
docker logs -f clarity-video
```

### F. Point a domain (Nginx + HTTPS)

```bash
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/clarity-video`:

```nginx
server {
    listen 80;
    server_name video.yourdomain.com;

    client_max_body_size 20m;
    proxy_read_timeout 600s;
    proxy_connect_timeout 600s;
    proxy_send_timeout 600s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/clarity-video /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d video.yourdomain.com
```

Your public API base becomes:
`https://video.yourdomain.com`

### G. Redeploy after code changes

```bash
cd ~/manim-vid
git pull
docker compose up -d --build
```

---

## 5. Host on Railway / Render (managed)

### Railway

1. Push repo to GitHub
2. New Project → Deploy from GitHub
3. Select Dockerfile
4. Add all `.env` variables in Railway Variables
5. Expose port `8000`
6. Copy the public URL

### Render

1. New Web Service → connect GitHub
2. Environment: Docker
3. Add env vars
4. Deploy

> Note: free tiers may kill long jobs. Prefer a paid plan or VPS for Manim/Remotion.

---

## 6. Integrate into ANY Next.js / React app

This service is a pure HTTP API. Your Next.js app only needs:

1. Base URL of the API
2. Optional API key
3. Polling loop

### Env in your Next.js app

```env
NEXT_PUBLIC_CLARITY_API_URL=https://video.yourdomain.com
CLARITY_API_KEY=make-a-long-random-string
```

> Prefer calling the video API from a **Next.js Route Handler** (server side) so the API key is not exposed to the browser.

### Example: `app/api/video/route.ts` (server)

```ts
import { NextRequest, NextResponse } from "next/server";

const BASE = process.env.NEXT_PUBLIC_CLARITY_API_URL!;
const KEY = process.env.CLARITY_API_KEY!;

export async function POST(req: NextRequest) {
  const body = await req.json();
  const res = await fetch(`${BASE}/video/request`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": KEY,
    },
    body: JSON.stringify({
      prompt: body.prompt,
      model: body.model || "deepseek/deepseek-v3.2",
      engine: body.engine || "auto",
      duration: body.duration || 60,
    }),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
```

### Example: client poller

```ts
async function generateVideo(prompt: string) {
  const create = await fetch("/api/video", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  }).then((r) => r.json());

  if (create.video_url) return create.video_url; // cache hit

  const jobId = create.job_id;
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 3000));
    const status = await fetch(
      `${process.env.NEXT_PUBLIC_CLARITY_API_URL}/video/status/${jobId}`,
    ).then((r) => r.json());

    if (status.status === "completed") return status.video_url;
    if (status.status === "failed") throw new Error(status.error || "failed");
  }
  throw new Error("Timed out waiting for video");
}
```

### Chat UX pattern (`@video ...`)

In your chat app:

1. Detect message starts with `@video `
2. Strip prefix → send remaining text as `prompt`
3. Show “Generating video…” with status badges: `queued → planning → rendering → merging → uploading → completed`
4. Render `<video src={video_url} controls />` when ready

---

## 7. Engine routing (how Manim vs Remotion is chosen)

Router LLM (`ROUTER_MODEL`) returns JSON:

```json
{
  "engine": "manim",
  "reason": "...",
  "complexity": "medium",
  "duration": 60,
  "subject": "cleaned topic"
}
```

- Math / calculus / vectors / LaTeX → **manim**
- Charts / timelines / infographics → **remotion**
- User can force with `"engine": "manim"` or `"remotion"`

---

## 8. Folder map (what matters)

```
manim-vid/
├── main.py                 # FastAPI
├── worker.py               # dual-engine pipeline
├── router.py               # manim vs remotion decision
├── prompts/                # LLM system prompts
├── services/
│   ├── llm.py
│   ├── renderer.py         # Manim
│   ├── remotion_renderer.py
│   ├── audio.py
│   ├── merger.py
│   └── storage.py          # R2 upload (boto3 S3)
├── remotion-src/           # Remotion React project
├── Dockerfile
├── docker-compose.yml
└── DEPLOY.md               # this file
```

---

## 9. Common failures

| Error                         | Fix                                                        |
| ----------------------------- | ---------------------------------------------------------- |
| `docker.sock no such file`    | Start Docker Desktop                                       |
| `lookup registry-1.docker.io` | Fix DNS/VPN; set Docker DNS to `8.8.8.8`                   |
| `Dockerfile not found`        | `cd` into project root before `docker build`               |
| R2 upload fails               | Check endpoint has **no** `/bucket` suffix; verify keys    |
| Remotion fails in Docker      | Ensure Chromium installed; `PUPPETEER_EXECUTABLE_PATH` set |
| OpenRouter 401/403            | Rotate/replace `OPENROUTER_API_KEY`                        |

---

## 10. Security checklist before going public

- [ ] Set `CLARITY_API_KEY`
- [ ] Restrict `ALLOWED_ORIGINS` to your frontend domains
- [ ] Rotate any keys that were ever pasted into chat/logs
- [ ] Keep `.env` out of git
- [ ] Prefer server-side Next.js proxy for API key
- [ ] Monitor rate limits / OpenRouter spend

---

You’re done when:

```bash
curl https://video.yourdomain.com/health
# {"status":"ok","service":"clarity-video"}
```

Then wire your Next.js app to `/video/request` + `/video/status/{id}` and stream the returned R2 URL.
