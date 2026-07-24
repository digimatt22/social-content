FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system marketing-os && useradd --system --gid marketing-os --create-home marketing-os
WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY marketing_os ./marketing_os
COPY config ./config
COPY docs/business ./docs/business
RUN pip install --no-cache-dir .

RUN mkdir -p /app/data /app/assets /app/outputs && chown -R marketing-os:marketing-os /app
USER marketing-os

EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--access-logfile", "-", "marketing_os.wsgi:app"]
