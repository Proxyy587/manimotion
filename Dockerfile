FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    CHROME_BIN=/usr/bin/chromium

WORKDIR /app

# System deps: Manim + ffmpeg + Chromium (Remotion)
# build-essential/python3-dev/meson/ninja are required to compile pycairo/manimpango.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    meson \
    ninja-build \
    pkg-config \
    curl \
    ca-certificates \
    ffmpeg \
    libass9 \
    libass-dev \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpango1.0-dev \
    libffi-dev \
    libssl-dev \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    dvisvgm \
    ghostscript \
    fonts-liberation \
    fonts-dejavu-core \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 for Remotion
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python deps via uv — installs exactly what uv.lock says (--frozen).
# Always re-run `uv lock` after changing pyproject.toml dependencies.
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev \
    && /app/.venv/bin/python -c "import cryptography, psycopg; print('deps-ok')"

# Remotion deps (dev deps included: typescript powers the pre-render tsc check)
COPY remotion-src/package.json remotion-src/
RUN cd remotion-src && npm install

# App source
COPY . .
RUN mkdir -p outputs remotion-src/src/compositions

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
