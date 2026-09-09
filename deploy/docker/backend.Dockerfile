FROM python:3.13.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/app/backend/.venv/bin:$PATH
WORKDIR /app
RUN addgroup --system reweft \
    && adduser --system --ingroup reweft --home /nonexistent reweft \
    && mkdir -p /var/lib/reweft/evidence \
    && chown -R reweft:reweft /var/lib/reweft
COPY backend/pyproject.toml backend/uv.lock /app/backend/
COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/migrations /app/backend/migrations
COPY backend/src /app/backend/src
COPY deploy/docker/prepare-real-api.sh /usr/local/bin/prepare-real-api
RUN python -m pip install --no-cache-dir uv==0.11.14 \
    && cd /app/backend \
    && uv sync --frozen --no-dev
USER reweft
EXPOSE 8000
