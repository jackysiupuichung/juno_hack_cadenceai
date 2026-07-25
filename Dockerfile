# syntax=docker/dockerfile:1

# ---- build stage -------------------------------------------------------
# uv resolves from uv.lock, so the image gets exactly the local versions.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies are their own layer: they only rebuild when the lock changes,
# not on every source edit.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# gunicorn is a deployment concern rather than a project dependency, so it is
# installed into the same venv instead of being added to pyproject.toml.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install gunicorn


# ---- runtime stage -----------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Run as a non-root user; the venv is copied in owned by that user so no
# recursive chown is needed at build time.
RUN useradd --create-home --uid 1000 cadence

WORKDIR /app

COPY --from=builder --chown=cadence:cadence /app/.venv /app/.venv
COPY --chown=cadence:cadence backend/ ./backend/
COPY --chown=cadence:cadence schemas/ ./schemas/
COPY --chown=cadence:cadence fixtures/ ./fixtures/
COPY --chown=cadence:cadence docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# The sqlite database lives here rather than beside the code, so a volume can
# outlive the container. settings.py still defaults to backend/db.sqlite3 for
# local non-Docker runs.
RUN mkdir -p /data && chown cadence:cadence /data
ENV CADENCE_DB_PATH=/data/db.sqlite3

USER cadence

# Hosts inject their own $PORT (Fly, Railway, Cloud Run all do); 8000 is the
# fallback for a plain `docker run`.
ENV PORT=8000
EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application"]
