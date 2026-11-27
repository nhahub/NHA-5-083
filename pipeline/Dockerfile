FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

COPY pipeline/requirements.txt /app/pipeline/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/pipeline/requirements.txt

COPY config/settings.toml config/cuisine_map.csv /app/config/
COPY sql/002_create_gold_views.sql /app/sql/002_create_gold_views.sql
COPY pipeline /app/pipeline

# Match Airflow's UID/GID (50000:0) so shared ./data and ./logs bind mounts stay writable by both containers.
RUN mkdir -p /app/data/bronze /app/data/quarantine /app/data/reports /app/logs \
    && useradd --uid 50000 --gid 0 --create-home appuser \
    && chown -R 50000:0 /app \
    && chmod -R g+rwX /app/data /app/logs

USER 50000:0

ENTRYPOINT ["python", "-m", "pipeline.runner"]
