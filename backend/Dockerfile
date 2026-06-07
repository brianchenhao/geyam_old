FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg for video frame extraction (training pipeline)
# libgl1 + libglib2 for OpenCV/ultralytics
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only torch first so ultralytics' transitive resolver doesn't pull
# the multi-GB CUDA wheels. The VPS has no GPU and the laptop runs inference on
# CPU anyway. Cuts the final image from ~12 GB to ~3 GB.
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
    --timeout 600 --retries 5 \
    torch torchvision

COPY requirements.txt .
RUN pip install --timeout 600 --retries 5 -r requirements.txt

COPY . .

EXPOSE 8000

# Run migrations on boot, then serve.
CMD alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000
