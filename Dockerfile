# Kanat — üretim imajı
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Yalnızca gerekenler; derleyici imaja girmez (psycopg[binary] ve argon2 hazır tekerlek kullanır)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Statik dosyalar imaj oluşturulurken toplanır (gizli anahtar gerektirmeyen geçici değerlerle)
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

# Root olmayan kullanıcı
RUN useradd --create-home --uid 10001 kanat \
    && mkdir -p /app/media /app/private_media \
    && chown -R kanat:kanat /app/media /app/private_media
USER kanat

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:8000/saglik/ || exit 1

ENTRYPOINT ["sh", "deploy/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", \
     "--access-logfile", "-", "--forwarded-allow-ips", "*"]
