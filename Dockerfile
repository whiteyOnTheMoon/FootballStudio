FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/footballstudio

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 footballstudio

COPY --chown=footballstudio:footballstudio . .

USER footballstudio
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_world_catalog && exec gunicorn app.config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --error-logfile - --log-level warning"]
