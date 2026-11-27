FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

COPY web/streamlit/requirements.txt /app/web/streamlit/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/web/streamlit/requirements.txt

COPY config/settings.toml /app/config/settings.toml
COPY web/__init__.py /app/web/__init__.py
COPY web/streamlit /app/web/streamlit

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8501

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "web/streamlit/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
