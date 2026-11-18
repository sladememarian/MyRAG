# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_RETRIES=10 \
    PIP_TIMEOUT=120

WORKDIR /app

# libgomp1 is used by torch; curl is used for the compose healthcheck.
# The retry options and the cache mounts keep the build alive on slow or
# flaky connections: a failed build reuses the files it already downloaded.
# Debian's HTTP mirror is unreliable here, so switch it to HTTPS first.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update -o Acquire::Retries=10 -o Acquire::http::Timeout=60 \
    && apt-get install -y --no-install-recommends \
        -o Acquire::Retries=10 -o Acquire::http::Timeout=60 \
        libgomp1 curl

COPY requirements-base.txt requirements-docker.txt /app/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install -r /app/requirements-docker.txt

COPY . /app

RUN chmod +x /app/entrypoint.sh

# `sh` keeps the entrypoint runnable even if the bind mount loses the exec bit.
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
