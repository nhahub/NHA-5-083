FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

COPY web/backend/requirements.txt /app/web/backend/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/web/backend/requirements.txt

# Pre-bake the ONNX semantic model so container startups stay fast and offline-capable.
RUN python -c "from huggingface_hub import hf_hub_download; hf_hub_download('sentence-transformers/all-MiniLM-L6-v2', 'onnx/model.onnx'); hf_hub_download('sentence-transformers/all-MiniLM-L6-v2', 'tokenizer.json')"

COPY config/settings.toml config/cuisine_map.csv /app/config/
COPY web/__init__.py /app/web/__init__.py
COPY web/backend /app/web/backend

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
