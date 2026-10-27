FROM ghcr.io/cirruslabs/flutter:3.35.1 AS flutter-build

WORKDIR /src/flutter_app
COPY flutter_app/ ./
RUN flutter pub get \
    && flutter build web --release --base-href=/

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY . ./
COPY --from=flutter-build /src/flutter_app/build/web /app/flutter_app/build/web

CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 300"]
