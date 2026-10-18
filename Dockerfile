FROM python:3.12-slim

# The application is pure standard library (sqlite3, ast, argparse, dataclasses),
# so there is nothing to install and no network access beyond pulling this image.

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CALC_DB=/data/calc.db

# /data is created here, owned by the unprivileged user, *before* the named
# volume is mounted onto it. Docker copies a fresh volume's initial contents and
# ownership from the image, which is what lets the non-root user write the
# database. See the troubleshooting section of the README.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data \
    && chown app:app /data

# `docker exec` does not use ENTRYPOINT, so the command is exposed as a wrapper
# on PATH instead of an entry point.
RUN printf '#!/bin/sh\nexec python -m calc "$@"\n' > /usr/local/bin/calc \
    && chmod 0755 /usr/local/bin/calc

WORKDIR /app
COPY src/ /app/

USER app

# Idle so the container can be `docker exec`-ed into.
CMD ["sleep", "infinity"]
