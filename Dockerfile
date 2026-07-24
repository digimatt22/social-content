# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG NEXT_DEPLOYMENT_ID=local
ENV MARKETING_OS_REPOSITORY_REVISION=$NEXT_DEPLOYMENT_ID

RUN groupadd --system marketing-os && useradd --system --gid marketing-os --create-home marketing-os
WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY marketing_os ./marketing_os
COPY config ./config
COPY docs/business ./docs/business
COPY --chown=marketing-os:marketing-os scripts/sheldon-database-readiness.sh \
    scripts/sheldon-database-backup.sh \
    scripts/sheldon-database-restore-check.sh \
    scripts/sheldon-migrate.sh \
    scripts/sheldon-protected-rows.sh \
    ./scripts/
RUN pip install --no-cache-dir .

RUN mkdir -p /app/data /app/assets /app/outputs && chown -R marketing-os:marketing-os /app
USER marketing-os

EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--access-logfile", "-", "marketing_os.wsgi:app"]

FROM runtime AS database-tools

USER root
RUN apt-get update \
    && apt-get install --yes --no-install-recommends postgresql-17 postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/usr/lib/postgresql/17/bin:${PATH}"
USER marketing-os
