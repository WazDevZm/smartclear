# syntax=docker/dockerfile:1

# ---------- Stage 1: build the officer web app ----------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: API + pipeline + baked demo database ----------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Minimal runtime libs for onnxruntime / OpenCV (headless) / pypdfium2
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY data/ ./data/
COPY models/ ./models/
COPY --from=frontend /app/frontend/dist ./frontend/dist

# HF Spaces runs the container as an unprivileged user; keep storage writable
RUN useradd -m -u 1000 user \
    && mkdir -p /app/storage/images /app/storage/uploads /app/storage/cache/docs \
    && chown -R user:user /app/storage
USER user

# Bake the seeded demo database into the image — first request is instant
RUN python backend/scripts/seed.py && python backend/scripts/seed_timeline.py

EXPOSE 7860

# FastAPI serves both the built SPA and /api on one port
CMD ["python", "-m", "uvicorn", "smartclear.api:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "7860"]
