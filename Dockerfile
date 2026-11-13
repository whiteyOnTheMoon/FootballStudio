FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/footballstudio

# Local-only, zero-provider video and English speech engine. All runtime
# utilities are Debian packages; no user uploads or web assets are involved
# in the synthetic readiness check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg espeak-ng fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 footballstudio

COPY --chown=footballstudio:footballstudio . .

USER footballstudio
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_world_catalog && exec gunicorn app.config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --error-logfile - --log-level warning"]
