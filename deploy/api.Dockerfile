FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GIVVI_ENVIRONMENT=production
WORKDIR /app
COPY requirements.txt ./
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 givvi \
    && useradd --uid 10001 --gid givvi --no-create-home givvi
COPY givvi ./givvi
COPY migrations ./migrations
COPY alembic.ini pyproject.toml ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=3)"]
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=2", "--timeout=30", "--graceful-timeout=30", "--worker-tmp-dir=/tmp", "--forwarded-allow-ips=", "givvi:create_app()"]